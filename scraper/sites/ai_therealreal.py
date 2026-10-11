"""Optimized TheRealReal scraper: Fixed pagination and performance issues."""

import random
import re
import json
import os
import asyncio
import hashlib
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup
from anthropic import Anthropic
from .base import BaseSiteScraper
from ..mappings.brand_urls import brand_mappings
from ..utils.data_models import Product, ProductImage
from ..utils.optimized_image_handler import OptimizedImageHandler
from ..utils.session_manager import session_manager

class AITheRealRealScraper(BaseSiteScraper):
    def __init__(self, scrapfly_client, rate_limit: float = 2.0, download_images: bool = True):
        super().__init__(scrapfly_client, rate_limit)
        
        # Site constants
        self.SITE_DOMAIN = "therealreal.com"
        self.CDN_DOMAIN = "product-images.therealreal.com"
        
        # Timing constants - REDUCED for better performance
        self.MIN_RENDERING_WAIT = 3000  # Reduced from 5000
        self.MAX_RENDERING_WAIT = 5000  # Reduced from 8000
        
        # Data limits - REDUCED for production mode
        self.MAX_MODEL_LENGTH = 20
        self.PRODUCT_ID_LENGTH = 16
        self.MAX_PAGES_DEFAULT = 15  # Reduced from 30 - most products found in first 15 pages
        self.EMPTY_PAGE_TOLERANCE = 3  # Increased from 2 - allow 3 consecutive empty pages
        self.NO_NEW_PRODUCTS_TOLERANCE = 5  # NEW: Stop if 5 consecutive pages have no new products
        self.MAX_CONCURRENT_CATEGORIES = 1  # Reduced from 2 to avoid conflicts
        
        # Initialize Anthropic client
        api_key = os.getenv('ANTHROPIC_API_KEY')
        self.anthropic = Anthropic(api_key=api_key) if api_key else None
        
        # Image settings
        self.download_images = download_images
        self.base_image_dir = "images"
        self.max_images_per_product = 2
        
        # Session management
        self.current_session = None
        self.session_request_count = 0
        
        # Time tracking
        self.start_time = None
        self.category_times = {}
        self.product_processing_times = []

    def _clean_brand_name(self, brand: str) -> str:
        """Remove thread pollution from brand name."""
        return re.sub(r'_thread_\d+', '', brand)

    def _detect_gender_from_url(self, url: str) -> str:
        """Detect gender from URL."""
        url_lower = url.lower()
        return 'women' if '/women/' in url_lower else 'men' if '/men/' in url_lower else 'unisex'

    def _generate_product_id(self, brand: str, model: str, sku: str) -> str:
        """Generate a consistent product ID from brand, model, and SKU."""
        clean_brand = re.sub(r'[^a-zA-Z0-9]', '', brand.lower())
        clean_model = re.sub(r'[^a-zA-Z0-9]', '', model.lower()[:self.MAX_MODEL_LENGTH])
        clean_sku = sku if sku else 'nosku'
        
        combined = f"{clean_brand}:{clean_model}:{clean_sku}"
        hash_obj = hashlib.sha256(combined.encode())
        return hash_obj.hexdigest()[:self.PRODUCT_ID_LENGTH]

    def _parse_model_from_title(self, full_title: str, expected_brand: str) -> str:
        """Parse model from title, removing the brand if present."""
        full_title_lower = full_title.lower()
        expected_brand_lower = expected_brand.lower()
        
        if full_title_lower.startswith(expected_brand_lower):
            model = full_title[len(expected_brand):].strip()
            if model.startswith('-') or model.startswith(':'):
                model = model[1:].strip()
            return model if model else full_title
        
        return full_title
    
    def get_site_name(self) -> str:
        return "therealreal"
    
    def get_brand_search_urls(self, brand: str) -> List[str]:
        """Get brand URLs from mappings."""
        urls = []
        
        # Try to find brand mapping
        mapping = brand_mappings.find_brand_mapping("therealreal", brand)
        
        if mapping and mapping.active:
            # Handle both single URL and list of URLs
            if isinstance(mapping.url, list):
                urls.extend(mapping.url)
            else:
                urls.append(mapping.url)
        
        # Fallback URLs if no mappings found
        if not urls:
            brand_formatted = brand.lower().replace(' ', '-').replace('&', '-')
            fallback_urls = [
                f"https://www.{self.SITE_DOMAIN}/designers/{brand_formatted}"
            ]
            urls.extend(fallback_urls)
        
        return urls
    
    def get_supported_brands(self) -> List[str]:
        return brand_mappings.get_supported_brands("therealreal")
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """Get scraping statistics."""
        session_stats = session_manager.get_session_stats()
        
        return {
            'session_requests': self.session_request_count,
            'current_session': self.current_session[:20] if self.current_session else 'None',
            'session_manager_stats': session_stats,
            'error_counts': {
                'total_errors': 0,
                'session_errors': 0,
                'timeout_errors': 0,
                'asp_errors': 0
            }
        }
    
    async def scrape_brand_products(self, brand: str, max_products: int = None) -> List[Product]:
        """Enhanced scraping with session management and stats."""
        self.start_time = time.time()
        
        try:
            # Step 1: Get category URLs
            category_urls = self.get_brand_search_urls(brand)
            print(f"📍 Found {len(category_urls)} category URLs for {brand}")
            
            # Step 2: Process categories - SIMPLIFIED for production
            all_products_data = await self._process_categories_sequential(
                category_urls, brand, max_products
            )
            
            if not all_products_data:
                print("❌ No products found")
                return []
                
            print(f"🔍 Found {len(all_products_data)} products")
            
            # Apply max_products limit with image prioritization
            if max_products:
                products_with_images = [p for p in all_products_data if p.get('images')]
                products_without_images = [p for p in all_products_data if not p.get('images')]
                
                if len(products_with_images) >= max_products:
                    all_products_data = products_with_images[:max_products]
                else:
                    needed = max_products - len(products_with_images)
                    all_products_data = products_with_images + products_without_images[:needed]
            
            # Step 3: Download images if enabled
            if self.download_images and all_products_data:
                print(f"📸 Downloading images for {len(all_products_data)} products...")
                all_products_data = await self._download_images_for_products(all_products_data, brand)
            
            # Step 4: Convert to Product objects with BATCHED AI categorization
            print(f"🤖 Converting to Product objects...")
            products = await self._convert_to_product_objects(all_products_data)
            
            print(f"✅ Successfully processed {len(products)} products")
            return products
            
        except Exception as e:
            print(f"❌ Error in scrape_brand_products: {e}")
            return []
    
    async def _process_categories_sequential(self, category_urls: List[str], brand: str, max_products: int = None) -> List[Dict[str, Any]]:
        """Process categories sequentially - FIXED for production mode."""
        all_products_data = []
        
        for i, category_url in enumerate(category_urls, 1):
            print(f"🔄 Processing category {i}/{len(category_urls)}: {category_url}")
            category_start = time.time()
            
            try:
                # FIXED: Pass first_page_only=False for production mode
                products_data = await self._extract_urls_and_product_info(
                    category_url, brand, thread_operation=None, first_page_only=False
                )
                
                if products_data:
                    all_products_data.extend(products_data)
                    print(f"✅ Category {i}: Found {len(products_data)} products")
                else:
                    print(f"⚠️ Category {i}: No products found")
                
                category_time = time.time() - category_start
                category_name = f"Category_{i}"
                self.category_times[category_name] = category_time
                
                # Early exit if we have enough products
                if max_products and len(all_products_data) >= max_products:
                    print(f"🎯 Reached target of {max_products} products")
                    break
                
            except Exception as e:
                print(f"❌ Error processing category {i}: {e}")
                continue
        
        return all_products_data
    
    def _extract_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        """Extract the next page URL from TheRealReal's pagination structure - OPTIMIZED."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Strategy 1: Look for the specific pagination structure
            next_link = soup.find('a', {
                'class': lambda x: x and 'pagination__nav-link' in x,
                'aria-label': lambda x: x and 'Go to Next Page' in x
            })
            
            if next_link and next_link.get('href'):
                next_href = next_link['href']
                # Convert relative URL to absolute
                if next_href.startswith('/'):
                    next_url = f"https://www.{self.SITE_DOMAIN}{next_href}"
                else:
                    next_url = next_href
                
                # Clean up the URL (remove _pjax parameter)
                if '_pjax=' in next_url:
                    parsed = urlparse(next_url)
                    query_params = parse_qs(parsed.query)
                    if '_pjax' in query_params:
                        del query_params['_pjax']
                    
                    new_query = urlencode(query_params, doseq=True)
                    next_url = urlunparse((
                        parsed.scheme, parsed.netloc, parsed.path,
                        parsed.params, new_query, parsed.fragment
                    ))
                
                return next_url
            
            # Strategy 2: Look for any link with "Next" 
            next_patterns = [
                {'aria-label': lambda x: x and 'next' in x.lower()},
                {'class': lambda x: x and 'next' in ' '.join(x).lower()},
            ]
            
            for pattern in next_patterns:
                next_link = soup.find('a', pattern)
                if next_link and next_link.get('href'):
                    next_href = next_link['href']
                    if next_href.startswith('/'):
                        return f"https://www.{self.SITE_DOMAIN}{next_href}"
                    elif next_href.startswith('http'):
                        return next_href
            
            return None
            
        except Exception as e:
            print(f"❌ Error extracting next page URL: {e}")
            return None
    
    async def _extract_urls_and_product_info(self, page_url: str, brand: str, 
                                           thread_operation: str = None, 
                                           first_page_only: bool = False) -> List[Dict[str, Any]]:
        """Extract URLs and product info - FIXED pagination logic with better exit conditions."""
        all_products_data = []
        all_seen_urls = set()
        page_num = 1
        max_pages = 1 if first_page_only else self.MAX_PAGES_DEFAULT
        consecutive_empty_pages = 0
        consecutive_no_new_products = 0  # NEW: Track consecutive pages with no new products
        current_url = page_url
        
        print(f"🔍 Starting pagination - max_pages: {max_pages}")
        
        while (page_num <= max_pages and 
               consecutive_empty_pages < self.EMPTY_PAGE_TOLERANCE and 
               consecutive_no_new_products < self.NO_NEW_PRODUCTS_TOLERANCE and 
               current_url):
            
            print(f"📄 Processing page {page_num}/{max_pages}")
            
            try:
                # Use thread_operation if provided, otherwise default operation
                operation = f"{thread_operation}_page_{page_num}" if thread_operation else f"page_{page_num}"
                
                result = await self.make_request_with_session(
                    url=current_url,
                    brand=brand,
                    operation=operation,
                    render_js=True,
                    rendering_wait=random.randint(self.MIN_RENDERING_WAIT, self.MAX_RENDERING_WAIT),
                    auto_scroll=True,
                )
                
                if not result or result.status_code != 200:
                    print(f"❌ Failed to get page {page_num}: {result.status_code if result else 'No result'}")
                    consecutive_empty_pages += 1
                    consecutive_no_new_products += 1
                    break

                gender = self._detect_gender_from_url(page_url)
                page_products_data = await self._extract_products_with_urls_and_info(
                    result.content, current_url, brand, gender
                )
                
                if not page_products_data:
                    print(f"⚠️ No products found on page {page_num}")
                    consecutive_empty_pages += 1
                    consecutive_no_new_products += 1
                    
                    if first_page_only:
                        break
                    
                    # Try to get next page URL even if no products found
                    next_url = self._extract_next_page_url(result.content, current_url)
                    current_url = next_url
                    page_num += 1
                    continue
                
                print(f"✅ Found {len(page_products_data)} products on page {page_num}")
                
                # FIXED: Duplicate detection logic for multi-page scraping
                if not first_page_only and page_num > 1:
                    current_page_urls = [
                        product.get('source_url', '') for product in page_products_data 
                        if product.get('source_url')
                    ]
                    
                    new_product_urls = [url for url in current_page_urls if url not in all_seen_urls]
                    
                    if len(new_product_urls) == 0:
                        print(f"⚠️ No new products on page {page_num} - may be duplicate page")
                        consecutive_no_new_products += 1
                        
                        # IMPROVED: Check if we should exit based on consecutive no-new-products
                        if consecutive_no_new_products >= self.NO_NEW_PRODUCTS_TOLERANCE:
                            print(f"🛑 Stopping: {consecutive_no_new_products} consecutive pages with no new products")
                            break
                        
                        # Still try to get next page
                        next_url = self._extract_next_page_url(result.content, current_url)
                        if not next_url:
                            print("🔚 No more pages found")
                            break
                        current_url = next_url
                        page_num += 1
                        continue
                    
                    # Only add new products
                    new_products_data = []
                    for product in page_products_data:
                        product_url = product.get('source_url', '')
                        if product_url in new_product_urls:
                            new_products_data.append(product)
                    
                    all_products_data.extend(new_products_data)
                    all_seen_urls.update(new_product_urls)
                    print(f"✅ Added {len(new_products_data)} new products from page {page_num}")
                    
                    # Reset consecutive counters if we found new products
                    if len(new_products_data) > 0:
                        consecutive_no_new_products = 0
                        consecutive_empty_pages = 0
                    else:
                        consecutive_no_new_products += 1
                    
                else:
                    # First page or first_page_only mode
                    all_products_data.extend(page_products_data)
                    
                    current_page_urls = [
                        product.get('source_url', '') for product in page_products_data 
                        if product.get('source_url')
                    ]
                    all_seen_urls.update(current_page_urls)
                    
                    # Reset counters for first page
                    consecutive_empty_pages = 0
                    consecutive_no_new_products = 0
                
                if first_page_only:
                    print("🎯 First page only mode - stopping")
                    break
                
                # Get next page URL for the next iteration
                next_url = self._extract_next_page_url(result.content, current_url)
                if not next_url:
                    print("🔚 No more pages found")
                    break
                
                current_url = next_url
                page_num += 1
                
                # Add small delay between pages
                await asyncio.sleep(random.uniform(1.0, 2.0))
                
            except Exception as e:
                print(f"❌ Error processing page {page_num}: {e}")
                consecutive_empty_pages += 1
                consecutive_no_new_products += 1
                page_num += 1
                
                if (consecutive_empty_pages >= self.EMPTY_PAGE_TOLERANCE or 
                    consecutive_no_new_products >= self.NO_NEW_PRODUCTS_TOLERANCE):
                    print(f"🛑 Too many consecutive issues - stopping")
                    break
                
                # Try to continue with next page if possible
                if result and result.content:
                    next_url = self._extract_next_page_url(result.content, current_url)
                    current_url = next_url
                else:
                    break
        
        # Final summary
        if consecutive_no_new_products >= self.NO_NEW_PRODUCTS_TOLERANCE:
            print(f"🛑 Stopped due to {consecutive_no_new_products} consecutive pages with no new products")
        elif consecutive_empty_pages >= self.EMPTY_PAGE_TOLERANCE:
            print(f"🛑 Stopped due to {consecutive_empty_pages} consecutive empty pages")
        elif page_num > max_pages:
            print(f"🛑 Stopped due to reaching max pages limit ({max_pages})")
        
        print(f"📊 Pagination complete: {len(all_products_data)} total products from {page_num-1} pages")
        return all_products_data

    async def _extract_products_with_urls_and_info(self, html: str, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """Extract product info."""
        try:
            # Extract URLs
            product_urls = await self._extract_product_urls_robust(html)
            
            # Extract container info
            soup = BeautifulSoup(html, 'html.parser')
            product_containers_info = await self._extract_product_containers_info(soup, page_url, brand, gender)
            
            # Match URLs to containers
            matched_products = await self._match_urls_to_containers(product_urls, product_containers_info, page_url, brand, gender)
            
            return matched_products
            
        except Exception as e:
            print(f"❌ Error extracting products: {e}")
            return []
    
    async def _extract_product_urls_robust(self, html: str) -> List[str]:
        """Robust URL extraction method adapted for TheRealReal."""
        urls = set()
        
        # Multiple regex patterns to catch different formats for TheRealReal
        patterns = [
            r'href=["\']([^"\']*\/products\/[^"\']*)["\']',  # /products/ URLs
            r'href=["\']([^"\']*therealreal\.com[^"\']*\/products\/[^"\']*)["\']',
            r'https://[^"\s]*therealreal\.com[^"\s]*\/products\/[^"\s]*',
            r'\/products\/([^\/\s"\']+)',
        ]
        
        all_matches = []
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            all_matches.extend(matches)
        
        # Process all matches
        for match in all_matches:
            url = match
            
            # Clean and complete the URL
            if url.startswith('/'):
                url = f"https://www.{self.SITE_DOMAIN}{url}"
            elif not url.startswith('http'):
                if '/products/' in url or url.startswith('products/'):
                    if not url.startswith('/'):
                        url = '/' + url
                    url = f"https://www.{self.SITE_DOMAIN}{url}"
                else:
                    continue
            
            url = url.replace('\\', '')
            
            # Remove query parameters except for important ones
            if '?' in url:
                base_url, query = url.split('?', 1)
                url = base_url  # TheRealReal products don't need query params
            
            if self._is_valid_product_url(url):
                urls.add(url)
        
        # BeautifulSoup approach for additional URLs
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            all_links = soup.find_all(['a', 'link'], href=True)
            for link in all_links:
                href = link.get('href', '')
                if '/products/' in href and href not in [u for u in urls]:
                    if href.startswith('/'):
                        href = f"https://www.{self.SITE_DOMAIN}{href}"
                    if self._is_valid_product_url(href):
                        urls.add(href)
            
            for element in soup.find_all(attrs=True):
                for attr, value in element.attrs.items():
                    if isinstance(value, str) and '/products/' in value and 'http' in value:
                        if self._is_valid_product_url(value):
                            urls.add(value)
            
        except Exception as e:
            pass
        
        return list(urls)
    
    async def _extract_product_containers_info(self, soup: BeautifulSoup, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """Find the actual product containers."""
        product_containers = []
        
        # Strategy 1: Look for divs that directly contain product links
        all_links = soup.find_all('a', href=lambda x: x and '/products/' in x)
        
        # Get the immediate parent of each product link
        for link in all_links:
            # Try different parent levels to find the product container
            for parent_level in range(1, 4):  # Check 1-3 levels up
                current = link
                for _ in range(parent_level):
                    current = current.parent
                    if not current:
                        break
                
                if current and current.name in ['div', 'article', 'li']:
                    # Check if this container has images
                    container_images = current.find_all('img')
                    if container_images and current not in product_containers:
                        product_containers.append(current)
                        break
        
        # Strategy 2: If still no containers, look for common class patterns
        if not product_containers:
            class_patterns = [
                'product-card',
                'product-item', 
                'product-grid-item',
                'listing-item',
                'item-card'
            ]
            
            for pattern in class_patterns:
                containers = soup.find_all('div', class_=lambda x: x and pattern in ' '.join(x) if x else False)
                if containers:
                    product_containers.extend(containers)
                    break
        
        # Strategy 3: Fallback - any div with both a product link AND an image
        if not product_containers:
            all_divs = soup.find_all('div')
            for div in all_divs:
                has_product_link = div.find('a', href=lambda x: x and '/products/' in x)
                has_image = div.find('img')
                if has_product_link and has_image:
                    product_containers.append(div)
        
        # Extract info from containers
        containers_info = []
        
        for i, container in enumerate(product_containers):
            try:
                container_info = self._extract_info_from_container(container, page_url, brand, gender)
                if container_info:
                    containers_info.append(container_info)
            except Exception as e:
                continue
        
        return containers_info

    def _extract_info_from_container(self, container, page_url: str, brand: str, gender: str) -> Optional[Dict[str, Any]]:
        """Extract info from container."""
        try:
            # Step 1: Find product URL
            link_elem = container.find('a', href=lambda x: x and '/products/' in x)
            if not link_elem:
                return None
            
            container_url = link_elem['href']
            
            if not container_url.startswith('http'):
                if container_url.startswith('/'):
                    container_url = f"https://www.{self.SITE_DOMAIN}{container_url}"
                else:
                    container_url = f"https://www.{self.SITE_DOMAIN}/{container_url}"
            
            if not self._is_valid_product_url(container_url):
                return None
            
            # Step 2: Enhanced title extraction
            title_elem = None
            full_title = None
            
            # Strategy 1: Try specific TheRealReal title selectors
            therealreal_selectors = [
                '.product-card__title',
                '.product-card__name', 
                '.product-card-title',
                '.product-title',
                '.card-title',
                '.item-title',
                '.product-name'
            ]
            
            for selector in therealreal_selectors:
                title_elem = container.select_one(selector)
                if title_elem:
                    full_title = title_elem.get_text(strip=True)
                    if full_title:
                        break
            
            # Strategy 2: Try generic selectors
            if not full_title:
                generic_selectors = [
                    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',  # All headers
                    '[class*="title"]', 
                    '[class*="name"]',
                    '[class*="product"]',
                    'span[class*="title"]',
                    'div[class*="title"]',
                    'p[class*="title"]'
                ]
                
                for selector in generic_selectors:
                    elements = container.select(selector) if selector.startswith('[') else container.find_all(selector)
                    
                    for elem in elements:
                        text = elem.get_text(strip=True)
                        if text and len(text) > 5 and len(text) < 200:  # Reasonable title length
                            full_title = text
                            break
                    
                    if full_title:
                        break
            
            # Strategy 3: Extract from the product link's text or nearby elements
            if not full_title:
                # Check the link text itself
                link_text = link_elem.get_text(strip=True)
                if link_text and len(link_text) > 5:
                    full_title = link_text
                
                # Check link's siblings
                if not full_title:
                    for sibling in link_elem.find_next_siblings():
                        text = sibling.get_text(strip=True)
                        if text and len(text) > 5 and len(text) < 200:
                            full_title = text
                            break
                
                # Check elements near the link
                if not full_title:
                    parent = link_elem.parent
                    if parent:
                        for child in parent.find_all(text=True, recursive=True):
                            text = str(child).strip()
                            if text and len(text) > 10 and len(text) < 200:
                                # Skip obvious non-title text
                                if not any(skip in text.lower() for skip in ['price', '$', 'size', 'color', 'sold', 'new']):
                                    full_title = text
                                    break
            
            # Strategy 4: Fallback - extract from URL
            if not full_title:
                url_parts = container_url.split('/')
                if len(url_parts) > 0:
                    # Get the last part (slug) and convert to title
                    slug = url_parts[-1]
                    if slug:
                        # Remove common URL suffixes
                        slug = slug.split('?')[0].split('#')[0]
                        # Convert slug to title
                        full_title = slug.replace('-', ' ').title()
            
            if not full_title:
                return None
            
            # Step 3: Extract images
            images = self._extract_images_from_container(container)
            
            # Step 4: Extract other info
            model = self._parse_model_from_title(full_title, brand)
            sku = self._extract_sku_from_url(container_url)
            product_id = self._generate_product_id(brand, model, sku)
            
            # Create product name
            if gender != 'unisex':
                product_name = f"{brand} {model} {gender}"
            else:
                product_name = f"{brand} {model}"
            
            result = {
                'container_url': container_url,
                'product_id': product_id,
                'brand': brand,
                'model': model,
                'sku': sku,
                'product_name': product_name,
                'description': '',
                'images': images,
                'source_url': container_url
            }
            
            return result
            
        except Exception as e:
            return None

    def _extract_images_from_container(self, container) -> List[str]:
        """Extract images from container - FIXED for TheRealReal lazy loading."""
        images = []
        
        # Strategy 1: Find all img elements and check data-src first
        img_elements = container.find_all('img')
        for img in img_elements:
            # TheRealReal uses data-src for lazy loading - check this FIRST
            src_attrs = [
                'data-src',      # PRIMARY: TheRealReal uses this for lazy loading
                'data-srcset',   # SECONDARY: Responsive images
                'src',           # FALLBACK: Already loaded images
                'data-lazy-src', 
                'data-original', 
                'data-image-src',
                'srcset'
            ]
            
            for attr in src_attrs:
                src = img.get(attr)
                if src:
                    # Handle srcset format if needed
                    if attr in ['data-srcset', 'srcset']:
                        # Extract first URL from srcset: "url1 110w, url2 220w, ..."
                        urls = [url.strip().split(' ')[0] for url in str(src).split(',')]
                        for url in urls:
                            if url and self._is_valid_product_image(url):
                                enhanced_url = self._enhance_image_url(url)
                                if enhanced_url not in images:
                                    images.append(enhanced_url)
                    else:
                        # Regular src attribute
                        if self._is_valid_product_image(src):
                            enhanced_url = self._enhance_image_url(src)
                            if enhanced_url not in images:
                                images.append(enhanced_url)
                    
                    # Break after finding first valid source
                    if images:
                        break
        
        return images[:self.max_images_per_product]

    async def _match_urls_to_containers(self, product_urls: List[str], 
                                    containers_info: List[Dict[str, Any]], 
                                    page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """
        Match robust URL extraction results with container info.
        This ensures we get ALL products (from URL extraction) with as much info as possible.
        """
        matched_products = []
        
        # Create a lookup for container info by URL
        container_lookup = {}
        for container_info in containers_info:
            container_url = container_info.get('container_url', '')
            if container_url:
                # Normalize URL for matching
                normalized_url = container_url.split('?')[0]  # Remove query params
                container_lookup[normalized_url] = container_info
        
        # Match each URL to container info
        for product_url in product_urls:
            # Normalize URL for matching
            normalized_url = product_url.split('?')[0]
            
            if normalized_url in container_lookup:
                # Perfect match - use container info
                container_info = container_lookup[normalized_url].copy()
                container_info['source_url'] = product_url  # Use the original URL
                del container_info['container_url']  # Remove internal field
                matched_products.append(container_info)
            else:
                # No container match - create minimal product from URL
                minimal_product = await self._create_minimal_product_from_url(product_url, page_url, brand, gender)
                if minimal_product:
                    matched_products.append(minimal_product)
        
        return matched_products
    
    async def _create_minimal_product_from_url(self, product_url: str, page_url: str, brand: str, gender: str) -> Dict[str, Any]:
        """Create minimal product data when no container info is available."""
        try:
            # Extract SKU from URL (TheRealReal slug)
            sku = self._extract_sku_from_url(product_url)
            
            # Try to extract product name from URL path
            # Example: /products/women/shoes/flats/chanel-interlocking-cc-logo-leather-espadrilles-qfejg
            url_parts = product_url.split('/')
            if len(url_parts) >= 6 and 'products' in url_parts:
                # Get the last part which should be the product slug
                product_slug = url_parts[-1]
                product_name = product_slug.replace('-', ' ').title()
                brand_parsed, model = self._parse_brand_and_model(product_name)
            else:
                brand_parsed = brand
                model = "Unknown Product"
                product_name = f"{brand_parsed} {model}"

            # Generate product ID
            product_id = self._generate_product_id(brand_parsed, model, sku)
            
            # Create product name with gender
            if gender != 'unisex':
                product_name = f"{brand_parsed} {model} {gender}"
            else:
                product_name = f"{brand_parsed} {model}"
            
            return {
                'product_id': product_id,
                'source_url': product_url,
                'brand': brand_parsed,
                'model': model,
                'sku': sku,
                'product_name': product_name,
                'description': '',
                'images': []
            }
            
        except Exception as e:
            return None

    def _parse_brand_and_model(self, full_title: str) -> Tuple[str, str]:
        """Parse brand and model from full product title."""
        brands = [
            'Chanel', 'Louis Vuitton', 'Gucci', 'Hermès', 'Hermes', 'Prada', 'Dior', 
            'Versace', 'Balenciaga', 'Saint Laurent', 'Bottega Veneta',
            'Burberry', 'Valentino', 'Givenchy', 'Fendi', 'Celine',
            'Tom Ford', 'Alexander McQueen', 'Stella McCartney', 'Off-White',
            'Golden Goose', 'Maison Margiela', 'Thom Browne', 'Jacquemus',
            'Isabel Marant', 'Ganni', 'Acne Studios', 'Stone Island',
            'Coach', 'Michael Kors', 'Kate Spade', 'Tory Burch', 'Marc Jacobs',
            'Adidas', 'Nike', 'Balenciaga', 'Yeezy', 'Converse'
        ]
        
        full_title_lower = full_title.lower()
        
        for brand in brands:
            if brand.lower() in full_title_lower:
                brand_index = full_title_lower.find(brand.lower())
                model = full_title[brand_index + len(brand):].strip()
                
                if model.startswith('-') or model.startswith(':'):
                    model = model[1:].strip()
                
                return brand, model if model else full_title
        
        parts = full_title.split(' ', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        else:
            return 'Unknown Brand', full_title
    
    def _extract_sku_from_url(self, url: str) -> Optional[str]:
        """Extract SKU from product URL (TheRealReal uses the slug as identifier)."""
        try:
            url_parts = url.split('/')
            if url_parts and url_parts[-1]:
                return url_parts[-1].split('?')[0]  # Remove query params if any
            return None
        except:
            return None
    
    def _is_valid_product_image(self, img_url: str) -> bool:
        """Fixed validation - simplified and more permissive for TheRealReal."""
        if not img_url or not isinstance(img_url, str):
            return False
        
        img_url_lower = img_url.lower()
        
        # MUST contain product-images.therealreal.com (their CDN)
        if 'product-images.therealreal.com' not in img_url_lower:
            return False
        
        # Skip obvious non-product patterns
        skip_patterns = ['logo', 'icon', 'favicon', 'sprite']
        if any(pattern in img_url_lower for pattern in skip_patterns):
            return False
        
        # Must be an image file
        if not any(ext in img_url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            return False
        
        return True

    def _enhance_image_url(self, img_url: str) -> str:
        """Enhanced image URL optimization for TheRealReal CDN."""
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = f'https://www.{self.SITE_DOMAIN}{img_url}'
        
        # TheRealReal image optimization
        if 'product-images.therealreal.com' in img_url:
            # Remove existing width/height params and add our preferred size
            base_url = img_url.split('?')[0]
            
            # For TheRealReal, request larger images
            if '?' in img_url:
                img_url = f"{base_url}?width=1200"  # Larger than original 1005
            else:
                img_url = f"{img_url}?width=1200"
        
        # Handle other size parameters if present
        elif 'w=' in img_url or 'h=' in img_url:
            img_url = re.sub(r'w=\d+', 'w=1200', img_url)
            img_url = re.sub(r'h=\d+', 'h=1200', img_url)
        
        return img_url
    
    def _is_valid_product_url(self, url: str) -> bool:
        """Check if URL is a valid product page."""
        return bool(url and self.SITE_DOMAIN in url and '/products/' in url)
    
    async def _download_images_for_products(self, products_data: List[Dict[str, Any]], brand: str) -> List[Dict[str, Any]]:
        """Download images for all products using the optimized image handler."""
        try:
            async with OptimizedImageHandler(
                base_image_dir=self.base_image_dir,
                max_images_per_product=self.max_images_per_product
            ) as image_handler:
                
                products_for_download = []
                for data in products_data:
                    if data.get('images'):
                        clean_brand = self._clean_brand_name(brand)
                        
                        product_id = data.get('product_id', f"{clean_brand}_{data.get('sku', 'unknown')}")
                        products_for_download.append({
                            'product_id': product_id,
                            'brand': clean_brand,
                            'image_urls': data['images'][:self.max_images_per_product]
                        })
                
                if not products_for_download:
                    return products_data
                
                enhanced_products = await image_handler.download_images_streaming(
                    products_for_download, batch_size=30  # Reduced batch size
                )
                
                # Merge image data back
                enhanced_lookup = {p['product_id']: p for p in enhanced_products}
                
                for data in products_data:
                    clean_brand = self._clean_brand_name(brand)
                    
                    product_id = data.get('product_id', f"{clean_brand}_{data.get('sku', 'unknown')}")
                    if product_id in enhanced_lookup:
                        enhanced = enhanced_lookup[product_id]
                        if enhanced.get('images'):
                            data['downloaded_images'] = enhanced['images']
                
                return products_data
                
        except Exception as e:
            print(f"❌ Error downloading images: {e}")
            return products_data
    
    async def _convert_to_product_objects(self, products_data: List[Dict[str, Any]]) -> List[Product]:
        """Convert scraped data to Product objects with BATCHED AI categorization."""
        from ..utils.ai_categorizer import ai_categorizer
        
        conversion_start = time.time()
        
        products = []
        
        # Use BATCHED AI categorization instead of individual calls
        try:
            # Process in smaller batches for better performance
            batch_size = 50
            categories = []
            
            for i in range(0, len(products_data), batch_size):
                batch = products_data[i:i+batch_size]
                print(f"🤖 Processing AI categorization batch {i//batch_size + 1}/{(len(products_data) + batch_size - 1)//batch_size}")
                
                try:
                    batch_categories = await ai_categorizer.categorize_products_batch(batch)
                    categories.extend(batch_categories)
                except Exception as e:
                    print(f"❌ Error in AI categorization batch: {e}")
                    # Fallback to keyword-based categorization for this batch
                    for data in batch:
                        fallback_category = ai_categorizer._fallback_categorize(
                            data.get('model', '') or data.get('product_name', '')
                        )
                        categories.append(fallback_category)
                
                # Small delay between batches
                await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"❌ Error in AI categorization: {e}")
            # Fallback to keyword-based categorization
            categories = []
            for data in products_data:
                fallback_category = ai_categorizer._fallback_categorize(
                    data.get('model', '') or data.get('product_name', '')
                )
                categories.append(fallback_category)
        
        # Ensure we have categories for all products
        while len(categories) < len(products_data):
            categories.append('accessories')  # Default fallback
        
        # Process each product with its category
        for i, data in enumerate(products_data):
            try:
                # Get category (with bounds checking)
                category = categories[i] if i < len(categories) else 'accessories'
                
                # Create images list (max 2 images)
                images = []
                
                # Use downloaded images if available
                if data.get('downloaded_images'):
                    for img_data in data['downloaded_images'][:self.max_images_per_product]:
                        if img_data and isinstance(img_data, dict):
                            images.append(ProductImage(
                                image_id=img_data.get('image_id', ''),
                                url=img_data.get('image_url', ''),
                                local_path=img_data.get('local_path'),
                                file_size=img_data.get('file_size')
                            ))
                elif data.get('images'):
                    for j, img_url in enumerate(data['images'][:self.max_images_per_product]):
                        image_id = f"{data.get('product_id', 'unknown')}_img_{j+1}"
                        images.append(ProductImage(
                            image_id=image_id,
                            url=img_url
                        ))
                
                product = Product(
                    product_id=data.get('product_id', ''),
                    brand=data['brand'],
                    model=data['model'],
                    sku=[data['sku']] if data.get('sku') else [],
                    product_name=data['product_name'],
                    source_url=[data['source_url']],
                    images=images,
                    category=category
                )
                
                products.append(product)
                
            except Exception as e:
                print(f"❌ Error converting product {i}: {e}")
                continue
        
        conversion_time = time.time() - conversion_start
        print(f"✅ Converted {len(products)} products in {conversion_time:.2f}s")
        return products
    
    def _get_safe_product_name(self, product) -> str:
        """Get a safe product name that won't cause NoneType errors."""
        if product.product_name:
            return product.product_name
        elif product.model and product.brand:
            return f"{product.brand} {product.model}"
        elif product.model:
            return product.model
        elif product.brand:
            return f"{product.brand} Product"
        else:
            return "Unknown Product"