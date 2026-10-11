"""Optimized Fashionphile scraper: Following the same pattern as Farfetch scraper."""

import random
import re
import json
import os
import asyncio
import hashlib
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from anthropic import Anthropic
from .base import BaseSiteScraper
from ..mappings.brand_urls import brand_mappings
from ..utils.data_models import Product, ProductImage
from ..utils.optimized_image_handler import OptimizedImageHandler
from ..utils.session_manager import session_manager

class AIFashionphileScraper(BaseSiteScraper):
    def __init__(self, scrapfly_client, rate_limit: float = 3.0, download_images: bool = True):
        super().__init__(scrapfly_client, rate_limit)
        
        # Site constants
        self.SITE_DOMAIN = "fashionphile.com"
        self.CDN_DOMAIN = "fashionphile.imgix.net"
        
        # Timing constants
        self.MIN_RENDERING_WAIT = 4000
        self.MAX_RENDERING_WAIT = 7000
        
        # Data limits
        self.MAX_MODEL_LENGTH = 20
        self.PRODUCT_ID_LENGTH = 16
        self.MAX_PAGES_DEFAULT = 30
        self.EMPTY_PAGE_TOLERANCE = 2
        self.MAX_CONCURRENT_CATEGORIES = 3
        
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
        """Detect gender from URL. Fashionphile doesn't separate by gender, so default to 'unisex'."""
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
    
    def get_site_name(self) -> str:
        return "fashionphile"
    
    def get_brand_search_urls(self, brand: str) -> List[str]:
        """Get brand URLs from mappings."""
        urls = []
        
        # Try to find brand mapping
        mapping = brand_mappings.find_brand_mapping("fashionphile", brand)
        
        if mapping and mapping.active:
            print(f"📌 Found mapping: {mapping.brand_name}")
            
            # Handle both single URL and list of URLs
            if isinstance(mapping.url, list):
                urls.extend(mapping.url)
                print(f"   📋 Added {len(mapping.url)} URLs")
            else:
                urls.append(mapping.url)
                print(f"   📋 Added 1 URL")
        
        # Fallback URL if no mappings found
        if not urls:
            brand_formatted = brand.lower().replace(' ', '-').replace('&', 'and')
            fallback_url = f"https://www.{self.SITE_DOMAIN}/shop/brands/{brand_formatted}"
            print(f"⚠️  No mappings found for {brand}, using fallback URL")
            urls.append(fallback_url)
        
        print(f"🎯 Total URLs to scrape: {len(urls)}")
        return urls
    
    def get_supported_brands(self) -> List[str]:
        return brand_mappings.get_supported_brands("fashionphile")
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """Get scraping statistics."""
        try:
            session_stats = session_manager.get_session_stats()
        except:
            session_stats = {}
        
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
        # START TIMING
        self.start_time = time.time()
        start_datetime = datetime.now()
        
        if max_products:
            print(f"🎯 Limited to {max_products} products")
            print(f"🧪 Development mode: Only scraping first page")
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
            print(f"🛡️  Session errors: {final_stats['error_counts']['session_errors']}")
            print(f"⏱️  Timeout errors: {final_stats['error_counts']['timeout_errors']}")
            print(f"🛡️  ASP errors: {final_stats['error_counts']['asp_errors']}")
            
            print(f"✅ Successfully created {len(products)} products!")
            
            # ADD TIMING SUMMARY HERE
            total_time = time.time() - self.start_time
            end_datetime = datetime.now()
            
            print(f"\n⏰ TIMING SUMMARY:")
            print(f"🕐 Started: {start_datetime.strftime('%H:%M:%S')}")
            print(f"🕐 Ended: {end_datetime.strftime('%H:%M:%S')}")
            print(f"⏱️  Total Time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
            if len(products) > 0:
                print(f"📊 Products per minute: {(len(products) / (total_time/60)):.1f}")
                print(f"⚡ Seconds per product: {(total_time / len(products)):.1f}s")
            
            # Category timing breakdown
            if self.category_times:
                print(f"📋 Category breakdown:")
                for category, cat_time in self.category_times.items():
                    print(f"   {category}: {cat_time:.1f}s")
            
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
                print(f"   ⏱️  Category {i} completed in {category_time:.1f}s ({len(products_data)} products)")
            
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
                
                print(f"\n📄 [Thread {index+1}] Starting: {category_url}")
                
                # CREATE A SEPARATE SCRAPER INSTANCE FOR THIS THREAD
                thread_scraper = AIFashionphileScraper(
                    self.client, 
                    rate_limit=self.rate_limit,
                    download_images=False  # Don't download images in concurrent phase
                )
                
                # Create unique thread operation identifier
                thread_operation = f"concurrent_category_{index}_{int(time.time())}_{random.randint(1000,9999)}"
                
                print(f"🔧 [Thread {index+1}] Created isolated scraper instance")
                
                products_data = await thread_scraper._extract_urls_and_product_info(
                    category_url, brand, thread_operation=thread_operation, first_page_only=bool(max_products)
                )
                
                category_time = time.time() - category_start
                category_name = f"Thread_{index+1}"
                self.category_times[category_name] = category_time
                
                print(f"✅ [Thread {index+1}] Completed: {len(products_data)} products in {category_time:.1f}s")
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
                
                print(f"\n📄 [Fallback] Processing category {i}/{len(category_urls)}: {category_url}")
                
                try:
                    products_data = await self._extract_urls_and_product_info(
                        category_url, brand, thread_operation=None, first_page_only=bool(max_products)
                    )
                    
                    all_products_data.extend(products_data)
                    
                    category_time = time.time() - category_start
                    category_name = f"Fallback_Category_{i}"
                    self.category_times[category_name] = category_time
                    print(f"   ⏱️  [Fallback] Category {i} completed in {category_time:.1f}s ({len(products_data)} products)")
                    
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
                # Construct paginated URL
                if page_num == 1:
                    paginated_url = page_url
                else:
                    separator = '&' if '?' in page_url else '?'
                    paginated_url = f"{page_url}{separator}page={page_num}"
                
                page_label = "first page" if first_page_only else f"page {page_num}"
                
                # Use thread_operation if provided, otherwise default operation
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
                    print(f"    ❌ {page_label} failed: {result.status_code if result else 'No response'}")
                    consecutive_empty_pages += 1
                    page_num += 1
                    continue

                gender = self._detect_gender_from_url(page_url)
                page_products_data = await self._extract_products_with_urls_and_info(
                    result.content, paginated_url, brand, gender
                )
                
                if not page_products_data:
                    print(f"    📄 No products found on {page_label}")
                    consecutive_empty_pages += 1
                    page_num += 1
                    if first_page_only:
                        break
                    continue
                
                # Duplicate detection logic for multi-page scraping
                if not first_page_only and page_num > 1:
                    current_page_urls = [
                        product.get('source_url', '') for product in page_products_data 
                        if product.get('source_url')
                    ]
                    
                    new_product_urls = [url for url in current_page_urls if url not in all_seen_urls]
                                        
                    if len(new_product_urls) == 0:
                        print(f"    🛑 STOPPING: Found 0 new products on {page_label} - reached end of unique products")
                        break
                    
                    new_products_data = []
                    for product in page_products_data:
                        product_url = product.get('source_url', '')
                        if product_url in new_product_urls:
                            new_products_data.append(product)
                                        
                    all_products_data.extend(new_products_data)
                    all_seen_urls.update(new_product_urls)
                    
                else:
                    all_products_data.extend(page_products_data)
                    
                    current_page_urls = [
                        product.get('source_url', '') for product in page_products_data 
                        if product.get('source_url')
                    ]
                    all_seen_urls.update(current_page_urls)
                
                consecutive_empty_pages = 0
                
                if first_page_only:
                    break
                    
                page_num += 1
                
            except Exception as e:
                print(f"    ❌ Error fetching {page_label}: {e}")
                consecutive_empty_pages += 1
                page_num += 1
                if consecutive_empty_pages >= 2:
                    break
        
        print(f"    📊 Total NEW products extracted: {len(all_products_data)} (across {page_num-1} pages)")
        print(f"    🔗 Total unique URLs tracked: {len(all_seen_urls)}")
        return all_products_data
    
    async def _extract_products_with_urls_and_info(self, html: str, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """
        Extract product info using BOTH robust URL extraction and lightweight info extraction.
        This combines the best of both approaches:
        1. Find ALL product URLs using the robust regex method
        2. Extract product info from containers on the same page (lightweight)
        3. Match URLs to containers to get complete product data
        """
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
            print(f"    ❌ Error extracting products with URLs and info: {e}")
            return []
    
    async def _extract_product_urls_robust(self, html: str) -> List[str]:
        """Robust URL extraction method for Fashionphile."""
        urls = set()
        
        # Fashionphile product URL patterns
        patterns = [
            r'href=["\']([^"\']*\/p\/[^"\']*)["\']',
            r'https://[^"\s]*fashionphile\.com[^"\s]*\/p\/[^"\s]*',
            r'\/p\/([^"\'\/\s]+)',
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
                if '/p/' in url:
                    if not url.startswith('/'):
                        url = '/' + url
                    url = f"https://www.{self.SITE_DOMAIN}{url}"
                else:
                    continue
            
            url = url.replace('\\', '')
            
            # Remove query parameters for consistency
            if '?' in url:
                url = url.split('?')[0]
            
            if self._is_valid_product_url(url):
                urls.add(url)
        
        # BeautifulSoup approach for additional URLs
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            all_links = soup.find_all(['a', 'link'], href=True)
            for link in all_links:
                href = link.get('href', '')
                if '/p/' in href and href not in [u for u in urls]:
                    if href.startswith('/'):
                        href = f"https://www.{self.SITE_DOMAIN}{href}"
                    if self._is_valid_product_url(href):
                        urls.add(href)
            
            for element in soup.find_all(attrs=True):
                for attr, value in element.attrs.items():
                    if isinstance(value, str) and '/p/' in value and 'http' in value:
                        if self._is_valid_product_url(value):
                            urls.add(value)
            
        except Exception as e:
            print(f"    ❌ BeautifulSoup URL extraction failed: {e}")
        
        return list(urls)
    
    async def _extract_product_containers_info(self, soup: BeautifulSoup, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """Extract product info from containers using lightweight method."""
        # Find all product containers using multiple strategies
        product_containers = []
        
        # Strategy 1: Look for product cards or tiles
        containers = soup.find_all(['div', 'article'], class_=lambda x: x and ('product' in str(x).lower() or 'item' in str(x).lower() or 'card' in str(x).lower()))
        product_containers.extend(containers)
        
        # Strategy 2: Look for links with /p/ pattern and get parent containers
        if not product_containers:
            item_links = soup.find_all('a', href=lambda x: x and '/p/' in x)
            for link in item_links:
                container = link.find_parent(['div', 'li', 'article'])
                if container and container not in product_containers:
                    product_containers.append(container)
        
        # Strategy 3: Find containers with price information
        if not product_containers:
            price_elements = soup.find_all(text=re.compile(r'\$[\d,]+'))
            for price_elem in price_elements:
                container = price_elem.parent
                while container and container.name not in ['div', 'li', 'article']:
                    container = container.parent
                if container and container not in product_containers:
                    product_containers.append(container)
        
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
        """Extract product info from a single container."""
        try:
            # Extract product URL from container
            link_elem = container.find('a', href=True)
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
            
            # Extract product title/name from various possible elements
            title_elem = (
                container.find('h3') or
                container.find('h2') or
                container.find('h4') or
                container.find('div', class_=lambda x: x and 'title' in str(x).lower()) or
                container.find('span', class_=lambda x: x and 'title' in str(x).lower()) or
                link_elem
            )
            
            if not title_elem:
                return None
                
            full_title = title_elem.get_text(strip=True)
            if not full_title:
                return None
            
            # Parse model from title
            model = self._parse_model_from_title(full_title, brand)
            
            # Create product name
            product_name = f"{brand} {model}"
            
            # Extract images (limit to 2)
            images = self._extract_images_from_container(container)[:self.max_images_per_product]
            
            # Extract SKU from URL
            sku = self._extract_sku_from_url(container_url)
            
            # Generate product ID
            product_id = self._generate_product_id(brand, model, sku)
            
            return {
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
            
        except Exception as e:
            return None

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
            # Extract SKU from URL
            sku = self._extract_sku_from_url(product_url)
            
            # Try to extract product name from URL
            # Fashionphile URLs are like: /p/chanel-caviar-quilted-medium-sunset-on-the-sea-flap-beige-1667682
            url_parts = product_url.split('/p/')
            if len(url_parts) > 1:
                product_slug = url_parts[1].split('?')[0]  # Remove query params
                # Remove the SKU from the end
                if sku:
                    product_slug = product_slug.replace(f'-{sku}', '')
                
                # Convert slug to title
                product_name = product_slug.replace('-', ' ').title()
                brand_parsed, model = self._parse_brand_and_model(product_name)
            else:
                brand_parsed = brand
                model = "Unknown Product"
                product_name = f"{brand_parsed} {model}"

            # Generate product ID
            product_id = self._generate_product_id(brand_parsed, model, sku)
            
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
            print(f"    ⚠️  Error creating minimal product from URL: {e}")
            return None

    def _parse_brand_and_model(self, full_title: str) -> Tuple[str, str]:
        """Parse brand and model from full product title."""
        brands = [
            'Chanel', 'Louis Vuitton', 'Hermes', 'Hermès', 'Gucci', 'Prada', 'Dior', 
            'Versace', 'Balenciaga', 'Saint Laurent', 'Bottega Veneta',
            'Burberry', 'Valentino', 'Givenchy', 'Fendi', 'Celine',
            'Tom Ford', 'Alexander McQueen', 'Stella McCartney', 'Off-White',
            'Golden Goose', 'Maison Margiela', 'Thom Browne', 'Jacquemus',
            'Isabel Marant', 'Ganni', 'Acne Studios', 'Stone Island',
            'Coach', 'Marc Jacobs', 'Michael Kors', 'Kate Spade'
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
    
    def _extract_images_from_container(self, container) -> List[str]:
        """Extract and filter product images from container."""
        images = []
        
        # Find img tags
        img_elements = container.find_all('img')
        for img in img_elements:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original') or img.get('data-lazy') or img.get('data-image-src')
            if src and self._is_valid_product_image(src):
                src = self._enhance_image_url(src)
                if src not in images:
                    images.append(src)
        
        # Look for picture/source elements
        picture_elements = container.find_all('picture')
        for picture in picture_elements:
            sources = picture.find_all('source')
            for source in sources:
                srcset = source.get('srcset')
                if srcset:
                    urls = [url.strip().split(' ')[0] for url in srcset.split(',')]
                    for url in urls:
                        if self._is_valid_product_image(url):
                            url = self._enhance_image_url(url)
                            if url not in images:
                                images.append(url)
        
        # Look in data attributes
        for attr in ['data-image-url', 'data-src', 'data-original', 'data-lazy-src']:
            if container.get(attr):
                img_url = container[attr]
                if self._is_valid_product_image(img_url):
                    img_url = self._enhance_image_url(img_url)
                    if img_url not in images:
                        images.append(img_url)

        return images
    
    def _enhance_image_url(self, img_url: str) -> str:
        """Convert image URL to highest quality version."""
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = f'https://www.{self.SITE_DOMAIN}{img_url}'
        
        # For Fashionphile, try to get high-res versions
        # They typically use imgix CDN, so we can add parameters for higher quality
        if 'imgix.net' in img_url and '?' not in img_url:
            img_url += '?w=800&h=800&fit=fill&auto=format'
        
        return img_url
    
    def _extract_sku_from_url(self, url: str) -> Optional[str]:
        """Extract SKU from product URL."""
        # Fashionphile URLs end with the SKU: /p/product-name-1667682
        sku_match = re.search(r'-(\d+)$', url.split('?')[0])
        return sku_match.group(1) if sku_match else None
    
    def _is_valid_product_image(self, img_url: str) -> bool:
        """Image validation for Fashionphile."""
        if not img_url:
            return False
        
        img_url_lower = img_url.lower()
        
        # Skip obviously non-product images
        skip_patterns = [
            'logo', 'icon', 'banner', 'promo', 'ad_',
            '_thumb', '_mini', 'favicon', 'sprite'
        ]
        
        if any(pattern in img_url_lower for pattern in skip_patterns):
            return False
        
        # Accept images from Fashionphile domains
        return any(domain in img_url_lower for domain in [self.SITE_DOMAIN, self.CDN_DOMAIN, 'imgix.net'])
    
    def _is_valid_product_url(self, url: str) -> bool:
        """Check if URL is a valid product page."""
        return bool(url and self.SITE_DOMAIN in url and '/p/' in url)
    
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
                    products_for_download, batch_size=75
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
        print(f"🤖 Running batched AI categorization for {len(products_data)} products...")
        
        try:
            # This now processes in batches instead of all at once!
            categories = await ai_categorizer.categorize_products_batch(products_data)
        except Exception as e:
            print(f"⚠️  Batched AI categorization failed: {e}, using fallback")
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
                print(f"⚠️  Error creating Product object for {data.get('product_name', 'unknown')}: {e}")
                continue
        
        conversion_time = time.time() - conversion_start
        print(f"✅ Successfully categorized and created {len(products)} products!")
        print(f"⏱️  Product conversion took {conversion_time:.1f}s ({conversion_time/len(products):.2f}s per product)")
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