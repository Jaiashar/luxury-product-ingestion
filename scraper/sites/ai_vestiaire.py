"""Optimized Vestiaire Collective scraper: Clean version with better duplicate detection."""

import random
import re
import json
import os
import asyncio
import hashlib
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from anthropic import Anthropic
from .base import BaseSiteScraper
from ..mappings.brand_urls import brand_mappings
from ..utils.data_models import Product, ProductImage
from ..utils.optimized_image_handler import OptimizedImageHandler
from ..utils.session_manager import session_manager

class AIVestiaireScraper(BaseSiteScraper):
    def __init__(self, scrapfly_client, rate_limit: float = 2.0, download_images: bool = True):
        super().__init__(scrapfly_client, rate_limit)
        
        # Site constants
        self.SITE_DOMAIN = "vestiairecollective.com"
        self.CDN_DOMAIN = "images.vestiairecollective.com"
        
        # Timing constants
        self.MIN_RENDERING_WAIT = 6000
        self.MAX_RENDERING_WAIT = 10000
        
        # Data limits
        self.MAX_MODEL_LENGTH = 25
        self.PRODUCT_ID_LENGTH = 16
        self.MAX_PAGES_DEFAULT = 30
        self.EMPTY_PAGE_TOLERANCE = 2
        self.MAX_CONCURRENT_CATEGORIES = 2
        
        # Initialize Anthropic client
        api_key = os.getenv('ANTHROPIC_API_KEY')
        self.anthropic = Anthropic(api_key=api_key) if api_key else None
        if not api_key:
            print("Warning: ANTHROPIC_API_KEY not found - will use pattern matching only")
        
        # Image settings
        self.download_images = download_images
        self.base_image_dir = "images"
        self.max_images_per_product = 2
        
        # Session management
        self.current_session = None
        self.session_request_count = 0
        
        print(f"✅ Image downloading {'enabled' if download_images else 'disabled'} (max 2 per product)")
        print(f"⏱️  Rate limit set to {rate_limit}s between requests")
        
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
        if '/women-' in url_lower:
            return 'women'
        elif '/men-' in url_lower:
            return 'men'
        else:
            return 'unisex'

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

    def _normalize_product_url(self, url: str) -> str:
        """Normalize product URL for better duplicate detection."""
        if not url:
            return ""
        
        # Remove query parameters and fragments
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # Remove trailing slash
        if normalized.endswith('/') and not normalized.endswith('.shtml'):
            normalized = normalized[:-1]
        
        return normalized
    
    def get_site_name(self) -> str:
        return "vestiaire"
    
    def get_brand_search_urls(self, brand: str) -> List[str]:
        """Get brand URLs from mappings."""
        urls = []
        
        # Try to find brand mapping
        mapping = brand_mappings.find_brand_mapping("vestiaire", brand)
        
        if mapping and mapping.active:
            print(f"📌 Found mapping: {mapping.brand_name}")
            
            # Handle both single URL and list of URLs
            if isinstance(mapping.url, list):
                urls.extend(mapping.url)
                print(f"   📋 Added {len(mapping.url)} URLs")
            else:
                urls.append(mapping.url)
                print(f"   📋 Added 1 URL")
        
        # Fallback URLs if no mappings found
        if not urls:
            brand_formatted = brand.lower().replace(' ', '-').replace('&', '-')
            fallback_urls = [
                f"https://www.{self.SITE_DOMAIN}/{brand_formatted}/",
                f"https://www.{self.SITE_DOMAIN}/women-{brand_formatted}/",
                f"https://www.{self.SITE_DOMAIN}/men-{brand_formatted}/"
            ]
            print(f"⚠️  No mappings found for {brand}, using fallback URLs")
            urls.extend(fallback_urls)
        
        print(f"🎯 Total URLs to scrape: {len(urls)}")
        return urls
    
    def get_supported_brands(self) -> List[str]:
        return brand_mappings.get_supported_brands("vestiaire")
    
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
        start_datetime = datetime.now()
        
        print(f"\n🚀 Optimized scraping for {brand} on Vestiaire Collective")
        print(f"⏰ Started at: {start_datetime.strftime('%H:%M:%S')}")
        if max_products:
            print(f"🎯 Limited to {max_products} products")
        else:
            print(f"🎯 Scraping ALL available products")
        
        try:
            # Step 1: Get category URLs
            category_urls = self.get_brand_search_urls(brand)
            all_products_data = []
            
            # Step 2: Process categories concurrently for speed
            all_products_data = await self._process_categories_concurrent(
                category_urls, brand, max_products
            )
            
            if not all_products_data:
                print(f"❌ No products found for {brand}")
                return []
            
            print(f"\n🎯 Found {len(all_products_data)} products total")
            
            # Apply max_products limit with image prioritization
            if max_products:
                products_with_images = [p for p in all_products_data if p.get('images')]
                products_without_images = [p for p in all_products_data if not p.get('images')]
                
                print(f"📸 Products with images: {len(products_with_images)}")
                print(f"📭 Products without images: {len(products_without_images)}")
                
                if len(products_with_images) >= max_products:
                    all_products_data = products_with_images[:max_products]
                    print(f"✅ Selected {max_products} products with images")
                else:
                    needed = max_products - len(products_with_images)
                    all_products_data = products_with_images + products_without_images[:needed]
                    print(f"✅ Selected {len(products_with_images)} with images + {needed} without images")
            
            # Step 3: Download images if enabled
            if self.download_images and all_products_data:
                print(f"📸 Downloading images for {len(all_products_data)} products...")
                all_products_data = await self._download_images_for_products(all_products_data, brand)
            
            # Step 4: Convert to Product objects with BATCHED AI categorization
            products = await self._convert_to_product_objects(all_products_data)
            
            # Final session stats
            final_stats = self.get_scraping_stats()
            print(f"\n📊 FINAL SESSION STATS:")
            print(f"🔄 Total requests: {final_stats['session_requests']}")
            print(f"❌ Total errors: {final_stats['error_counts']['total_errors']}")
            
            print(f"✅ Successfully created {len(products)} products!")
            
            # Timing summary
            total_time = time.time() - self.start_time
            end_datetime = datetime.now()
            
            print(f"\n⏰ TIMING SUMMARY:")
            print(f"🕐 Started: {start_datetime.strftime('%H:%M:%S')}")
            print(f"🕐 Ended: {end_datetime.strftime('%H:%M:%S')}")
            print(f"⏱️  Total Time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
            if len(products) > 0:
                print(f"📊 Products per minute: {(len(products) / (total_time/60)):.1f}")
                print(f"⚡ Seconds per product: {(total_time / len(products)):.1f}s")
            
            return products
            
        except Exception as e:
            print(f"❌ Error scraping {brand}: {e}")
            import traceback
            print(f"🔍 Full traceback: {traceback.format_exc()}")
            return []
    
    async def _process_categories_concurrent(self, category_urls: List[str], brand: str, max_products: int = None) -> List[Dict[str, Any]]:
        """Process category URLs concurrently for improved speed."""
        if len(category_urls) <= 1:
            # Single category - use sequential logic
            all_products_data = []
            for i, category_url in enumerate(category_urls, 1):
                category_start = time.time()
                
                print(f"\n📄 Processing category {i}/{len(category_urls)}: {category_url}")
                
                products_data = await self._extract_urls_and_product_info(
                    category_url, brand, thread_operation=None, first_page_only=bool(max_products)
                )
                
                all_products_data.extend(products_data)
                
                category_time = time.time() - category_start
                category_name = f"Category_{i}"
                self.category_times[category_name] = category_time
                
            return all_products_data
        
        # Multiple categories - process concurrently with ISOLATED sessions
        print(f"\n🚀 Processing {len(category_urls)} categories concurrently...")

        async def process_single_category(category_url: str, index: int) -> List[Dict[str, Any]]:
            """Process a single category URL with its OWN session manager instance."""
            try:
                category_start = time.time()
                
                # Add small random delay to prevent timing conflicts
                delay = random.uniform(0.5, 2.0) * index
                await asyncio.sleep(delay)
                
                # CREATE A SEPARATE SCRAPER INSTANCE FOR THIS THREAD
                thread_scraper = AIVestiaireScraper(
                    self.client, 
                    rate_limit=self.rate_limit,
                    download_images=False
                )
                
                thread_operation = f"concurrent_category_{index}_{int(time.time())}_{random.randint(1000,9999)}"
                
                products_data = await thread_scraper._extract_urls_and_product_info(
                    category_url, brand, thread_operation=thread_operation, first_page_only=bool(max_products)
                )
                
                category_time = time.time() - category_start
                category_name = f"Thread_{index+1}"
                self.category_times[category_name] = category_time
                
                return products_data
                
            except Exception as e:
                print(f"❌ [Thread {index+1}] Error processing {category_url}: {e}")
                return []
        
        # Create tasks for concurrent processing
        max_concurrent = min(len(category_urls), self.MAX_CONCURRENT_CATEGORIES)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def controlled_process(category_url: str, index: int):
            async with semaphore:
                return await process_single_category(category_url, index)
        
        # Execute all categories concurrently
        tasks = [
            controlled_process(category_url, i) 
            for i, category_url in enumerate(category_urls)
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Collect successful results
            all_products_data = []
            successful_categories = 0
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"❌ Category {i+1} failed: {result}")
                elif isinstance(result, list):
                    all_products_data.extend(result)
                    successful_categories += 1
                else:
                    print(f"⚠️  Category {i+1} returned unexpected result type")
            
            print(f"\n📊 Concurrent processing complete: {successful_categories}/{len(category_urls)} categories successful")
            return all_products_data
            
        except Exception as e:
            print(f"❌ Concurrent processing failed, falling back to sequential: {e}")
            
            # Fallback to sequential processing
            all_products_data = []
            for i, category_url in enumerate(category_urls, 1):
                category_start = time.time()
                
                try:
                    products_data = await self._extract_urls_and_product_info(
                        category_url, brand, thread_operation=None, first_page_only=bool(max_products)
                    )
                    
                    all_products_data.extend(products_data)
                    
                    category_time = time.time() - category_start
                    category_name = f"Fallback_Category_{i}"
                    self.category_times[category_name] = category_time
                    
                except Exception as fallback_error:
                    print(f"❌ [Fallback] Category {i} also failed: {fallback_error}")
                    continue
            
            return all_products_data
    
    async def _extract_urls_and_product_info(self, page_url: str, brand: str, 
                                           thread_operation: str = None, 
                                           first_page_only: bool = False) -> List[Dict[str, Any]]:
        """Extract URLs and product info - handles both sequential and concurrent contexts."""
        all_products_data = []
        all_seen_urls = set()
        page_num = 1
        max_pages = 1 if first_page_only else self.MAX_PAGES_DEFAULT
        consecutive_empty_pages = 0
        
        while page_num <= max_pages and consecutive_empty_pages < self.EMPTY_PAGE_TOLERANCE:
            try:
                # Construct paginated URL for Vestiaire
                if page_num == 1:
                    paginated_url = page_url
                else:
                    if '?' in page_url:
                        paginated_url = f"{page_url}&page={page_num}"
                    else:
                        paginated_url = f"{page_url}?page={page_num}"
                
                operation = f"{thread_operation}_page_{page_num}" if thread_operation else f"page_{page_num}"
                
                result = await self.make_request_with_session(
                    url=paginated_url,
                    brand=brand,
                    operation=operation,
                    render_js=True,
                    rendering_wait=random.randint(self.MIN_RENDERING_WAIT, self.MAX_RENDERING_WAIT),
                    auto_scroll=True,
                )
                
                if not result or result.status_code != 200:
                    consecutive_empty_pages += 1
                    page_num += 1
                    continue

                gender = self._detect_gender_from_url(page_url)
                page_products_data = await self._extract_products_with_urls_and_info(
                    result.content, paginated_url, brand, gender
                )
                
                if not page_products_data:
                    consecutive_empty_pages += 1
                    page_num += 1
                    if first_page_only:
                        break
                    continue
                
                # Better duplicate detection for multi-page scraping
                if not first_page_only and page_num > 1:
                    current_page_urls = [
                        self._normalize_product_url(product.get('source_url', '')) 
                        for product in page_products_data if product.get('source_url')
                    ]
                    
                    new_product_urls = [url for url in current_page_urls if url not in all_seen_urls]
                    
                    if len(new_product_urls) == 0:
                        print(f"    🛑 STOPPING: Found 0 new products on page {page_num}")
                        break
                    
                    new_products_data = []
                    for product in page_products_data:
                        product_url = self._normalize_product_url(product.get('source_url', ''))
                        if product_url in new_product_urls:
                            new_products_data.append(product)
                    
                    all_products_data.extend(new_products_data)
                    all_seen_urls.update(new_product_urls)
                    
                else:
                    all_products_data.extend(page_products_data)
                    
                    current_page_urls = [
                        self._normalize_product_url(product.get('source_url', '')) 
                        for product in page_products_data if product.get('source_url')
                    ]
                    all_seen_urls.update(current_page_urls)
                
                consecutive_empty_pages = 0
                
                if first_page_only:
                    break
                    
                page_num += 1
                
            except Exception as e:
                print(f"    ❌ Error fetching page {page_num}: {e}")
                consecutive_empty_pages += 1
                page_num += 1
                if consecutive_empty_pages >= 2:
                    break
        
        return all_products_data
    
    async def _extract_products_with_urls_and_info(self, html: str, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """Extract product info using BOTH robust URL extraction and lightweight info extraction."""
        try:
            # Step 1: Use robust URL extraction to find ALL product URLs
            product_urls = await self._extract_product_urls_robust(html)
            
            # Step 2: Use lightweight method to extract product info from containers
            soup = BeautifulSoup(html, 'html.parser')
            product_containers_info = await self._extract_product_containers_info(soup, page_url, brand, gender)
            
            # Step 3: Match URLs to containers to create complete product data
            matched_products = await self._match_urls_to_containers(product_urls, product_containers_info, page_url, brand, gender)
            
            return matched_products
            
        except Exception as e:
            print(f"    ❌ Error extracting products: {e}")
            return []
    
    async def _extract_product_urls_robust(self, html: str) -> List[str]:
        """Enhanced URL extraction with better duplicate detection."""
        urls = set()
        
        # Primary approach: BeautifulSoup extraction
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Strategy 1: Direct product links
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                if '.shtml' in href:
                    if href.startswith('/'):
                        href = f"https://www.{self.SITE_DOMAIN}{href}"
                    elif not href.startswith('http'):
                        href = f"https://www.{self.SITE_DOMAIN}/{href}"
                    
                    normalized_href = self._normalize_product_url(href)
                    if self._is_valid_product_url(normalized_href):
                        urls.add(normalized_href)
            
            # Strategy 2: Data attributes
            all_elements = soup.find_all(attrs=True)
            for element in all_elements:
                for attr, value in element.attrs.items():
                    if isinstance(value, str) and '.shtml' in value:
                        if value.startswith('/'):
                            value = f"https://www.{self.SITE_DOMAIN}{value}"
                        elif not value.startswith('http') and value.endswith('.shtml'):
                            value = f"https://www.{self.SITE_DOMAIN}/{value}"
                        
                        normalized_value = self._normalize_product_url(value)
                        if self._is_valid_product_url(normalized_value):
                            urls.add(normalized_value)
            
            # Strategy 3: JSON data
            script_tags = soup.find_all('script', type='application/json')
            for script in script_tags:
                try:
                    script_text = script.get_text()
                    if '.shtml' in script_text:
                        json_url_matches = re.findall(r'"[^"]*\.shtml[^"]*"', script_text)
                        for match in json_url_matches:
                            url = match.strip('"')
                            if url.startswith('/'):
                                url = f"https://www.{self.SITE_DOMAIN}{url}"
                            
                            normalized_url = self._normalize_product_url(url)
                            if self._is_valid_product_url(normalized_url):
                                urls.add(normalized_url)
                except:
                    continue
            
        except Exception as e:
            print(f"    ❌ BeautifulSoup URL extraction failed: {e}")
        
        return list(urls)
    
    async def _extract_product_containers_info(self, soup: BeautifulSoup, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """Extract product containers with better quality filtering."""
        product_containers = []
        seen_skus = set()  # Track by SKU to avoid duplicates
        
        # Find all product links and get their containers
        all_product_links = soup.find_all('a', href=lambda x: x and '.shtml' in x)
        
        for link in all_product_links:
            # Extract SKU from link to check for duplicates
            href = link.get('href', '')
            sku = self._extract_sku_from_url(href)
            
            if sku and sku in seen_skus:
                continue  # Skip duplicate SKUs
            
            # Check immediate parent containers
            for parent_level in range(1, 3):
                current = link
                for _ in range(parent_level):
                    current = current.parent
                    if not current:
                        break
                
                if current and current.name in ['div', 'article', 'li']:
                    # Quality check: should be a single product container
                    product_links_in_container = current.find_all('a', href=lambda x: x and '.shtml' in x)
                    images_in_container = current.find_all('img')
                    container_text = current.get_text(strip=True)
                    
                    # Good product container criteria
                    if (1 <= len(product_links_in_container) <= 3 and 
                        1 <= len(images_in_container) <= 5 and
                        50 <= len(container_text) <= 500):
                        
                        product_containers.append(current)
                        if sku:
                            seen_skus.add(sku)
                        break
        
        # If we don't have enough containers, try specific selectors
        if len(product_containers) < 30:
            specific_selectors = [
                '[data-testid="product-card"]',
                '.product-card:not(.category-banner)',
                '.item-card',
                '.listing-item'
            ]
            
            for selector in specific_selectors:
                containers = soup.select(selector)
                for container in containers:
                    # Check for duplicates by SKU
                    product_links = container.find_all('a', href=lambda x: x and '.shtml' in x)
                    if product_links:
                        href = product_links[0].get('href', '')
                        sku = self._extract_sku_from_url(href)
                        
                        if sku and sku not in seen_skus:
                            product_containers.append(container)
                            seen_skus.add(sku)
                
                if len(product_containers) >= 60:  # Stop at reasonable limit
                    break
        
        # Extract info from each container
        containers_info = []
        for container in product_containers:
            try:
                container_info = self._extract_info_from_container(container, page_url, brand, gender)
                if container_info:
                    containers_info.append(container_info)
            except Exception as e:
                continue
        
        return containers_info
    
    def _extract_info_from_container(self, container, page_url: str, brand: str, gender: str) -> Optional[Dict[str, Any]]:
        """Extract product info from container."""
        try:
            # Extract product URL
            link_elem = container.find('a', href=lambda x: x and '.shtml' in x)
            if not link_elem:
                return None
            
            container_url = link_elem['href']
            if not container_url.startswith('http'):
                if container_url.startswith('/'):
                    container_url = f"https://www.{self.SITE_DOMAIN}{container_url}"
                else:
                    container_url = f"https://www.{self.SITE_DOMAIN}/{container_url}"
            
            normalized_url = self._normalize_product_url(container_url)
            if not self._is_valid_product_url(normalized_url):
                return None
            
            # Extract title with multiple strategies
            full_title = self._extract_title_from_container(container, link_elem)
            if not full_title:
                return None
            
            # Parse model from title
            model = self._parse_model_from_title(full_title, brand)
            
            # Extract price
            price = self._extract_price_from_container(container)
            
            # Create product name with gender
            if gender != 'unisex':
                product_name = f"{brand} {model} {gender}"
            else:
                product_name = f"{brand} {model}"
            
            # Extract images
            images = self._extract_images_from_container(container)
            
            # Extract SKU from URL
            sku = self._extract_sku_from_url(normalized_url)
            
            # Generate product ID
            product_id = self._generate_product_id(brand, model, sku)
            
            return {
                'container_url': normalized_url,
                'product_id': product_id,
                'brand': brand,
                'model': model,
                'sku': sku,
                'price': price,
                'product_name': product_name,
                'description': '',
                'images': images,
                'source_url': normalized_url
            }
            
        except Exception as e:
            return None

    def _extract_title_from_container(self, container, link_elem) -> Optional[str]:
        """Extract title from container using multiple strategies."""
        # Strategy 1: Vestiaire-specific selectors
        vestiaire_title_selectors = [
            '.product-card__title',
            '.product-card__name',
            '.product-title',
            '.item-title',
            '.card-title',
            '[data-testid*="title"]',
            '[data-testid*="name"]'
        ]
        
        for selector in vestiaire_title_selectors:
            title_elem = container.select_one(selector)
            if title_elem:
                full_title = title_elem.get_text(strip=True)
                if full_title and len(full_title) > 5:
                    return full_title
        
        # Strategy 2: Generic selectors
        for selector in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            title_elem = container.find(selector)
            if title_elem:
                full_title = title_elem.get_text(strip=True)
                if full_title and len(full_title) > 5:
                    return full_title
        
        # Strategy 3: Title-like classes
        title_patterns = [
            lambda x: x and 'title' in x.lower(),
            lambda x: x and 'name' in x.lower(),
            lambda x: x and 'product' in x.lower()
        ]
        
        for pattern in title_patterns:
            elements = container.find_all(['div', 'span', 'p'], class_=pattern)
            for elem in elements:
                text = elem.get_text(strip=True)
                if text and 5 < len(text) < 200:
                    return text
        
        # Strategy 4: Link text
        link_text = link_elem.get_text(strip=True)
        if link_text and len(link_text) > 5:
            return link_text
        
        # Strategy 5: Image alt text
        images = container.find_all('img')
        for img in images:
            alt_text = img.get('alt', '')
            if alt_text and 5 < len(alt_text) < 200:
                return alt_text
        
        return None

    async def _match_urls_to_containers(self, product_urls: List[str], 
                                    containers_info: List[Dict[str, Any]], 
                                    page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """Match URLs to containers, avoiding duplicates."""
        matched_products = []
        seen_skus = set()
        
        # Create lookup for container info by normalized URL
        container_lookup = {}
        for container_info in containers_info:
            container_url = container_info.get('container_url', '')
            if container_url:
                normalized_url = self._normalize_product_url(container_url)
                container_lookup[normalized_url] = container_info
        
        # Match each URL to container info
        for product_url in product_urls:
            normalized_url = self._normalize_product_url(product_url)
            
            # Check for duplicates by SKU
            sku = self._extract_sku_from_url(normalized_url)
            if sku and sku in seen_skus:
                continue
            
            if normalized_url in container_lookup:
                # Perfect match - use container info
                container_info = container_lookup[normalized_url].copy()
                container_info['source_url'] = normalized_url
                del container_info['container_url']
                matched_products.append(container_info)
                
                if sku:
                    seen_skus.add(sku)
            else:
                # No container match - create minimal product
                minimal_product = await self._create_minimal_product_from_url(
                    normalized_url, page_url, brand, gender
                )
                if minimal_product:
                    minimal_sku = minimal_product.get('sku')
                    if minimal_sku and minimal_sku not in seen_skus:
                        matched_products.append(minimal_product)
                        seen_skus.add(minimal_sku)
        
        return matched_products
    
    async def _create_minimal_product_from_url(self, product_url: str, page_url: str, brand: str, gender: str) -> Dict[str, Any]:
        """Create minimal product data when no container info is available."""
        try:
            # Extract SKU from URL
            sku = self._extract_sku_from_url(product_url)
            
            # Try to extract product name from URL
            name_match = re.search(r'/([^/]+)-\d+\.shtml', product_url)
            if name_match:
                product_name = name_match.group(1).replace('-', ' ').title()
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
                'price': None,
                'product_name': product_name,
                'description': '',
                'images': []
            }
            
        except Exception as e:
            return None

    def _parse_brand_and_model(self, full_title: str) -> Tuple[str, str]:
        """Parse brand and model from full product title."""
        brands = [
            'Gucci', 'Louis Vuitton', 'Chanel', 'Hermès', 'Hermes', 'Prada', 'Dior', 
            'Versace', 'Balenciaga', 'Saint Laurent', 'Bottega Veneta',
            'Burberry', 'Valentino', 'Givenchy', 'Fendi', 'Celine',
            'Tom Ford', 'Alexander McQueen', 'Stella McCartney', 'Off-White',
            'Golden Goose', 'Maison Margiela', 'Thom Browne', 'Jacquemus',
            'Isabel Marant', 'Ganni', 'Acne Studios', 'Stone Island'
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
    
    def _extract_price_from_container(self, container) -> Optional[int]:
        """Extract price from container."""
        price_selectors = [
            '[data-testid*="price"]',
            '.price',
            '[class*="price"]',
            '[class*="Price"]'
        ]
        
        for selector in price_selectors:
            price_elem = container.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'[\d,]+', price_text.replace(',', '').replace('.', ''))
                if price_match:
                    try:
                        return int(price_match.group().replace(',', ''))
                    except ValueError:
                        continue
        
        return None
    
    def _extract_images_from_container(self, container) -> List[str]:
        """Extract images from container."""
        images = []
        
        img_elements = container.find_all('img')
        
        for img in img_elements:
            src_attrs = [
                'src',
                'data-src',
                'data-srcset',
                'data-lazy-src',
                'data-original',
                'srcset'
            ]
            
            img_found = False
            for attr in src_attrs:
                src = img.get(attr)
                if src and not img_found:
                    if attr in ['data-srcset', 'srcset']:
                        # Handle srcset format
                        urls = []
                        for url_desc in str(src).split(','):
                            url_part = url_desc.strip().split(' ')[0]
                            if url_part:
                                urls.append(url_part)
                        
                        if urls:
                            best_url = urls[-1]
                            if self._is_valid_product_image(best_url):
                                enhanced_url = self._enhance_image_url(best_url)
                                if enhanced_url not in images:
                                    images.append(enhanced_url)
                                    img_found = True
                    else:
                        # Regular src attribute
                        if self._is_valid_product_image(src):
                            enhanced_url = self._enhance_image_url(src)
                            if enhanced_url not in images:
                                images.append(enhanced_url)
                                img_found = True
        
        return images[:self.max_images_per_product]
    
    def _enhance_image_url(self, img_url: str) -> str:
        """Optimize image URL for Vestiaire CDN."""
        if not img_url:
            return img_url
            
        # Handle protocol-relative URLs
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = f'https://www.{self.SITE_DOMAIN}{img_url}'
        
        # Don't modify if it's not a Vestiaire image
        if 'vestiairecollective.com' not in img_url:
            return img_url
        
        # Optimize Vestiaire image URLs
        if 'images.vestiairecollective.com' in img_url:
            if '/resized/' in img_url:
                # Update existing parameters
                if 'w=' not in img_url:
                    img_url = img_url.replace('/resized/', '/resized/w=800,q=85,f=auto,')
                else:
                    img_url = re.sub(r'w=\d+', 'w=800', img_url)
                    if 'q=' not in img_url:
                        img_url = re.sub(r'(w=\d+)', r'\1,q=85', img_url)
            else:
                # Add resized parameters
                if '/images/produit/' in img_url:
                    img_url = img_url.replace('/images/produit/', '/images/resized/w=800,q=85,f=auto,/produit/')
                elif '/produit/' in img_url:
                    img_url = img_url.replace('/produit/', '/resized/w=800,q=85,f=auto,/produit/')
        
        return img_url
    
    def _extract_sku_from_url(self, url: str) -> Optional[str]:
        """Extract SKU from product URL."""
        sku_match = re.search(r'-(\d+)\.shtml', url)
        return sku_match.group(1) if sku_match else None
    
    def _is_valid_product_image(self, img_url: str) -> bool:
        """Check if image URL is valid for Vestiaire products."""
        if not img_url or not isinstance(img_url, str):
            return False
        
        img_url_lower = img_url.lower()
        
        # Check valid domains
        valid_domains = [
            'images.vestiairecollective.com',
            'vestiairecollective.com',
            'cdn.vestiairecollective.com',
            'static.vestiairecollective.com'
        ]
        
        is_valid_domain = any(domain in img_url_lower for domain in valid_domains)
        is_relative_vestiaire = (img_url.startswith('/') and 
                               ('/produit/' in img_url_lower or '/images/' in img_url_lower))
        
        if not is_valid_domain and not is_relative_vestiaire:
            return False
        
        # Check for image extension or product path
        has_image_ext = any(ext in img_url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp'])
        has_product_path = any(path in img_url_lower for path in ['/produit/', '/images/', '/resized/'])
        
        if not has_image_ext and not has_product_path:
            return False
        
        # Skip non-product patterns
        skip_patterns = [
            'logo', 'icon', 'banner', 'promo', 'ad_',
            'favicon', 'placeholder', 'sprite', 'background',
            'avatar', 'profile'
        ]
        
        if any(pattern in img_url_lower for pattern in skip_patterns):
            return False
        
        return True
    
    def _is_valid_product_url(self, url: str) -> bool:
        """Check if URL is a valid product page."""
        return bool(url and self.SITE_DOMAIN in url and url.endswith('.shtml'))
    
    async def _download_images_for_products(self, products_data: List[Dict[str, Any]], brand: str) -> List[Dict[str, Any]]:
        """Download images for all products."""
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
                    products_for_download, batch_size=50
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
        """Convert scraped data to Product objects with batched AI categorization."""
        from ..utils.ai_categorizer import ai_categorizer
        
        conversion_start = time.time()
        
        products = []
        
        print(f"🤖 Running batched AI categorization for {len(products_data)} products...")
        
        try:
            categories = await ai_categorizer.categorize_products_batch(products_data)
        except Exception as e:
            print(f"⚠️  Batched AI categorization failed: {e}, using fallback")
            categories = []
            for data in products_data:
                fallback_category = ai_categorizer._fallback_categorize(
                    data.get('model', '') or data.get('product_name', '')
                )
                categories.append(fallback_category)
        
        # Ensure we have categories for all products
        while len(categories) < len(products_data):
            categories.append('accessories')
        
        # Process each product with its category
        for i, data in enumerate(products_data):
            try:
                category = categories[i] if i < len(categories) else 'accessories'
                
                # Create images list
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
                print(f"⚠️  Error creating Product object: {e}")
                continue
        
        conversion_time = time.time() - conversion_start
        print(f"✅ Successfully categorized and created {len(products)} products!")
        print(f"⏱️  Product conversion took {conversion_time:.1f}s")
        return products