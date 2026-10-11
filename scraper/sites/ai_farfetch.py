"""Optimized Farfetch scraper: Enhanced product detection with complete info extraction."""

import random
import re
import json
import os
import asyncio
import hashlib
import time
import base64
import json
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

class AIFarfetchScraper(BaseSiteScraper):
    def __init__(self, scrapfly_client, rate_limit: float = 3.0, download_images: bool = True):
        super().__init__(scrapfly_client, rate_limit)
        
        # Site constants
        self.SITE_DOMAIN = "farfetch.com"
        self.CDN_DOMAIN = "cdn-images.farfetch-contents.com"
        
        # Timing constants
        self.MIN_RENDERING_WAIT = 6000
        self.MAX_RENDERING_WAIT = 9000
        
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
        return "farfetch"
    
    def get_brand_search_urls(self, brand: str) -> List[str]:
        """Get all brand URLs (both men's and women's) from mappings."""
        urls = []
        
        # Try to find both men's and women's versions
        for gender in ['women', 'men']:
            search_key = f"{brand.lower()} {gender}"
            mapping = brand_mappings.find_brand_mapping("farfetch", search_key)
            
            if mapping and mapping.active:
                print(f"📌 Found {gender}'s mapping: {mapping.brand_name}")
                
                # Handle both single URL and list of URLs
                if isinstance(mapping.url, list):
                    urls.extend(mapping.url)
                    print(f"   📋 Added {len(mapping.url)} URLs for {gender}")
                else:
                    urls.append(mapping.url)
                    print(f"   📋 Added 1 URL for {gender}")
        
        # If no gender-specific mappings found, try general brand mapping
        if not urls:
            mapping = brand_mappings.find_brand_mapping("farfetch", brand)
            if mapping and mapping.active:
                print(f"📌 Found general mapping: {mapping.brand_name}")
                
                # Handle both single URL and list of URLs
                if isinstance(mapping.url, list):
                    urls.extend(mapping.url)
                    print(f"   📋 Added {len(mapping.url)} URLs from general mapping")
                else:
                    urls.append(mapping.url)
                    print(f"   📋 Added 1 URL from general mapping")
        
        # Fallback URLs if no mappings found
        if not urls:
            brand_formatted = brand.lower().replace(' ', '-').replace('&', 'and')
            fallback_urls = [
                f"https://www.{self.SITE_DOMAIN}/shopping/women/{brand_formatted}/items.aspx",
                f"https://www.{self.SITE_DOMAIN}/shopping/men/{brand_formatted}/items.aspx"
            ]
            print(f"⚠️  No mappings found for {brand}, using fallback URLs")
            urls.extend(fallback_urls)
        
        print(f"🎯 Total URLs to scrape: {len(urls)}")
        return urls
    
    def get_supported_brands(self) -> List[str]:
        return brand_mappings.get_supported_brands("farfetch")
    
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
        # START TIMING
        self.start_time = time.time()
        start_datetime = datetime.now()
        
        print(f"\n🚀 Enhanced scraping for {brand}")
        print(f"⏰ Started at: {start_datetime.strftime('%H:%M:%S')}")
        print(f"🔍 Strategy: Enhanced product detection + Complete info extraction")
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
                delay = random.uniform(2.0, 5.0) * index 
                await asyncio.sleep(delay)
                
                print(f"\n📄 [Thread {index+1}] Starting: {category_url}")
                
                # CREATE A SEPARATE SCRAPER INSTANCE FOR THIS THREAD
                thread_scraper = AIFarfetchScraper(
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

    async def _make_enhanced_request(self, url: str, brand: str, operation: str):
        """Enhanced request focusing on better auto-scroll and wait times."""
        try:
            print(f"    🔄 Using enhanced auto-scroll for lazy loading")
            
            # Skip JS scenario for now - use enhanced auto-scroll with longer waits
            result = await self.make_request_with_session(
                url=url,
                brand=brand,
                operation=operation,
                render_js=True,
                auto_scroll=True,
                rendering_wait=random.randint(12000, 18000),  # Much longer wait for lazy loading
                
                # Additional headers
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                }
            )
            
            return result
            
        except Exception as e:
            print(f"❌ Enhanced request failed: {e}")
            # Fallback to your original method
            try:
                print(f"    🔄 Falling back to original request method...")
                result = await self.make_request_with_session(
                    url=url,
                    brand=brand,
                    operation=operation,
                    render_js=True,
                    auto_scroll=True,
                    rendering_wait=random.randint(self.MIN_RENDERING_WAIT, self.MAX_RENDERING_WAIT),
                )
                return result
            except Exception as fallback_error:
                print(f"❌ Fallback also failed: {fallback_error}")
                return None

    # UPDATE your container detection to be smarter about lazy loading:

    def _find_all_product_containers(self, soup: BeautifulSoup) -> List:
        """Corrected container detection with proper validation."""
        
        # STRATEGY 1: Try selectors but VALIDATE the results
        primary_selectors = [
            'li[data-testid*="product"]',                 # Your original winning selector
            'div[data-component="ProductCard"]',          # Also effective
            'div[data-testid*="product"]',                # Alternative
            'div[data-testid="product-card"]',            # More specific
            'article[data-testid*="product"]',            # Article-based
        ]
        
        for selector in primary_selectors:
            try:
                containers = soup.select(selector)
                if containers:
                    # VALIDATE: Check if these containers actually contain products
                    valid_containers = []
                    for container in containers:
                        if self._is_valid_product_container(container):
                            valid_containers.append(container)
                    
                    print(f"    🔍 Selector '{selector}' found {len(containers)} containers, {len(valid_containers)} valid")
                    
                    # If we found a good number of valid containers, use this selector
                    if len(valid_containers) >= 80:
                        print(f"    ✅ Using selector: {selector} ({len(valid_containers)} valid containers)")
                        return valid_containers
                    elif len(valid_containers) >= 50:
                        print(f"    ⚠️  Moderate results with {selector}, continuing search...")
                        # Don't return yet, try to find more
                    
            except Exception as e:
                print(f"    ❌ Error with selector '{selector}': {e}")
                continue
        
        # STRATEGY 2: Combine all valid containers from all selectors
        print(f"    🔄 No single selector found enough containers, combining all...")
        
        all_containers = []
        for selector in primary_selectors:
            try:
                containers = soup.select(selector)
                for container in containers:
                    if self._is_valid_product_container(container):
                        all_containers.append(container)
            except Exception as e:
                continue
        
        # STRATEGY 3: URL-based detection if still not enough
        if len(all_containers) < 80:
            print(f"    🔍 Still low count ({len(all_containers)}), trying URL-based detection...")
            
            # Find all product links
            product_links = soup.find_all('a', href=lambda x: x and '-item-' in x)
            print(f"    🔗 Found {len(product_links)} product links")
            
            # Find containers from links
            for link in product_links:
                container = self._find_container_from_link(link)
                if container and self._is_valid_product_container(container):
                    all_containers.append(container)
        
        # STRATEGY 4: Grid-based detection as last resort
        if len(all_containers) < 60:
            print(f"    🔍 Last resort: trying grid-based detection...")
            
            grid_selectors = [
                'main div[class*="grid"] > div',
                'div[class*="listing"] > div',
                'div[class*="products"] > div',
                'ul[class*="list"] > li',
                'div[class*="row"] > div[class*="col"]',
                'section[class*="grid"] > div',
            ]
            
            for grid_selector in grid_selectors:
                try:
                    potential_containers = soup.select(grid_selector)
                    for container in potential_containers:
                        if self._is_valid_product_container(container):
                            all_containers.append(container)
                            
                    if len(all_containers) >= 60:
                        break
                        
                except Exception as e:
                    continue
        
        # Final deduplication and return
        unique_containers = self._deduplicate_containers(all_containers)
        print(f"    📊 Final container count: {len(unique_containers)}")
        
        return unique_containers
    

    def _is_valid_product_container(self, element) -> bool:
        """ENHANCED validation to ensure container actually contains a product."""
        if not element or not hasattr(element, 'name') or not element.name:
            return False
        
        # Must be a container element
        if element.name not in ['div', 'li', 'article', 'section']:
            return False
        
        # CRITICAL: Must contain a product link
        product_link = element.find('a', href=lambda x: x and '-item-' in x)
        if not product_link:
            return False
        
        # Must have actual product characteristics
        has_image = element.find('img') is not None
        has_price = bool(element.find(string=lambda x: x and re.search(r'[\$€£¥]\s*\d+', x) if x else False))
        has_text_content = bool(element.find(['h1', 'h2', 'h3', 'h4', 'p', 'span']))
        
        # Check for meaningful text content (not just whitespace)
        text_content = element.get_text(strip=True)
        has_meaningful_text = len(text_content) > 10  # At least 10 characters
        
        # Check for product-specific attributes
        has_product_data = bool(element.get('data-testid') or element.get('data-component'))
        
        # Check for product-specific CSS classes
        class_attr = element.get('class', [])
        if isinstance(class_attr, list):
            class_str = ' '.join(class_attr).lower()
        else:
            class_str = str(class_attr).lower()
        
        has_product_class = any(keyword in class_str for keyword in [
            'product', 'item', 'card', 'listing'
        ])
        
        # STRICTER VALIDATION: Must have multiple characteristics
        basic_characteristics = [has_image, has_price, has_text_content, has_meaningful_text]
        attribute_characteristics = [has_product_data, has_product_class]
        
        basic_score = sum(basic_characteristics)
        attribute_score = sum(attribute_characteristics)
        
        # Must have at least 2 basic characteristics AND 1 attribute characteristic
        # OR at least 3 basic characteristics
        return (basic_score >= 2 and attribute_score >= 1) or basic_score >= 3

    # Also update the extraction to be more permissive
    async def _extract_products_enhanced(self, html: str, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """Enhanced product extraction with better container detection."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Step 1: Find all containers with improved detection
            all_containers = self._find_all_product_containers(soup)
            print(f"    🔍 Found {len(all_containers)} potential containers")
            
            # Step 2: Extract from containers
            products_data = []
            successful_extractions = 0
            
            for i, container in enumerate(all_containers):
                try:
                    product_info = self._extract_complete_info_from_container(container, page_url, brand, gender)
                    if product_info:
                        products_data.append(product_info)
                        successful_extractions += 1
                        
                        # Debug: Print every 25th successful extraction
                        if successful_extractions % 25 == 0:
                            print(f"    ✅ Extracted {successful_extractions} products so far...")
                            
                except Exception as e:
                    continue
            
            print(f"    📊 Successfully extracted {len(products_data)} products from {len(all_containers)} containers")
            
            # Step 3: Only use URL fallback if we found very few products
            if len(products_data) < 50:
                print(f"    🔄 Low extraction count, running URL-based fallback...")
                url_based_products = await self._extract_products_from_urls(html, page_url, brand, gender)
                
                # Merge without duplicates
                existing_urls = {p.get('source_url', '') for p in products_data}
                for url_product in url_based_products:
                    if url_product.get('source_url') not in existing_urls:
                        products_data.append(url_product)
                
                print(f"    📈 After URL fallback: {len(products_data)} total products")
            else:
                print(f"    ✅ Good extraction count, skipping URL fallback")
            
            return products_data
            
        except Exception as e:
            print(f"    ❌ Error in enhanced product extraction: {e}")
            return []

    # ALSO: Update your main extraction method to handle the enhanced request:

    async def _extract_urls_and_product_info(self, page_url: str, brand: str, 
                                        thread_operation: str = None, 
                                        first_page_only: bool = False) -> List[Dict[str, Any]]:
        """Enhanced extraction with proper lazy loading."""
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
                    if '?' in page_url:
                        paginated_url = f"{page_url}&page={page_num}"
                    else:
                        paginated_url = f"{page_url}?page={page_num}"
                
                page_label = "first page" if first_page_only else f"page {page_num}"
                print(f"    📄 Processing {page_label}: {paginated_url}")
                
                # Use thread_operation if provided, otherwise default operation
                operation = f"{thread_operation}_page_{page_num}" if thread_operation else f"page_{page_num}"
                
                # USE ENHANCED REQUEST for better lazy loading
                result = await self._make_enhanced_request(
                    url=paginated_url,
                    brand=brand,
                    operation=operation
                )
                
                if not result or result.status_code != 200:
                    print(f"    ❌ {page_label} failed: {result.status_code if result else 'No response'}")
                    consecutive_empty_pages += 1
                    page_num += 1
                    continue

                gender = self._detect_gender_from_url(page_url)
                
                # Extract products with enhanced method
                page_products_data = await self._extract_products_enhanced(
                    result.content, paginated_url, brand, gender
                )
                
                print(f"    📊 Found {len(page_products_data)} products on {page_label}")
                
                if not page_products_data:
                    print(f"    📄 No products found on {page_label}")
                    consecutive_empty_pages += 1
                    page_num += 1
                    if first_page_only:
                        break
                    continue
                
                # Rest of your existing pagination logic...
                all_products_data.extend(page_products_data)
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
        
        print(f"    📊 Total products extracted: {len(all_products_data)} (across {page_num-1} pages)")
        return all_products_data

    def _has_product_link(self, element) -> bool:
        """VERY permissive check: does this element contain a product link?"""
        if not element or not hasattr(element, 'name'):
            return False
        
        # STRATEGY 1: Look for exact product link pattern
        product_link = element.find('a', href=lambda x: x and '-item-' in x)
        if product_link:
            return True
        
        # STRATEGY 2: Look for any link that might be a product link
        all_links = element.find_all('a', href=True)
        for link in all_links:
            href = link.get('href', '')
            if any(pattern in href for pattern in ['-item-', '/item-', 'item_', 'product-', '/product/', '/shopping/']):
                return True
        
        # STRATEGY 3: Look for product links in any attribute
        for elem in element.find_all(attrs=True):
            for attr_name, attr_value in elem.attrs.items():
                if isinstance(attr_value, str) and any(pattern in attr_value for pattern in ['-item-', 'product', 'shopping']):
                    return True
        
        # STRATEGY 4: Look for product information indicators
        text_content = element.get_text(strip=True)
        
        # Check for product-like indicators
        has_price = bool(re.search(r'[\$€£¥]\s*\d+', text_content))
        has_brand_words = any(word in text_content.lower() for word in ['chanel', 'gucci', 'dior', 'prada', 'versace', 'luxury', 'designer'])
        has_product_words = any(word in text_content.lower() for word in ['bag', 'shoes', 'dress', 'jacket', 'watch', 'wallet', 'item', 'size', 'color'])
        has_image = element.find('img') is not None
        
        # If it has product-like content, consider it valid
        if has_price or (has_brand_words and has_image) or (has_product_words and has_image):
            return True
        
        # STRATEGY 5: If it's from the li[data-testid*="product"] selector, it's probably valid
        # Check if this element has product-related data attributes
        if element.name == 'li' and element.get('data-testid'):
            testid = element.get('data-testid', '').lower()
            if 'product' in testid:
                # If it has some text content and an image, it's likely a product
                if len(text_content) > 20 and has_image:
                    return True
        
        return False

    def _deduplicate_containers(self, containers: List) -> List:
        """Remove duplicate containers while preserving order."""
        unique_containers = []
        seen_signatures = set()
        
        for container in containers:
            # Use the product URL as the unique signature
            product_link = container.find('a', href=lambda x: x and '-item-' in x)
            if product_link and product_link.get('href'):
                signature = product_link.get('href')
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    unique_containers.append(container)
        
        return unique_containers

    def _find_container_from_link(self, link) -> Optional:
        """Find the product container that contains a product link."""
        if not link:
            return None
        
        current = link.parent
        
        # Look up the DOM tree (up to 6 levels)
        for level in range(1, 7):
            if not current or not hasattr(current, 'name'):
                break
            
            # Check if this level looks like a product container
            if (current.name in ['div', 'li', 'article', 'section'] and 
                self._container_has_product_characteristics(current)):
                return current
            
            current = current.parent if hasattr(current, 'parent') else None
        
        return None
    
    def _container_has_product_characteristics(self, element) -> bool:
        """Quick check if element has product container characteristics."""
        if not element:
            return False
        
        # Must contain our product link
        if not element.find('a', href=lambda x: x and '-item-' in x):
            return False
        
        # Quick characteristic check
        has_image = element.find('img') is not None
        has_text = len(element.get_text(strip=True)) > 10
        
        return has_image and has_text

    # ALSO UPDATE your _extract_complete_info_from_container method to be more permissive:

    def _extract_complete_info_from_container(self, container, page_url: str, brand: str, gender: str) -> Optional[Dict[str, Any]]:
        """Extract complete product info with more permissive validation."""
        try:
            # Extract product URL
            link_elem = container.find('a', href=lambda x: x and '-item-' in x)
            if not link_elem:
                return None
            
            container_url = link_elem['href']
            if not container_url.startswith('http'):
                if container_url.startswith('/'):
                    container_url = f"https://www.{self.SITE_DOMAIN}{container_url}"
                else:
                    container_url = f"https://www.{self.SITE_DOMAIN}/{container_url}"
            
            # Extract product title/name - MORE PERMISSIVE
            title_elem = (
                container.find('p', {'data-component': 'ProductCardDescription'}) or
                container.find('div', class_=lambda x: x and ('title' in x.lower() or 'name' in x.lower())) or
                container.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) or
                container.find('span', class_=lambda x: x and 'name' in x.lower()) or
                container.find('p', class_=lambda x: x and 'title' in x.lower()) or
                container.find('a', href=True) or
                container.find('span') or  # More permissive
                container.find('p')        # Even more permissive
            )
            
            if title_elem:
                full_title = title_elem.get_text(strip=True)
            else:
                # Extract from URL as fallback
                url_match = re.search(r'/([^/]+)-item-\d+', container_url)
                if url_match:
                    full_title = url_match.group(1).replace('-', ' ').title()
                else:
                    full_title = "Unknown Product"
            
            if not full_title:
                full_title = "Unknown Product"
            
            # Parse model from title
            model = self._parse_model_from_title(full_title, brand)
            
            # Extract price - more permissive
            price = self._extract_price_enhanced(container)
            
            # Create product name with gender
            if gender != 'unisex':
                product_name = f"{brand} {model} {gender}"
            else:
                product_name = f"{brand} {model}"
            
            # Enhanced image extraction
            images = self._extract_images_enhanced(container)
            
            # Extract SKU from URL
            sku = self._extract_sku_from_url(container_url)
            
            # Generate product ID
            product_id = self._generate_product_id(brand, model, sku)
            
            return {
                'product_id': product_id,
                'brand': brand,
                'model': model,
                'sku': sku,
                'price': price,
                'product_name': product_name,
                'description': '',
                'images': images,
                'source_url': container_url
            }
            
        except Exception as e:
            # Don't fail silently - but be more permissive
            return None
    
    def _looks_like_product_container(self, element) -> bool:
        """Check if element looks like a product container."""
        if not element or not hasattr(element, 'name') or not element.name:
            return False
        
        # Must contain a product link
        if not element.find('a', href=lambda x: x and '-item-' in x):
            return False
        
        # Check for product-like content
        has_image = element.find('img') is not None
        has_price = bool(element.find(text=lambda x: x and re.search(r'[\$€£]\s*\d+', x) if x else False))
        has_title = bool(element.find(['h1', 'h2', 'h3', 'h4', 'p', 'span']))
        
        # Should have at least 2 of these characteristics
        characteristics = sum([has_image, has_price, has_title])
        return characteristics >= 2
    
    def _find_containers_in_grids(self, soup: BeautifulSoup) -> List:
        """Find product containers within grid layouts."""
        containers = []
        
        # Common grid patterns
        grid_selectors = [
            'div[class*="grid"] > div',
            'ul[class*="list"] > li',
            'div[class*="row"] > div',
            'div[class*="items"] > div',
            'div[class*="products"] > div',
            'section[class*="grid"] > div',
            'main div[class*="grid"] > div'
        ]
        
        for selector in grid_selectors:
            try:
                potential_containers = soup.select(selector)
                for container in potential_containers:
                    # Check if this container has a product link
                    if container.find('a', href=lambda x: x and '-item-' in x):
                        containers.append(container)
                        
                if containers:
                    print(f"    📊 Found {len(containers)} containers in grid: {selector}")
                    break
            except Exception as e:
                continue
        
        return containers
    
    def _extract_price_enhanced(self, container) -> Optional[int]:
        """Enhanced price extraction with multiple strategies."""
        # Strategy 1: Data component selectors
        price_selectors = [
            '[data-component*="Price"]',
            '[data-testid*="price"]',
            '.price',
            '[class*="price"]',
            '[class*="cost"]',
            '[class*="amount"]'
        ]
        
        for selector in price_selectors:
            try:
                price_elem = container.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price = self._parse_price_from_text(price_text)
                    if price:
                        return price
            except Exception:
                continue
        return None
    
    def _parse_price_from_text(self, price_text: str) -> Optional[int]:
        """Parse price from text string."""
        if not price_text:
            return None
        
        # Remove currency symbols and extract numbers
        price_match = re.search(r'(\d{1,3}(?:,\d{3})*)', price_text.replace(',', '').replace('.', ''))
        if price_match:
            try:
                return int(price_match.group().replace(',', ''))
            except ValueError:
                return None
        
        return None
    
    def _extract_images_enhanced(self, container) -> List[str]:
        """Enhanced image extraction with multiple strategies."""
        images = []
        
        # Strategy 1: Direct img tags with all possible attributes
        img_attributes = [
            'src', 'data-src', 'data-lazy-src', 'data-original', 
            'data-lazy', 'data-image-src', 'data-srcset', 'data-image-url',
            'data-bg-src', 'data-background-image'
        ]
        
        for img in container.find_all('img'):
            for attr in img_attributes:
                src = img.get(attr)
                if src and self._is_valid_product_image(src):
                    enhanced_src = self._enhance_image_url(src)
                    if enhanced_src not in images:
                        images.append(enhanced_src)
        
        # Strategy 2: Picture/source elements
        for picture in container.find_all('picture'):
            for source in picture.find_all('source'):
                # Check srcset
                srcset = source.get('srcset')
                if srcset:
                    for url_part in srcset.split(','):
                        url = url_part.strip().split(' ')[0]
                        if self._is_valid_product_image(url):
                            enhanced_url = self._enhance_image_url(url)
                            if enhanced_url not in images:
                                images.append(enhanced_url)
                
                # Check src
                src = source.get('src')
                if src and self._is_valid_product_image(src):
                    enhanced_src = self._enhance_image_url(src)
                    if enhanced_src not in images:
                        images.append(enhanced_src)
        
        # Strategy 3: Background images in CSS
        for elem in container.find_all(['div', 'span', 'section'], style=True):
            style = elem.get('style', '')
            bg_matches = re.findall(r'background-image:\s*url\(["\']?([^"\']+)["\']?\)', style)
            for bg_url in bg_matches:
                if self._is_valid_product_image(bg_url):
                    enhanced_bg = self._enhance_image_url(bg_url)
                    if enhanced_bg not in images:
                        images.append(enhanced_bg)
        
        # Strategy 4: Data attributes on any element
        for elem in container.find_all(attrs=True):
            for attr, value in elem.attrs.items():
                if isinstance(value, str) and any(x in attr.lower() for x in ['image', 'src', 'url']):
                    if self._is_valid_product_image(value):
                        enhanced_val = self._enhance_image_url(value)
                        if enhanced_val not in images:
                            images.append(enhanced_val)
        
        # Strategy 5: Look for Farfetch-specific image patterns
        for elem in container.find_all(['div', 'span', 'img']):
            for attr in ['data-image', 'data-media', 'data-asset']:
                value = elem.get(attr)
                if value and self._is_valid_product_image(value):
                    enhanced_val = self._enhance_image_url(value)
                    if enhanced_val not in images:
                        images.append(enhanced_val)
        
        return images[:self.max_images_per_product]
    
    async def _extract_products_from_urls(self, html: str, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """URL-based product extraction as fallback."""
        try:
            # Use existing robust URL extraction
            product_urls = await self._extract_product_urls_robust(html)
            
            products_data = []
            for product_url in product_urls:
                try:
                    # Create enhanced product from URL
                    soup = BeautifulSoup(html, 'html.parser')
                    product_data = await self._create_enhanced_product_from_url(
                        product_url, page_url, brand, gender, soup
                    )
                    if product_data:
                        products_data.append(product_data)
                except Exception as e:
                    continue
            
            return products_data
            
        except Exception as e:
            print(f"    ❌ Error in URL-based extraction: {e}")
            return []
    
    async def _extract_product_urls_robust(self, html: str) -> List[str]:
        """Robust URL extraction method (enhanced version)."""
        urls = set()
        
        # Multiple regex patterns to catch different formats
        patterns = [
            r'href=["\']([^"\']*-item-\d+[^"\']*\.aspx[^"\']*)["\']',
            r'href=["\']([^"\']*-item-\d+[^"\']*)["\']',
            r'data-[^=]*=["\']([^"\']*-item-\d+[^"\']*)["\']',
            r'https://[^"\s]*farfetch\.com[^"\s]*-item-\d+[^"\s]*',
            r'-item-(\d+)',
        ]
        
        all_matches = []
        for pattern in patterns:
            try:
                matches = re.findall(pattern, html, re.IGNORECASE)
                all_matches.extend(matches)
            except Exception as e:
                continue
        
        # Process all matches
        for match in all_matches:
            try:
                url = match
                
                # If it's just a number (from pattern 5), construct the URL
                if isinstance(match, str) and match.isdigit():
                    id_pattern = f'-item-{match}'
                    context_matches = re.findall(f'[^"\'\\s]*{re.escape(id_pattern)}[^"\'\\s]*', html)
                    if context_matches:
                        url = context_matches[0]
                    else:
                        continue
                
                # Clean and complete the URL
                if url.startswith('/'):
                    url = f"https://www.{self.SITE_DOMAIN}{url}"
                elif not url.startswith('http'):
                    if '/shopping/' in url or url.startswith('shopping/'):
                        if not url.startswith('/'):
                            url = '/' + url
                        url = f"https://www.{self.SITE_DOMAIN}{url}"
                    else:
                        continue
                
                url = url.replace('\\', '')
                
                if '?' in url:
                    base_url, query = url.split('?', 1)
                    if 'storeid=' in query:
                        url = f"{base_url}?{query}"
                    else:
                        url = base_url
                
                if self._is_valid_product_url(url):
                    urls.add(url)
            except Exception as e:
                continue
        
        # BeautifulSoup approach for additional URLs
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all links
            all_links = soup.find_all(['a', 'link'], href=True)
            for link in all_links:
                try:
                    href = link.get('href', '')
                    if '-item-' in href:
                        if href.startswith('/'):
                            href = f"https://www.{self.SITE_DOMAIN}{href}"
                        if self._is_valid_product_url(href):
                            urls.add(href)
                except Exception as e:
                    continue
            
            # Find URLs in data attributes
            for element in soup.find_all(attrs=True):
                try:
                    for attr, value in element.attrs.items():
                        if isinstance(value, str) and '-item-' in value and 'http' in value:
                            if self._is_valid_product_url(value):
                                urls.add(value)
                except Exception as e:
                    continue
            
        except Exception as e:
            print(f"    ❌ BeautifulSoup URL extraction failed: {e}")
        
        return list(urls)
    
    async def _create_enhanced_product_from_url(self, product_url: str, page_url: str, 
                                              brand: str, gender: str, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Create enhanced product from URL with better image detection."""
        try:
            # Extract SKU from URL
            sku = self._extract_sku_from_url(product_url)
            
            # Try to find this product in the page HTML
            product_images = []
            if sku:
                # Look for this product ID in the page HTML
                product_elements = soup.find_all(text=lambda x: x and sku in x if x else False)
                for elem in product_elements:
                    if elem.parent:
                        # Search for images near this element
                        nearby_images = self._find_images_near_element(elem.parent)
                        product_images.extend(nearby_images)
                        if product_images:
                            break
            
            # Extract product name from URL
            name_match = re.search(r'/([^/]+)-item-\d+', product_url)
            if name_match:
                url_name = name_match.group(1).replace('-', ' ').title()
                brand_parsed, model = self._parse_brand_and_model(url_name)
            else:
                brand_parsed = brand
                model = "Unknown Product"
            
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
                'images': product_images[:self.max_images_per_product]
            }
            
        except Exception as e:
            return None
    
    def _find_images_near_element(self, element) -> List[str]:
        """Find images near a specific element."""
        images = []
        
        # Search in parent elements (up to 5 levels)
        current = element
        for _ in range(5):
            if current and hasattr(current, 'find_all'):
                for img in current.find_all('img'):
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src and self._is_valid_product_image(src):
                        enhanced_src = self._enhance_image_url(src)
                        if enhanced_src not in images:
                            images.append(enhanced_src)
                
                # Also check for background images
                for elem in current.find_all(['div', 'span'], style=True):
                    style = elem.get('style', '')
                    bg_match = re.search(r'background-image:\s*url\(["\']?([^"\']+)["\']?\)', style)
                    if bg_match:
                        bg_url = bg_match.group(1)
                        if self._is_valid_product_image(bg_url):
                            enhanced_bg = self._enhance_image_url(bg_url)
                            if enhanced_bg not in images:
                                images.append(enhanced_bg)
            
            current = current.parent if current and hasattr(current, 'parent') else None
            if not current:
                break
        
        return images
    
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
    
    def _enhance_image_url(self, img_url: str) -> str:
        """Convert image URL to highest quality version."""
        if not img_url:
            return img_url
        
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = f'https://{self.CDN_DOMAIN}{img_url}'
        
        # Convert to high-res version
        size_patterns = [
            ('_480.jpg', '_1000.jpg'),
            ('_320.jpg', '_1000.jpg'),
            ('_240.jpg', '_1000.jpg'),
            ('_480.webp', '_1000.webp'),
            ('_320.webp', '_1000.webp'),
            ('_240.webp', '_1000.webp'),
            ('_small.jpg', '_large.jpg'),
            ('_medium.jpg', '_large.jpg'),
            ('_thumb.jpg', '_large.jpg')
        ]
        
        for old_size, new_size in size_patterns:
            if old_size in img_url:
                img_url = img_url.replace(old_size, new_size)
                break
        
        return img_url
    
    def _extract_sku_from_url(self, url: str) -> Optional[str]:
        """Extract SKU from product URL."""
        if not url:
            return None
        
        sku_match = re.search(r'-item-(\d+)', url)
        return sku_match.group(1) if sku_match else None
    
    def _is_valid_product_image(self, img_url: str) -> bool:
        """Enhanced image validation for Farfetch."""
        if not img_url:
            return False
        
        img_url_lower = img_url.lower()
        
        # Must be from Farfetch domains
        if not any(domain in img_url_lower for domain in [self.SITE_DOMAIN, self.CDN_DOMAIN, 'farfetch']):
            return False
        
        # Skip invalid patterns
        skip_patterns = [
            'logo', 'icon', 'banner', 'promo', 'ad_',
            '_thumb', '_mini', 'favicon', 'sprite',
            'placeholder', 'loading', 'blank'
        ]
        
        if any(pattern in img_url_lower for pattern in skip_patterns):
            return False
        
        # Must have valid image extension or be from CDN
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        has_valid_extension = any(ext in img_url_lower for ext in valid_extensions)
        is_cdn = self.CDN_DOMAIN in img_url_lower
        
        return has_valid_extension or is_cdn
    
    def _is_valid_product_url(self, url: str) -> bool:
        """Enhanced validation for product URLs."""
        if not url:
            return False
        
        # Must be from Farfetch domain
        if self.SITE_DOMAIN not in url:
            return False
        
        # Must contain item pattern
        if not re.search(r'-item-\d+', url):
            return False
        
        # Exclude common false positives
        exclude_patterns = [
            '/wishlist/', '/cart/', '/checkout/', '/account/', '/help/',
            '/size-guide/', '/lookbook/', '/editorial/', '/brand-',
            '/sale/', '/outlet/', '/new-in/', '/search/', '/filter/',
            'javascript:', 'mailto:', 'tel:', '#', 'void(0)'
        ]
        
        url_lower = url.lower()
        if any(pattern in url_lower for pattern in exclude_patterns):
            return False
        
        return True
    
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
        # from ..utils.ai_categorizer import ai_categorizer
        
        conversion_start = time.time()
        
        products = []
        
        # # Use BATCHED AI categorization instead of individual calls
        # print(f"🤖 Running batched AI categorization for {len(products_data)} products...")
        
        # try:
        #     # This now processes in batches instead of all at once!
        #     categories = await ai_categorizer.categorize_products_batch(products_data)
        # except Exception as e:
        #     print(f"⚠️  Batched AI categorization failed: {e}, using fallback")
        #     # Fallback to keyword-based categorization
        #     categories = []
        #     for data in products_data:
        #         fallback_category = ai_categorizer._fallback_categorize(
        #             data.get('model', '') or data.get('product_name', '')
        #         )
        #         categories.append(fallback_category)
        
        # # Ensure we have categories for all products
        # while len(categories) < len(products_data):
        #     categories.append('accessories')  # Default fallback

        # Process each product with its category
        for i, data in enumerate(products_data):
            try:
                # Get category (with bounds checking)
                category = None                
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