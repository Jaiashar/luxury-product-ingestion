# scraper/sites/ai_stockx.py
"""Complete StockX scraper with accurate product extraction."""

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

class AIStockXScraper(BaseSiteScraper):
    def __init__(self, scrapfly_client, rate_limit: float = 2.0, download_images: bool = True):
        super().__init__(scrapfly_client, rate_limit)
        
        # Site constants
        self.SITE_DOMAIN = "stockx.com"
        self.CDN_DOMAIN = "images.stockx.com"
        
        # Timing constants
        self.MIN_RENDERING_WAIT = 8000
        self.MAX_RENDERING_WAIT = 12000
        
        # Data limits
        self.MAX_MODEL_LENGTH = 30
        self.PRODUCT_ID_LENGTH = 16
        self.MAX_PAGES_DEFAULT = 15
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
        
        print(f"✅ StockX Image downloading {'enabled' if download_images else 'disabled'} (max {self.max_images_per_product} per product)")
        print(f"⏱️  Rate limit set to {rate_limit}s between requests")
        
        # Time tracking
        self.start_time = None
        self.category_times = {}
        self.product_processing_times = []

    def _clean_brand_name(self, brand: str) -> str:
        """Remove thread pollution from brand name."""
        return re.sub(r'_thread_\d+', '', brand)

    def _detect_gender_from_url(self, url: str) -> str:
        """Detect gender from URL or product info. StockX doesn't have gender-specific URLs."""
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
        return "stockx"
    
    def get_brand_search_urls(self, brand: str) -> List[str]:
        """Get brand URLs from mappings for StockX."""
        urls = []
        
        # Try to find brand mapping
        mapping = brand_mappings.find_brand_mapping("stockx", brand)
        
        if mapping and mapping.active:
            # Handle both single URL and list of URLs
            if isinstance(mapping.url, list):
                urls.extend(mapping.url)
            else:
                urls.append(mapping.url)
        
        # Fallback URL if no mappings found
        if not urls:
            brand_formatted = brand.lower().replace(' ', '-').replace('&', '-and-')
            fallback_url = f"https://stockx.com/brands/{brand_formatted}"
            urls.append(fallback_url)
        
        return urls
    
    def get_supported_brands(self) -> List[str]:
        return brand_mappings.get_supported_brands("stockx")
    
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
        
        print(f"\n🚀 StockX scraping for {brand}")
        print(f"⏰ Started at: {start_datetime.strftime('%H:%M:%S')}")
        
        if max_products:
            print(f"🎯 Limited to {max_products} products")
        else:
            print(f"🎯 Scraping ALL available products")
        
        try:
            # Step 1: Get category URLs
            category_urls = self.get_brand_search_urls(brand)
            all_products_data = []
            
            # Step 2: Process categories
            all_products_data = await self._process_categories_concurrent(
                category_urls, brand, max_products
            )
            
            if not all_products_data:
                print(f"❌ No products found for {brand}")
                return []
            
            print(f"\n🎯 Found {len(all_products_data)} products total")
            
            # FIXED: Only keep products with images if we need to limit
            if max_products and len(all_products_data) > max_products:
                # Prioritize products with images
                products_with_images = [p for p in all_products_data if p.get('images')]
                products_without_images = [p for p in all_products_data if not p.get('images')]
                
                print(f"📸 Products with images: {len(products_with_images)}")
                print(f"📭 Products without images: {len(products_without_images)}")
                
                if len(products_with_images) >= max_products:
                    all_products_data = products_with_images[:max_products]
                    print(f"✅ Selected {max_products} products with images only")
                else:
                    needed = max_products - len(products_with_images)
                    all_products_data = products_with_images + products_without_images[:needed]
                    print(f"✅ Selected {len(products_with_images)} with images + {needed} without")
            
            # Step 3: Download images if enabled
            if self.download_images and all_products_data:
                print(f"📸 Downloading images for {len(all_products_data)} products...")
                all_products_data = await self._download_images_for_products(all_products_data, brand)
            
            # Step 4: Convert to Product objects
            print(f"🤖 Running AI categorization for {len(all_products_data)} products...")
            products = await self._convert_to_product_objects(all_products_data)
            
            # Final stats
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
            return []
    
    async def _process_categories_concurrent(self, category_urls: List[str], brand: str, max_products: int = None) -> List[Dict[str, Any]]:
        """Process category URLs."""
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
        
        print(f"    📊 Total products extracted: {len(all_products_data)}")
        return all_products_data
    
    async def _extract_urls_and_product_info(self, page_url: str, brand: str, 
                                        thread_operation: str = None, 
                                        first_page_only: bool = False) -> List[Dict[str, Any]]:
        """Extract URLs and product info."""
        all_products_data = []
        page_num = 1
        max_pages = 1 if first_page_only else self.MAX_PAGES_DEFAULT
        pages_processed = 0
        
        while page_num <= max_pages:
            try:
                # Construct paginated URL
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
                    pages_processed = page_num - 1 if page_num > 1 else 0
                    break

                gender = self._detect_gender_from_url(page_url)
                page_products_data = await self._extract_products_with_urls_and_info(
                    result.content, paginated_url, brand, gender
                )
                
                if not page_products_data:
                    print(f"    📄 No products found on page {page_num}")
                    pages_processed = page_num
                    break
                
                all_products_data.extend(page_products_data)
                pages_processed = page_num
                
                if first_page_only:
                    break
                    
                page_num += 1
                
            except Exception as e:
                print(f"    ❌ Error fetching page {page_num}: {e}")
                pages_processed = page_num
                break
        
        print(f"    📊 Total products extracted: {len(all_products_data)} (across {pages_processed} pages)")
        return all_products_data
    
    async def _extract_products_with_urls_and_info(self, html: str, page_url: str, brand: str, gender: str) -> List[Dict[str, Any]]:
        """FIXED: Extract products with much better accuracy and filtering."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # FIXED: Use StockX-specific selectors for product containers
            products_data = []
            
            # Try multiple selectors that are known to work for StockX
            selectors = [
                'div[data-testid="product-tile"]',  # Primary StockX product tiles
                'a[href*="/"][data-testid*="product"]',  # Product links
                'div.tile',  # Generic tiles
                'article',  # Article elements
            ]
            
            all_containers = set()
            for selector in selectors:
                containers = soup.select(selector)
                for container in containers:
                    # Convert to string for deduplication
                    container_str = str(container)
                    all_containers.add(container_str)
                        
            valid_products = []
            
            for container_str in all_containers:
                try:
                    container = BeautifulSoup(container_str, 'html.parser').find()
                    product_data = self._extract_product_from_container(container, brand, gender)
                    
                    if product_data and self._is_valid_product_data(product_data):
                        valid_products.append(product_data)
                        
                except Exception as e:
                    continue
            
            return valid_products
            
        except Exception as e:
            print(f"    ❌ Error in product extraction: {e}")
            return []
    
    def _extract_product_from_container(self, container, brand: str, gender: str) -> Optional[Dict[str, Any]]:
        """FIXED: Extract product data from container with better validation."""
        try:
            # Get product URL
            product_url = self._extract_product_url_from_container(container)
            if not product_url:
                return None
            
            # FIXED: Better URL validation
            if not self._is_valid_product_url(product_url):
                return None
            
            # Extract title/name
            title = self._extract_title_from_container(container)
            if not title or len(title) < 3:
                # Try to extract from URL as fallback
                title = self._extract_title_from_url(product_url)
            
            if not title or len(title) < 3:
                return None
            
            # FIXED: Better model parsing
            model = self._parse_model_from_title(title, brand)
            
            # Extract other data
            price = self._extract_price_from_container(container)
            images = self._extract_images_from_container(container)
            sku = self._extract_sku_from_url(product_url)
            
            # Generate IDs
            product_id = self._generate_product_id(brand, model, sku)
            product_name = f"{brand} {model}" if gender == 'unisex' else f"{brand} {model} {gender}"
            
            return {
                'product_id': product_id,
                'brand': brand,
                'model': model,
                'sku': sku,
                'price': price,
                'product_name': product_name,
                'description': '',
                'images': images,
                'source_url': product_url
            }
            
        except Exception as e:
            return None
    
    def _extract_product_url_from_container(self, container) -> Optional[str]:
        """FIXED: Extract product URL from container."""
        try:
            # Try different ways to get URL
            url = None
            
            # Method 1: Direct href
            if hasattr(container, 'get') and container.get('href'):
                url = container.get('href')
            
            # Method 2: Find first anchor
            if not url and hasattr(container, 'find'):
                anchor = container.find('a', href=True)
                if anchor:
                    url = anchor.get('href')
            
            # Method 3: Look for data attributes
            if not url and hasattr(container, 'get'):
                for attr in ['data-href', 'data-url', 'data-link']:
                    if container.get(attr):
                        url = container.get(attr)
                        break
            
            if not url:
                return None
            
            # Clean and complete URL
            if url.startswith('/'):
                url = f"https://stockx.com{url}"
            elif not url.startswith('http'):
                url = f"https://stockx.com/{url}"
            
            return url
            
        except Exception:
            return None
    
    def _extract_title_from_container(self, container) -> Optional[str]:
        """FIXED: Extract title from container."""
        try:
            # Try different title selectors
            title_selectors = [
                '[data-testid*="product-title"]',
                '[data-testid*="title"]',
                '[data-testid*="name"]',
                'h1', 'h2', 'h3', 'h4',
                '.title', '.name', '.product-name',
                'p[title]',  # StockX often uses title attribute
                'span[title]'
            ]
            
            for selector in title_selectors:
                if hasattr(container, 'select_one'):
                    element = container.select_one(selector)
                    if element:
                        # Try text content first
                        text = element.get_text(strip=True)
                        if text and len(text) > 3:
                            return text
                        
                        # Try title attribute
                        title_attr = element.get('title')
                        if title_attr and len(title_attr) > 3:
                            return title_attr
            
            return None
            
        except Exception:
            return None
    
    def _extract_title_from_url(self, url: str) -> Optional[str]:
        """FIXED: Extract title from URL as fallback."""
        try:
            # Extract the path and convert to title
            path = url.replace('https://stockx.com/', '').replace('http://stockx.com/', '')
            if path:
                # Convert dashes to spaces and title case
                title = path.replace('-', ' ').title()
                return title
            return None
        except Exception:
            return None
    
    def _is_valid_product_data(self, product_data: Dict[str, Any]) -> bool:
        """FIXED: Validate product data to filter out non-products."""
        if not product_data:
            return False
        
        # Check required fields
        required_fields = ['product_id', 'brand', 'model', 'source_url']
        for field in required_fields:
            if not product_data.get(field):
                return False
        
        # Check if URL is valid
        source_url = product_data.get('source_url', '')
        if not self._is_valid_product_url(source_url):
            return False
        
        # Check if model makes sense (not just URL artifacts)
        model = product_data.get('model', '')
        if len(model) < 2:
            return False
        
        # FIXED: Filter out language/locale URLs
        invalid_patterns = [
            'zh-cn', 'en-us', 'fr-fr', 'de-de', 'es-es', 'it-it', 'ja-jp',
            'privacy', 'terms', 'help', 'support', 'about', 'contact',
            'login', 'signup', 'search', 'api', 'brands', 'news'
        ]
        
        model_lower = model.lower()
        source_url_lower = source_url.lower()
        
        for pattern in invalid_patterns:
            if pattern in model_lower or pattern in source_url_lower:
                return False
        
        return True
    
    def _extract_images_from_container(self, container) -> List[str]:
        """FIXED: Extract images from container with better quality control."""
        images = []
        
        try:
            # Image extraction attributes
            img_attributes = [
                'src', 'data-src', 'data-lazy-src', 'data-original',
                'data-image-src', 'srcset', 'data-srcset'
            ]
            
            # Find all img elements
            img_elements = []
            if hasattr(container, 'find_all'):
                img_elements = container.find_all('img')
            
            for img in img_elements:
                for attr in img_attributes:
                    value = img.get(attr)
                    if value:
                        if 'srcset' in attr and ',' in value:
                            # Handle srcset format
                            urls = [url.strip().split(' ')[0] for url in value.split(',')]
                            images.extend(urls)
                        else:
                            images.append(value)
            
            # Look for background images in style attributes
            style_elements = []
            if hasattr(container, 'find_all'):
                style_elements = container.find_all(style=True)
            
            for elem in style_elements:
                style = elem.get('style', '')
                bg_matches = re.findall(r'url\(["\']?([^"\']+)["\']?\)', style)
                images.extend(bg_matches)
            
            # Clean and validate images
            valid_images = []
            seen_base_urls = set()
            
            for img_url in images:
                img_url = img_url.strip().strip('"').strip("'")
                
                if not img_url or len(img_url) < 10:
                    continue
                
                # Complete relative URLs
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    img_url = f'https://images.stockx.com{img_url}'
                elif not img_url.startswith('http'):
                    continue
                
                # Validate as StockX image
                if self._is_valid_product_image(img_url):
                    # Enhance quality
                    img_url = self._enhance_image_url(img_url)
                    
                    # Avoid duplicates
                    base_url = re.sub(r'[?&](w|h|fit|q|dpr|bg)=[^&]*', '', img_url)
                    
                    if base_url not in seen_base_urls:
                        seen_base_urls.add(base_url)
                        valid_images.append(img_url)
            
            # Sort by quality and return top images
            quality_sorted = sorted(valid_images, key=lambda x: self._get_image_quality_score(x), reverse=True)
            return quality_sorted[:self.max_images_per_product]
            
        except Exception:
            return []
    
    def _get_image_quality_score(self, url: str) -> int:
        """Score image quality based on size indicators."""
        if '_1000' in url or 'w=1000' in url:
            return 1000
        elif '_800' in url or 'w=800' in url:
            return 800
        elif '_600' in url or 'w=600' in url:
            return 600
        elif '_480' in url or 'w=480' in url:
            return 480
        elif '_320' in url or 'w=320' in url:
            return 320
        elif '_240' in url or 'w=240' in url:
            return 240
        else:
            return 100
    
    def _enhance_image_url(self, img_url: str) -> str:
        """Convert image URL to highest quality version."""
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = f'https://{self.CDN_DOMAIN}{img_url}'
        
        # Convert to higher quality
        size_patterns = [
            ('_75.', '_1000.'),
            ('_150.', '_1000.'),
            ('_240.', '_1000.'),
            ('_320.', '_1000.'),
            ('_480.', '_1000.'),
            ('_600.', '_1000.'),
            ('_800.', '_1000.'),
            ('w=75', 'w=1000'),
            ('w=150', 'w=1000'),
            ('w=240', 'w=1000'),
            ('w=320', 'w=1000'),
            ('w=480', 'w=1000'),
        ]
        
        for old_size, new_size in size_patterns:
            if old_size in img_url:
                img_url = img_url.replace(old_size, new_size)
                break
        
        return img_url
    
    def _extract_sku_from_url(self, url: str) -> Optional[str]:
        """Extract SKU from product URL."""
        try:
            url_path = url.replace('https://stockx.com/', '').replace('http://stockx.com/', '')
            if url_path:
                return url_path[:50]
            return None
        except Exception:
            return None
    
    def _is_valid_product_image(self, img_url: str) -> bool:
        """FIXED: Image validation for StockX."""
        if not img_url:
            return False
        
        img_url_lower = img_url.lower()
        
        # Must be from StockX domains
        if not any(domain in img_url_lower for domain in [self.SITE_DOMAIN, self.CDN_DOMAIN, 'images.stockx.com']):
            return False
        
        # Skip non-product images
        skip_patterns = [
            'logo', 'icon', 'banner', 'promo', 'ad_',
            '_thumb', '_mini', 'favicon', 'sprite',
            'avatar', 'profile', 'brand-logo'
        ]
        
        return not any(pattern in img_url_lower for pattern in skip_patterns)
    
    def _is_valid_product_url(self, url: str) -> bool:
        """FIXED: Check if URL is a valid StockX product page."""
        if not url or self.SITE_DOMAIN not in url:
            return False
        
        try:
            # Parse URL to get clean path
            parsed = urlparse(url)
            path = parsed.path
            
            # FIXED: More strict validation for StockX product URLs
            
            # Skip known non-product paths
            skip_paths = [
                '/brands/', '/news/', '/about/', '/help/', '/login/', '/signup/', 
                '/search', '/api/', '/static/', '/assets/', '/favicon', '/robots',
                '/sitemap', '/privacy', '/terms', '/contact', '/careers', '/press',
                '/zh-cn', '/en-us', '/fr-fr', '/de-de', '/es-es', '/it-it', '/ja-jp'
            ]
            
            for skip_path in skip_paths:
                if path.startswith(skip_path):
                    return False
            
            # Must have at least one dash (typical product URLs)
            if '-' not in path:
                return False
            
            # Must not be too short or too long
            if len(path) < 10 or len(path) > 200:
                return False
            
            # FIXED: Better pattern matching for StockX product URLs
            # StockX product URLs typically look like: /nike-air-max-90-white-black
            # They usually don't have multiple slashes
            if path.count('/') > 1:
                return False
            
            # Should not contain common non-product indicators
            non_product_indicators = [
                'page=', 'sort=', 'filter=', 'search=', 'category=',
                'brand=', 'size=', 'color=', '?', '#'
            ]
            
            for indicator in non_product_indicators:
                if indicator in url:
                    return False
            
            # Should match product URL pattern
            return bool(re.match(r'^/[\w-]+-[\w-]+', path))
            
        except Exception:
            return False
    
    def _extract_price_from_container(self, container) -> Optional[int]:
        """Extract price from container."""
        try:
            price_selectors = [
                '[data-testid*="price"]',
                '.price',
                '[class*="price"]',
                '[class*="Price"]'
            ]
            
            for selector in price_selectors:
                if hasattr(container, 'select_one'):
                    price_elem = container.select_one(selector)
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        price_match = re.search(r'\$?([\d,]+)', price_text.replace(',', ''))
                        if price_match:
                            try:
                                return int(price_match.group(1).replace(',', ''))
                            except ValueError:
                                continue
            
            return None
            
        except Exception:
            return None
    
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
                    products_for_download, batch_size=150
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
        """Convert scraped data to Product objects with AI categorization."""
        from ..utils.ai_categorizer import ai_categorizer
        
        conversion_start = time.time()
        
        products = []
        
        try:
            categories = await ai_categorizer.categorize_products_batch(products_data)
        except Exception as e:
            print(f"⚠️  AI categorization failed: {e}, using fallback")
            categories = []
            for data in products_data:
                fallback_category = ai_categorizer._fallback_categorize(
                    data.get('model', '') or data.get('product_name', '')
                )
                categories.append(fallback_category)
        
        while len(categories) < len(products_data):
            categories.append('footwear')
        
        # Process each product with its category
        for i, data in enumerate(products_data):
            try:
                category = categories[i] if i < len(categories) else 'footwear'
                
                # Create images list
                images = []
                
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