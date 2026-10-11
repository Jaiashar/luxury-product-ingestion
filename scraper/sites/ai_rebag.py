# scraper/sites/ai_rebag.py
"""Enhanced Rebag scraper with improved image detection and product extraction."""

import random
import re
import json
import os
import asyncio
import hashlib
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from anthropic import Anthropic
from .base import BaseSiteScraper
from ..mappings.brand_urls import brand_mappings
from ..utils.data_models import Product, ProductImage
from ..utils.optimized_image_handler import OptimizedImageHandler

class AIRebagScraper(BaseSiteScraper):
    def __init__(self, scrapfly_client, rate_limit: float = 1.5, download_images: bool = True):
        super().__init__(scrapfly_client, rate_limit)
        
        # Site constants
        self.SITE_DOMAIN = "rebag.com"
        self.SHOP_DOMAIN = "shop.rebag.com"
        self.CDN_DOMAIN = "cdn.shopify.com"
        
        # Timing constants - optimized for Rebag
        self.MIN_RENDERING_WAIT = 6000
        self.MAX_RENDERING_WAIT = 9000
        
        # Data limits
        self.MAX_MODEL_LENGTH = 20
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

    def _clean_brand_name(self, brand: str) -> str:
        """Remove thread pollution from brand name."""
        return re.sub(r'_thread_\d+', '', brand)

    def _detect_gender_from_url(self, url: str) -> str:
        """Detect gender from URL - Rebag is primarily unisex luxury."""
        return 'unisex'

    def _generate_product_id(self, brand: str, model: str, sku: str) -> str:
        """Generate a consistent product ID from brand, model, and SKU."""
        clean_brand = re.sub(r'[^a-zA-Z0-9]', '', brand.lower())
        clean_model = re.sub(r'[^a-zA-Z0-9]', '', model.lower()[:self.MAX_MODEL_LENGTH])
        clean_sku = sku if sku else 'nosku'
        
        combined = f"{clean_brand}:{clean_model}:{clean_sku}"
        hash_obj = hashlib.sha256(combined.encode())
        return hash_obj.hexdigest()[:self.PRODUCT_ID_LENGTH]
    
    def get_site_name(self) -> str:
        return "rebag"
    
    def get_brand_search_urls(self, brand: str) -> List[str]:
        """Get brand URLs from mappings for Rebag."""
        urls = []
        
        # Try to find brand mapping
        mapping = brand_mappings.find_brand_mapping("rebag", brand)
        
        if mapping and mapping.active:
            print(f"📌 Found mapping: {mapping.brand_name}")
            
            # Handle both single URL and list of URLs
            if isinstance(mapping.url, list):
                urls.extend(mapping.url)
                print(f"   📋 Added {len(mapping.url)} URLs from mapping")
            else:
                urls.append(mapping.url)
                print(f"   📋 Added 1 URL from mapping")
        
        # Fallback URL if no mappings found
        if not urls:
            brand_formatted = brand.lower().replace(' ', '-').replace('&', '-')
            fallback_url = f"https://{self.SHOP_DOMAIN}/collections/{brand_formatted}"
            print(f"⚠️  No mappings found for {brand}, using fallback URL")
            urls.append(fallback_url)
        
        print(f"🎯 Total URLs to scrape: {len(urls)}")
        return urls
    
    def get_supported_brands(self) -> List[str]:
        return brand_mappings.get_supported_brands("rebag")
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """Get scraping statistics."""
        return {
            'session_requests': self.session_request_count,
            'current_session': self.current_session[:20] if self.current_session else 'None',
        }
    
    async def scrape_brand_products(self, brand: str, max_products: int = None) -> List[Product]:
        """Enhanced scraping with improved image detection for all products."""
        # START TIMING
        self.start_time = time.time()
        start_datetime = datetime.now()
        
        print(f"\n🚀 Enhanced Rebag scraping for {brand}")
        print(f"⏰ Started at: {start_datetime.strftime('%H:%M:%S')}")
        print(f"🔍 Strategy: Enhanced image detection for ALL products")
        if max_products:
            print(f"🎯 Limited to {max_products} products")
            print(f"🧪 Development mode: Only scraping first page")
        else:
            print(f"🎯 Scraping ALL available products")
        
        try:
            # Step 1: Get category URLs
            category_urls = self.get_brand_search_urls(brand)
            all_products_data = []
            
            # Step 2: Process categories
            all_products_data = await self._process_categories_sequential(
                category_urls, brand, max_products
            )
            
            if not all_products_data:
                print(f"❌ No products found for {brand}")
                return []
            
            print(f"\n🎯 Found {len(all_products_data)} products total")
            
            # Step 3: Enhanced lazy-loading image extraction from listing page
            print(f"🖼️  Running enhanced lazy-loading image extraction...")
            all_products_data = await self._extract_lazy_loaded_images(all_products_data)
            
            # Filter to only products with images
            products_with_images = [p for p in all_products_data if p.get('images')]
            products_without_images = len(all_products_data) - len(products_with_images)
            
            print(f"📸 Products with images: {len(products_with_images)}")
            print(f"📭 Products without images: {products_without_images}")
            
            if not products_with_images:
                print(f"❌ No products found with images for {brand}")
                return []
            
            # Use only products with images
            all_products_data = products_with_images
            print(f"✅ Final count: {len(all_products_data)} products with images")

            # Apply max_products limit to products with images
            if max_products and len(all_products_data) > max_products:
                all_products_data = all_products_data[:max_products]
                print(f"🎯 Limited to {max_products} products with images")
            
            # Step 4: Download images if enabled
            if self.download_images and all_products_data:
                print(f"📸 Downloading images for {len(all_products_data)} products...")
                all_products_data = await self._download_images_for_products(all_products_data, brand)
            
            # Step 5: Convert to Product objects
            products = await self._convert_to_product_objects(all_products_data)
            
            print(f"✅ Successfully created {len(products)} products!")
            
            # TIMING SUMMARY
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
    
    async def _extract_lazy_loaded_images(self, products_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract lazy-loaded images from the existing page HTML without additional requests."""
        print(f"🔍 Analyzing lazy-loaded images in existing page HTML...")
        
        enhanced_products = []
        
        for i, product_data in enumerate(products_data):
            product_url = product_data.get('source_url', '')
            product_name = product_data.get('product_name', 'Unknown')[:40]
            
            print(f"  📦 {i+1}/{len(products_data)}: {product_name}...")
            
            # Start with any existing images
            existing_images = product_data.get('images', [])
            all_images = list(existing_images)  # Copy existing
            
            # Extract product ID/SKU from URL for image pattern matching
            product_id = None
            if '/products/' in product_url:
                product_slug = product_url.split('/products/')[-1].split('?')[0]
                # Look for numeric ID in the slug
                id_match = re.search(r'(\d+)', product_slug)
                if id_match:
                    product_id = id_match.group(1)
            
            if product_id:
                # Generate potential image URLs based on common Rebag patterns
                potential_image_urls = self._generate_rebag_image_urls(product_data)
                
                for img_url in potential_image_urls:
                    if img_url not in all_images:
                        all_images.append(img_url)
                        print(f"    🖼️  Generated potential image: {img_url.split('/')[-1][:50]}...")
                        
                        # Limit to max images per product
                        if len(all_images) >= self.max_images_per_product:
                            break
            
            # Also try to extract from product data/attributes if available
            # This could include structured data, meta tags, etc.
            additional_images = self._extract_images_from_product_data(product_data)
            for img_url in additional_images:
                if img_url not in all_images:
                    all_images.append(img_url)
                    print(f"    🖼️  Found in product data: {img_url.split('/')[-1][:50]}...")
                    
                    if len(all_images) >= self.max_images_per_product:
                        break
            
            # Update product with new images
            product_data['images'] = all_images[:self.max_images_per_product]
            
            if len(all_images) > len(existing_images):
                print(f"    ✅ Enhanced: {len(existing_images)} → {len(all_images)} images")
            elif existing_images:
                print(f"    ✅ Kept {len(existing_images)} existing images")
            else:
                print(f"    ❌ No images found")
            
            enhanced_products.append(product_data)
        
        # Summary
        final_with_images = len([p for p in enhanced_products if p.get('images')])
        print(f"🎯 Enhanced result: {final_with_images}/{len(enhanced_products)} products have images")
        
        return enhanced_products
        
    def _extract_product_number_from_url(self, url: str, product_name: str = None) -> Optional[str]:
        """Extract product number from URL using product name logic."""
        # Try to extract the full numeric ID from URL end
        full_id_match = re.search(r'(\d+)(?:\?|$)', url)
        if not full_id_match:
            return None
        
        full_id = full_id_match.group(1)
        
        # If we have the product name, check if there's a number after a dash/space
        if product_name:
            # Look for patterns like "Leather 100" or "Medium-100" at the end
            number_match = re.search(r'(?:^|\s|-)(\d+)(?:\s|$)', product_name)
            if number_match:
                product_number = number_match.group(1)
                return product_number
        
        # No product number found in name
        return None

    def _generate_rebag_image_urls(self, product_data: Dict[str, Any]) -> List[str]:
        """Generate potential image URLs based on Rebag's actual naming patterns."""
        base_url = "https://cdn.shopify.com/s/files/1/0384/0161/files/"
        
        # Extract data from product
        brand = product_data.get('brand', '')
        source_url = product_data.get('source_url', '')
        product_name = product_data.get('product_name', '')
        
        print(f"DEBUG: Brand='{brand}', Product Name='{product_name}', URL='{source_url}'")
        
        # Extract SKU and product number using the CORRECTED logic
        sku = self._extract_sku_from_url(source_url, product_name)
        product_number = self._extract_product_number_from_url(source_url, product_name)
        
        if not sku:
            print("DEBUG: No SKU found, returning empty list")
            return []
        
        print(f"DEBUG: Final SKU='{sku}', Product Number='{product_number}'")
        
        # FIXED: Always use SKU + suffix format, with or without product number
        # Use first 6 digits of SKU + suffix
        sku_first_6 = sku[:6] if len(sku) >= 6 else sku
        suffix = sku[6:] if len(sku) > 6 else "1"
        filename_prefix = f"{sku_first_6}-{suffix}"
        
        print(f"DEBUG: Filename prefix='{filename_prefix}'")
        
        # Format brand and model for URL
        def format_for_url(text):
            if not text:
                return ""
            
            # Handle specific cases first - PRESERVE ORIGINAL CASE
            text = text.replace("Women's", "Women_s")  # Keep apostrophe as _s
            text = text.replace("Men's", "Men_s")      # Keep apostrophe as _s
            text = text.replace("E-Canvas", "E-Canvas")  # Keep hyphen in E-Canvas
            text = text.replace("E Canvas", "E-Canvas")  # Convert space to hyphen for E-Canvas
            
            # Handle ampersand
            text = text.replace('&', '_26')  # & becomes _26
            
            # Remove other apostrophes (but not the ones we already handled)
            text = re.sub(r"(?<!Women)(?<!Men)'s?", '', text)  # Remove apostrophes not after Women/Men
            text = text.replace("'", '')   # Remove any remaining apostrophes
            
            # SIZE TRANSFORMATIONS - Apply before space conversion
            # Large → Medium
            text = re.sub(r'\bLarge\b', 'Medium', text, flags=re.IGNORECASE)
            # Mini → Small  
            text = re.sub(r'\bMini\b', 'Small', text, flags=re.IGNORECASE)
            
            # DO NOT CHANGE CASE - use the original case from the HTML product name
            # PRESERVE DECIMAL POINTS - don't remove periods that are part of numbers
            
            # Convert spaces to _20, but preserve existing hyphens and decimal points
            text = text.replace(' ', '_20')
            
            # Clean up other characters but keep hyphens for compound words and decimals
            text = text.replace(',', '')
            # DON'T remove periods - they might be decimal points like "1.4"
            # text = text.replace('.', '')  # REMOVED THIS LINE
            text = text.replace('(', '')
            text = text.replace(')', '')
            
            return text
        
        formatted_brand = format_for_url(brand)
        
        # USE THE ACTUAL PRODUCT NAME FROM HTML (preserving original case)
        # Keep the full product name - don't remove the brand
        formatted_model_original = format_for_url(product_name)
        
        # Also create a version with size transformations
        def format_for_url_with_size_transforms(text):
            if not text:
                return ""
            
            # Handle specific cases first - PRESERVE ORIGINAL CASE
            text = text.replace("Women's", "Women_s")  # Keep apostrophe as _s
            text = text.replace("Men's", "Men_s")      # Keep apostrophe as _s
            text = text.replace("E-Canvas", "E-Canvas")  # Keep hyphen in E-Canvas
            text = text.replace("E Canvas", "E-Canvas")  # Convert space to hyphen for E-Canvas
            
            # Handle ampersand
            text = text.replace('&', '_26')  # & becomes _26
            
            # Remove other apostrophes (but not the ones we already handled)
            text = re.sub(r"(?<!Women)(?<!Men)'s?", '', text)  # Remove apostrophes not after Women/Men
            text = text.replace("'", '')   # Remove any remaining apostrophes
            
            # SIZE TRANSFORMATIONS - Apply before space conversion
            # Large → Medium
            text = re.sub(r'\bLarge\b', 'Medium', text, flags=re.IGNORECASE)
            # Mini → Small  
            text = re.sub(r'\bMini\b', 'Small', text, flags=re.IGNORECASE)
            
            # Convert spaces to _20, but preserve existing hyphens and decimal points
            text = text.replace(' ', '_20')
            
            # Clean up other characters but keep hyphens for compound words and decimals
            text = text.replace(',', '')
            # DON'T remove periods - they might be decimal points like "1.4"
            text = text.replace('(', '')
            text = text.replace(')', '')
            
            return text
        
        formatted_model_transformed = format_for_url_with_size_transforms(product_name)
        
        print(f"DEBUG: Formatted brand='{formatted_brand}'")
        print(f"DEBUG: Formatted model (original)='{formatted_model_original}'")
        print(f"DEBUG: Formatted model (transformed)='{formatted_model_transformed}'")
        
        image_urls = []
        
        # Generate URLs with both original and transformed sizes
        models_to_try = [formatted_model_original]
        
        # Only add transformed version if it's different from original
        if formatted_model_transformed != formatted_model_original:
            models_to_try.append(formatted_model_transformed)
            print(f"DEBUG: Will try both original and transformed versions")
        else:
            print(f"DEBUG: No size transformation needed, using original only")
        
        if formatted_brand:
            for model_variant in models_to_try:
                # FIXED: Try multiple size variants including _508x508 which appears in your working example
                for size in ['_300x300', '_508x508', '_800x800']:
                    img_url = f"{base_url}{filename_prefix}_20{formatted_brand}_20{model_variant}_2D_0002{size}.jpg"
                    image_urls.append(img_url)
                    print(f"DEBUG: Generated URL: {img_url}")
        else:
            print(f"DEBUG: Missing formatted brand, skipping URL generation")
        
        return image_urls
    
    def _extract_images_from_product_data(self, product_data: Dict[str, Any]) -> List[str]:
        """Extract images from product data attributes, metadata, etc."""
        images = []
        
        # Check if any product attributes contain image URLs
        for key, value in product_data.items():
            if isinstance(value, str) and 'cdn.shopify.com' in value and any(ext in value for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                if self._is_valid_product_image(value):
                    images.append(value)
        
        return images

    async def _extract_product_page_images(self, soup: BeautifulSoup, product_url: str) -> List[str]:
        """Extract images from individual product page using multiple strategies."""
        images = []
        
        # Strategy 1: Product page specific selectors for Rebag
        product_image_selectors = [
            # Main product images
            '.product-image-main img',
            '.product-photos img',
            '.product-gallery img',
            '.product-images img',
            
            # Rebag specific product page selectors
            '.product-single__photos img',
            '.product-form__item img',
            '[data-product-single-media] img',
            
            # Gallery and carousel selectors
            '.product-image-gallery img',
            '.image-carousel img',
            '.product-carousel img',
            '.slick-slide img',
            
            # General product selectors
            '[class*="ProductImage"] img',
            '[class*="product-image"] img',
            '[id*="product"] img',
            
            # Shopify specific
            '.product-single__media img',
            '.media img'
        ]
        
        for selector in product_image_selectors:
            try:
                img_elements = soup.select(selector)
                for img in img_elements:
                    src = self._get_best_image_src(img)
                    if src and self._is_valid_product_image(src):
                        enhanced_src = self._enhance_image_url(src)
                        if enhanced_src not in images:
                            images.append(enhanced_src)
            except Exception as e:
                continue
        
        # Strategy 2: Look for JSON-LD structured data
        try:
            json_scripts = soup.find_all('script', {'type': 'application/ld+json'})
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        image_data = data.get('image', [])
                        if isinstance(image_data, list):
                            for img_url in image_data:
                                if isinstance(img_url, str) and self._is_valid_product_image(img_url):
                                    enhanced_url = self._enhance_image_url(img_url)
                                    if enhanced_url not in images:
                                        images.append(enhanced_url)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        
        # Strategy 3: Look for Shopify product data
        try:
            shopify_scripts = soup.find_all('script', string=re.compile(r'window\.ShopifyAnalytics|product.*images'))
            for script in shopify_scripts:
                if script.string:
                    # Look for image URLs in JavaScript
                    img_matches = re.findall(r'["\']([^"\']*\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', script.string)
                    for img_url in img_matches:
                        if self._is_valid_product_image(img_url):
                            enhanced_url = self._enhance_image_url(img_url)
                            if enhanced_url not in images:
                                images.append(enhanced_url)
        except Exception:
            pass
        
        # Strategy 4: Meta property images (OpenGraph, etc.)
        try:
            meta_images = soup.find_all('meta', {'property': re.compile(r'og:image|twitter:image')})
            for meta in meta_images:
                content = meta.get('content')
                if content and self._is_valid_product_image(content):
                    enhanced_url = self._enhance_image_url(content)
                    if enhanced_url not in images:
                        images.append(enhanced_url)
        except Exception:
            pass
        
        return images[:self.max_images_per_product]
        
        for selector in product_image_selectors:
            try:
                img_elements = soup.select(selector)
                for img in img_elements:
                    src = self._get_best_image_src(img)
                    if src and self._is_valid_product_image(src):
                        enhanced_src = self._enhance_image_url(src)
                        if enhanced_src not in images:
                            images.append(enhanced_src)
            except Exception as e:
                continue
        
        # Strategy 2: Look for JSON-LD structured data
        try:
            json_scripts = soup.find_all('script', {'type': 'application/ld+json'})
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        image_data = data.get('image', [])
                        if isinstance(image_data, list):
                            for img_url in image_data:
                                if isinstance(img_url, str) and self._is_valid_product_image(img_url):
                                    enhanced_url = self._enhance_image_url(img_url)
                                    if enhanced_url not in images:
                                        images.append(enhanced_url)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        
        # Strategy 3: Look for Shopify product data
        try:
            shopify_scripts = soup.find_all('script', string=re.compile(r'window\.ShopifyAnalytics|product.*images'))
            for script in shopify_scripts:
                if script.string:
                    # Look for image URLs in JavaScript
                    img_matches = re.findall(r'["\']([^"\']*\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', script.string)
                    for img_url in img_matches:
                        if self._is_valid_product_image(img_url):
                            enhanced_url = self._enhance_image_url(img_url)
                            if enhanced_url not in images:
                                images.append(enhanced_url)
        except Exception:
            pass
        
        # Strategy 4: Meta property images (OpenGraph, etc.)
        try:
            meta_images = soup.find_all('meta', {'property': re.compile(r'og:image|twitter:image')})
            for meta in meta_images:
                content = meta.get('content')
                if content and self._is_valid_product_image(content):
                    enhanced_url = self._enhance_image_url(content)
                    if enhanced_url not in images:
                        images.append(enhanced_url)
        except Exception:
            pass
        
        return images[:self.max_images_per_product]

    def _get_best_image_src(self, img_element) -> Optional[str]:
        """Get the best image source from an img element, checking multiple attributes."""
        # Priority order for image sources
        src_attributes = [
            'data-src',           # Lazy loading
            'data-original',      # Lazy loading
            'data-lazy-src',      # Lazy loading
            'data-zoom-image',    # High res version
            'data-large-image',   # High res version
            'src',                # Standard src
            'data-image',         # Custom data attribute
        ]
        
        for attr in src_attributes:
            src = img_element.get(attr)
            if src and src.strip() and not src.startswith('data:'):  # Avoid data URIs
                return src.strip()
        
        return None
    
    async def _process_categories_sequential(self, category_urls: List[str], brand: str, max_products: int = None) -> List[Dict[str, Any]]:
        """Process category URLs sequentially for reliability."""
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
    
    async def _extract_urls_and_product_info(self, page_url: str, brand: str, 
                                           thread_operation: str = None, 
                                           first_page_only: bool = False) -> List[Dict[str, Any]]:
        """Extract URLs and product info from Rebag pages."""
        all_products_data = []
        all_seen_urls = set()
        page_num = 1
        max_pages = 1 if first_page_only else self.MAX_PAGES_DEFAULT
        consecutive_empty_pages = 0
        
        while page_num <= max_pages and consecutive_empty_pages < self.EMPTY_PAGE_TOLERANCE:
            try:
                # Construct paginated URL for Rebag
                if page_num == 1:
                    paginated_url = page_url
                else:
                    if '?' in page_url:
                        paginated_url = f"{page_url}&page={page_num}"
                    else:
                        paginated_url = f"{page_url}?page={page_num}"
                
                print(f"📄 Loading page {page_num}: {paginated_url}")

                page_label = "first page" if first_page_only else f"page {page_num}"
                
                operation = f"{thread_operation}_page_{page_num}" if thread_operation else f"page_{page_num}"
                
                # Try multiple approaches - first with JS, then without
                result = None
                approaches = [
                    {
                        'name': 'JavaScript rendering',
                        'config': {
                            'render_js': True,
                            'rendering_wait': random.randint(15000, 20000),
                            'auto_scroll': False,
                            'js': "console.log('Starting JS execution'); await new Promise(r => setTimeout(r, 8000)); console.log('Initial wait complete'); document.querySelectorAll('.plp__product').length > 0 ? console.log('Products found:', document.querySelectorAll('.plp__product').length) : console.log('No .plp__product found, checking alternatives'); window.scrollTo(0, document.body.scrollHeight/4); await new Promise(r => setTimeout(r, 2000)); window.scrollTo(0, document.body.scrollHeight/2); await new Promise(r => setTimeout(r, 2000)); window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 3000)); window.scrollTo(0, 0); console.log('Scrolling complete');"
                        }
                    },
                    {
                        'name': 'No JavaScript',
                        'config': {
                            'render_js': False,
                        }
                    },
                    {
                        'name': 'Basic JavaScript',
                        'config': {
                            'render_js': True,
                            'rendering_wait': 10000,
                            'auto_scroll': True,
                        }
                    }
                ]
                
                for i, approach in enumerate(approaches):
                    print(f"    🔄 Trying approach {i+1}: {approach['name']}")
                    
                    # Add delay between attempts to avoid session conflicts
                    if i > 0:
                        await asyncio.sleep(2)
                    
                    try:
                        result = await self.make_request_with_session(
                            url=paginated_url,
                            brand=brand,
                            operation=f"{operation}_attempt_{i+1}_{int(time.time()*1000)}",  # Add timestamp to operation
                            **approach['config']
                        )
                        
                        if result and result.status_code == 200:
                            # Quick check for products
                            soup_check = BeautifulSoup(result.content, 'html.parser')
                            products_found = len(soup_check.select('.plp__product, [data-product-id], .product-card, a[href*="/products/"]'))
                            print(f"    📊 {approach['name']}: {products_found} products found")
                            
                            if products_found > 0:
                                print(f"    ✅ Success with {approach['name']}!")
                                break
                            elif i < len(approaches) - 1:
                                print(f"    ⚠️  No products with {approach['name']}, trying next approach...")
                                result = None
                        else:
                            print(f"    ❌ {approach['name']} failed: {result.status_code if result else 'No response'}")
                            result = None
                            
                    except Exception as e:
                        print(f"    ❌ {approach['name']} error: {str(e)[:100]}...")
                        result = None
                
                if not result or result.status_code != 200:
                    print(f"    ❌ {page_label} failed: {result.status_code if result else 'No response'}")
                    consecutive_empty_pages += 1
                    page_num += 1
                    continue

                # Debug: Check what we actually got
                print(f"    📊 Response size: {len(result.content)} characters")
                soup_debug = BeautifulSoup(result.content, 'html.parser')
                title_debug = soup_debug.find('title')
                print(f"    📄 Page title: {title_debug.text.strip() if title_debug else 'No title'}")
                
                # Check for key elements
                plp_products = soup_debug.select('.plp__product')
                any_products = soup_debug.select('[data-product-id], .product-card, .product-item')
                print(f"    🔍 .plp__product elements: {len(plp_products)}")
                print(f"    🔍 Any product elements: {len(any_products)}")

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
                
                # Handle pagination logic
                if not first_page_only and page_num > 1:
                    current_page_urls = [
                        product.get('source_url', '') for product in page_products_data 
                        if product.get('source_url')
                    ]
                    
                    new_product_urls = [url for url in current_page_urls if url not in all_seen_urls]
                                        
                    if len(new_product_urls) == 0:
                        print(f"    🛑 STOPPING: Found 0 new products on {page_label}")
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
        """Extract product info using improved Rebag-specific selectors."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Enhanced selectors for Rebag - try multiple approaches
            product_containers = soup.select('.plp__product')
            
            if not product_containers:
                print(f"    ⚠️  No products found with primary selector, trying fallbacks...")
                # Enhanced fallback selectors
                fallback_selectors = [
                    '[data-product-id]',
                    '.product-card',
                    '.product-item',
                    '.product-tile',
                    '[class*="product"]',
                    '.grid-item',
                    '[data-product-handle]',
                    'article[class*="product"]',
                    'li[class*="product"]'
                ]
                
                for selector in fallback_selectors:
                    product_containers = soup.select(selector)
                    if product_containers:
                        print(f"    ✅ Found {len(product_containers)} products with fallback: {selector}")
                        break
                
                # If still no products, run debug analysis
                if not product_containers:
                    await self._debug_page_structure(soup, page_url)
                    return []
            
            print(f"    🔗 Found {len(product_containers)} product containers")
            
            products_data = []
            for i, container in enumerate(product_containers):
                try:
                    product_data = self._extract_rebag_product_info(container, page_url, brand, gender)
                    if product_data:
                        products_data.append(product_data)
                except Exception as e:
                    print(f"    ⚠️  Error extracting product {i+1}: {e}")
                    continue
            
            print(f"    ✅ Successfully extracted {len(products_data)} products")
            return products_data
            
        except Exception as e:
            print(f"    ❌ Error extracting products: {e}")
            return []
    
    def _extract_rebag_product_info(self, container, page_url: str, brand: str, gender: str) -> Optional[Dict[str, Any]]:
        """Extract product info from Rebag product container with enhanced selectors."""
        try:
            # Extract product URL with multiple selector attempts
            link_elem = (container.select_one('a.plp__card') or 
                        container.select_one('a[href*="/products/"]') or
                        container.find('a', href=True))
            
            if not link_elem:
                return None
            
            product_url = link_elem.get('href', '')
            if not product_url:
                return None
            
            # Make URL absolute
            if product_url.startswith('/'):
                product_url = f"https://{self.SHOP_DOMAIN}{product_url}"
            elif not product_url.startswith('http'):
                product_url = f"https://{self.SHOP_DOMAIN}/{product_url}"
            
            if not self._is_valid_product_url(product_url):
                return None
            
            # Extract brand with multiple selectors
            brand_elem = (container.select_one('.products-carousel__card-designer') or
                        container.select_one('[class*="brand"]') or
                        container.select_one('[class*="designer"]'))
            extracted_brand = brand_elem.get_text(strip=True) if brand_elem else brand
            
            # Extract ACTUAL product name from the page (not from URL)
            actual_product_name = self._extract_product_name_from_container(container)
            
            # Extract condition with multiple selectors
            condition_elem = (container.select_one('.products-carousel__card-condition') or
                            container.select_one('[class*="condition"]') or
                            container.select_one('[class*="grade"]'))
            condition = condition_elem.get_text(strip=True) if condition_elem else ''
            
            # Extract price with enhanced detection
            price = self._extract_rebag_price(container)
            
            # Extract product ID from multiple sources
            product_id_attr = (container.get('data-product-id') or
                            container.get('data-id') or
                            container.get('id') or '')
            
            # Extract images with enhanced detection
            images = []
            
            # Extract SKU from URL using ACTUAL product name from page
            sku = self._extract_sku_from_url(product_url, actual_product_name)
            
            # Parse model from URL (fallback if we can't get it from product name)
            model_from_url = self._extract_model_from_url(product_url, extracted_brand)
            
            # Use actual product name if available, otherwise fall back to URL-based model
            if actual_product_name and actual_product_name != extracted_brand:
                # Remove brand from product name to get model
                model = actual_product_name.replace(extracted_brand, '').strip()
                if not model:  # If removing brand left nothing, use URL-based model
                    model = model_from_url
            else:
                model = model_from_url
            
            # Generate consistent product ID
            final_product_id = self._generate_product_id(extracted_brand, model, sku)
            
            # Use actual product name if available
            product_name = actual_product_name if actual_product_name else f"{extracted_brand} {model}"
            
            # Extract additional info with fallbacks
            tag_elem = container.select_one('.products-carousel__tag') or container.select_one('[class*="tag"]')
            tag = tag_elem.get_text(strip=True) if tag_elem else ''
            
            # Extract favorite count
            favorite_count_elem = container.select_one('.products-carousel__favorite-container--counter')
            favorite_count = 0
            if favorite_count_elem:
                try:
                    favorite_count = int(favorite_count_elem.get_text(strip=True))
                except ValueError:
                    favorite_count = 0
            
            # Extract promo message
            promo_elem = (container.select_one('.products-carousel__promo-message') or
                        container.select_one('[class*="promo"]') or
                        container.select_one('[class*="sale"]'))
            promo_message = promo_elem.get_text(strip=True) if promo_elem else ''
            
            return {
                'product_id': final_product_id,
                'brand': extracted_brand,
                'model': model,
                'sku': sku,
                'price': price,
                'product_name': product_name,
                'condition': condition,
                'description': f"{condition} {promo_message}".strip(),
                'images': images,
                'source_url': product_url,
                'tag': tag,
                'favorite_count': favorite_count,
                'promo_message': promo_message
            }
            
        except Exception as e:
            print(f"    ⚠️  Error extracting product info: {e}")
            return None
    
    def _extract_rebag_price(self, container) -> Optional[int]:
        """Extract price from Rebag container using enhanced selectors."""
        # Enhanced price selectors
        price_selectors = [
            '.rewards-plus-plp__product-price-value',
            '.rewards-plus-plp__original-price-label',
            '[class*="price"]',
            '[data-testid*="price"]',
            '.money',
            '[class*="cost"]',
            '[class*="amount"]',
            '[data-price]',
            '.price-current',
            '.price-regular',
            '.product-price',
            '.price-value'
        ]
        
        for selector in price_selectors:
            price_elem = container.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                parsed_price = self._parse_price_text(price_text)
                if parsed_price:
                    return parsed_price
        
        # Fallback: look for any text that contains dollar amounts
        all_text = container.get_text()
        dollar_matches = re.findall(r'\$(\d{1,3}(?:,\d{3})*|\d+)', all_text)
        if dollar_matches:
            try:
                price_str = dollar_matches[0].replace(',', '')
                return int(price_str)
            except ValueError:
                pass
        
        return None
    
    def _extract_product_name_from_container(self, container) -> Optional[str]:
        """Extract the actual product name from the product container on the listing page."""
        # Try multiple selectors to find the product name/title
        title_selectors = [
            # Rebag specific selectors
            '.products-carousel__card-title',
            '.products-carousel__card-name',
            '.plp__card-title',
            '.plp__product-title',
            
            # Generic product title selectors
            '.product-title',
            '.product-name',
            '.card-title',
            '.title',
            'h2',
            'h3',
            '[class*="title"]',
            '[class*="name"]',
            '[data-testid*="title"]',
            '[data-testid*="name"]',
            
            # Fallback: look in any text elements
            'a[href*="/products/"]',  # The link text itself
        ]
        
        for selector in title_selectors:
            try:
                elem = container.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 3:  # Make sure we have meaningful text
                        return text
            except Exception as e:
                continue
        
        # If no title found in specific selectors, try to get it from the link text
        try:
            link_elem = container.select_one('a[href*="/products/"]')
            if link_elem:
                # Try title attribute first
                title_attr = link_elem.get('title')
                if title_attr and title_attr.strip():
                    return title_attr.strip()
                
                # Try aria-label
                aria_label = link_elem.get('aria-label')
                if aria_label and aria_label.strip():
                    return aria_label.strip()
        except Exception:
            pass
        
        print("DEBUG: Could not extract product name from container")
        return None
    
    def _extract_model_from_url(self, product_url: str, brand: str) -> str:
        """Extract clean model name from product URL slug."""
        if '/products/' not in product_url:
            return "Unknown Product"
        
        # Extract the slug part
        slug = product_url.split('/products/')[-1].split('?')[0]
        
        # Remove category prefixes and SKU suffix
        slug_parts = slug.split('-')
        
        # Remove first part (category like 'handbags', 'shoes', 'apparel')
        if len(slug_parts) > 1:
            slug_parts = slug_parts[1:]
        
        # Remove brand from beginning if present
        brand_words = brand.lower().split()
        while slug_parts and slug_parts[0].lower() in brand_words:
            slug_parts = slug_parts[1:]
        
        # Remove last part if it's all digits (SKU)
        if slug_parts:
            last_part = slug_parts[-1]
            # If the last part ends with digits, remove the digits
            import re
            cleaned_last = re.sub(r'\d+$', '', last_part)
            if cleaned_last:
                slug_parts[-1] = cleaned_last
            elif last_part.isdigit():
                slug_parts = slug_parts[:-1]
        
        # Join remaining parts and clean up
        if slug_parts:
            model = '-'.join(slug_parts).replace('-', ' ').title()
            return model
        else:
            return "Unknown Product"
    
    def _parse_price_text(self, price_text: str) -> Optional[int]:
        """Parse price text into integer."""
        if not price_text:
            return None
        
        # Remove currency symbols and clean
        price_cleaned = re.sub(r'[^\d,.]', '', price_text)
        
        # Handle different price formats
        price_match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', price_cleaned)
        if price_match:
            try:
                price_str = price_match.group(1).replace(',', '')
                return int(price_str)
            except ValueError:
                pass
        
        return None
    
    def _enhance_image_url(self, img_url: str) -> str:
        """Enhanced image URL conversion for Rebag/Shopify."""
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = f'https://{self.SHOP_DOMAIN}{img_url}'
        
        # Shopify size conversions - upgrade to larger sizes
        size_patterns = [
            # Standard size upgrades
            ('_300x300.', '_800x800.'),
            ('_400x400.', '_800x800.'),
            ('_500x500.', '_800x800.'),
            ('_600x600.', '_800x800.'),
            
            # Named size upgrades
            ('_small.', '_large.'),
            ('_medium.', '_large.'),
            ('_compact.', '_master.'),
            ('_thumb.', '_large.'),
            
            # Query parameter upgrades
            ('?width=300', '?width=800'),
            ('?width=400', '?width=800'),
        ]
        
        for old_size, new_size in size_patterns:
            if old_size in img_url:
                img_url = img_url.replace(old_size, new_size)
                break
        
        return img_url
    
    def _extract_sku_from_url(self, url: str, product_name: str = None) -> Optional[str]:
        """Extract SKU from product URL using product name logic."""
        # Try to extract the full numeric ID from URL end
        full_id_match = re.search(r'(\d+)(?:\?|$)', url)
        if not full_id_match:
            return None
        
        full_id = full_id_match.group(1)
        
        # If we have the product name, check if there's a number after a dash/space
        if product_name:
            # Look for patterns like "Leather 100" or "Medium-100" at the end
            number_match = re.search(r'(?:^|\s|-)(\d+)(?:\s|$)', product_name)
            if number_match:
                product_number = number_match.group(1)
                
                # FIXED: Remove the product number from the BEGINNING of full ID to get SKU
                if full_id.startswith(product_number):
                    sku = full_id[len(product_number):]
                    return sku if sku else full_id  # Return full_id if sku is empty
                # Don't check endswith - product numbers appear at start of ID
        
        # Default case - no number found in product name, use full ID as SKU
        return full_id
    
    def _is_valid_product_image(self, img_url: str) -> bool:
        """Validate product image URL for Rebag."""
        if not img_url:
            return False
        
        img_url_lower = img_url.lower()
        
        # Must be from valid domains
        valid_domains = [
            'cdn.shopify.com',
            'shop.rebag.com',
            'rebag.com',
            'shopifycdn.com'
        ]
        
        if not any(domain in img_url_lower for domain in valid_domains):
            return False
        
        # Must have image extension
        if not any(ext in img_url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            return False
        
        # Skip non-product images
        skip_patterns = [
            'logo', 'icon', 'banner', 'favicon', 'sprite',
            'button', 'arrow', 'close', 'search', 'cart',
            'loading', 'spinner', 'placeholder'
        ]
        
        return not any(pattern in img_url_lower for pattern in skip_patterns)
    
    def _is_valid_product_url(self, url: str) -> bool:
        """Check if URL is a valid Rebag product page."""
        return bool(url and 
                   (self.SITE_DOMAIN in url or self.SHOP_DOMAIN in url) and 
                   '/products/' in url and
                   not any(invalid in url.lower() for invalid in ['cart', 'checkout', 'account']))
    
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
                    products_for_download, batch_size=25  # Conservative batch size for Rebag
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
        """Convert scraped data to Product objects with optimized categorization."""
        from ..utils.ai_categorizer import ai_categorizer
        
        conversion_start = time.time()
        
        # Quick image stats
        products_with_images = len([p for p in products_data if p.get('images')])
        products_without_images = len(products_data) - products_with_images
        print(f"🤖 Running AI categorization for {len(products_data)} products...")
        print(f"📸 Image stats: {products_with_images} with images, {products_without_images} without")
        
        # try:
        #     # For small batches, use enhanced keyword categorization
        #     if len(products_data) <= 5:
        #         print(f"⚡ Using enhanced keyword categorization for small batch ({len(products_data)} products)")
        #         categories = []
        #         for data in products_data:
        #             category = self._categorize_rebag_product(data)
        #             categories.append(category)
        #     else:
        #         # Use AI for larger batches
        #         categories = await ai_categorizer.categorize_products_batch(products_data)
                
        # except Exception as e:
        #     print(f"⚠️  AI categorization failed: {e}")
        #     # Fallback categorization
        #     categories = []
        #     for data in products_data:
        #         category = self._categorize_rebag_product(data)
        #         categories.append(category)
        
        # categorization_time = time.time() - conversion_start
        # print(f"⚡ Categorization completed in {categorization_time:.1f}s ({categorization_time/len(products_data):.2f}s per product)")
        
        products = []
        for i, data in enumerate(products_data):
            try:
                # category = categories[i] if i < len(categories) else 'bags'
                
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
                
                # Enhanced product creation with additional fields
                product = Product(
                    product_id=data.get('product_id', ''),
                    brand=data['brand'],
                    model=data['model'],
                    sku=[data['sku']] if data.get('sku') else [],
                    product_name=data['product_name'],
                    source_url=[data['source_url']],
                    images=images,
                    category=None,  # No AI categorization
                    price=data.get('price'),
                    description=data.get('description', ''),
                    condition=data.get('condition', ''),
                    # Add Rebag-specific metadata
                    metadata={
                        'tag': data.get('tag', ''),
                        'favorite_count': data.get('favorite_count', 0),
                        'promo_message': data.get('promo_message', ''),
                        'site': 'rebag'
                    }
                )
                
                products.append(product)
                
            except Exception as e:
                print(f"⚠️  Error creating Product object for {data.get('product_name', 'unknown')}: {e}")
                continue
        
        conversion_time = time.time() - conversion_start
        print(f"✅ Successfully categorized and created {len(products)} products!")
        print(f"⏱️  Product conversion took {conversion_time:.1f}s ({conversion_time/len(products):.2f}s per product)")
        return products
    
    def _categorize_rebag_product(self, data: Dict[str, Any]) -> str:
        """Enhanced categorization for Rebag products using multiple signals."""
        product_name = data.get('product_name', '').lower()
        model = data.get('model', '').lower()
        tag = data.get('tag', '').lower()
        description = data.get('description', '').lower()
        
        # Combine all text for analysis
        all_text = f"{product_name} {model} {tag} {description}"
        
        # Enhanced category mapping for luxury goods
        category_keywords = {
            'bags': [
                'bag', 'handbag', 'purse', 'tote', 'clutch', 'satchel', 
                'backpack', 'crossbody', 'shoulder bag', 'hobo', 'bucket',
                'messenger', 'bowling', 'doctor bag', 'saddle', 'flap',
                'envelope', 'pouch', 'mini bag', 'micro bag', 'camera bag',
                'kelly', 'birkin', 'constance', 'evelyne', 'picotin'  # Hermès bags
            ],
            'jewelry': [
                'necklace', 'bracelet', 'ring', 'earring', 'jewelry',
                'pendant', 'chain', 'charm', 'bangle', 'cuff', 'choker',
                'anklet', 'brooch', 'pin', 'stud', 'hoop', 'drop earring',
                'tennis bracelet', 'love bracelet', 'clou', 'juste un clou'
            ],
            'watches': [
                'watch', 'timepiece', 'chronograph', 'smartwatch',
                'tank', 'santos', 'ballon bleu', 'panthere', 'roadster',
                'calibre', 'rotonde', 'drive', 'pasha', 'submariner',
                'datejust', 'rolex', 'cartier', 'omega', 'patek philippe'
            ],
            'shoes': [
                'shoe', 'sneaker', 'boot', 'heel', 'flat', 'sandal',
                'pump', 'loafer', 'oxford', 'trainer', 'ankle boot',
                'knee boot', 'stiletto', 'wedge', 'platform', 'slipper',
                'mule', 'espadrille', 'ballet flat'
            ],
            'wallets': [
                'wallet', 'card holder', 'cardholder', 'card case',
                'coin purse', 'money clip', 'billfold', 'zip wallet',
                'tri-fold', 'bi-fold', 'wristlet'
            ],
            'accessories': [
                'scarf', 'belt', 'keychain', 'key holder', 'sunglasses',
                'hair accessory', 'phone case', 'charm', 'pin', 'badge',
                'cufflink', 'tie clip', 'money clip', 'hat', 'cap',
                'gloves', 'headband'
            ],
            'apparel': [
                'jacket', 'coat', 'sweater', 'shirt', 'dress', 'skirt',
                'pants', 'jeans', 'blazer', 'cardigan', 'vest', 'hoodie',
                'top', 'blouse', 'suit', 'jumpsuit', 'kimono', 'poncho'
            ]
        }
        
        # Count keyword matches for each category
        category_scores = {}
        for category, keywords in category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in all_text)
            if score > 0:
                category_scores[category] = score
        
        # Return category with highest score, default to bags for Rebag
        if category_scores:
            return max(category_scores.items(), key=lambda x: x[1])[0]
        else:
            return 'bags'  # Default for Rebag since they specialize in luxury bags
    
    async def _debug_page_structure(self, soup, url: str):
        """Debug method to analyze page structure when no products are found."""
        print(f"\n🔍 DEBUG: Analyzing page structure for {url}")
        
        # Check if page loaded correctly
        title = soup.find('title')
        print(f"    📄 Page title: {title.text.strip() if title else 'No title found'}")
        
        # Look for common product container patterns
        potential_selectors = [
            'div[data-testid*="product"]',
            'div[class*="product"]',
            'article[class*="product"]',
            '.product-item',
            '.product-card',
            '.product-tile',
            '[data-product-id]',
            '[data-product-handle]',
            'div[class*="grid"] > div',
            'div[class*="collection"] > div',
            'li[class*="product"]',
            'a[href*="/products/"]',
            '.plp__product'  # Rebag specific
        ]
        
        print("    🎯 Testing potential product selectors:")
        for selector in potential_selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    # Show first element's classes and attributes
                    first_elem = elements[0]
                    classes = first_elem.get('class', [])
                    attrs = {k: v for k, v in first_elem.attrs.items() if k != 'class'}
                    print(f"           First element classes: {classes}")
                    if attrs:
                        print(f"           First element attributes: {attrs}")
                else:
                    print(f"        ❌ {selector}: No elements found")
            except Exception as e:
                print(f"        ⚠️  {selector}: Error - {e}")
        
        # Check for JavaScript-rendered content indicators
        js_indicators = [
            'script[src*="shopify"]',
            'script[src*="react"]',
            'script[src*="vue"]',
            'div[id*="app"]',
            'div[id*="root"]',
            '[data-reactroot]'
        ]
        
        print("    🔧 Checking for JavaScript framework indicators:")
        for selector in js_indicators:
            elements = soup.select(selector)
        
        # Sample some div elements to understand structure
        all_divs = soup.find_all('div', limit=50)
        print(f"    📊 Found {len(all_divs)} div elements (showing first 10 with interesting classes):")
        
        interesting_divs = []
        for div in all_divs:
            classes = div.get('class', [])
            if classes:
                class_str = ' '.join(classes)
                if any(keyword in class_str.lower() for keyword in ['product', 'item', 'card', 'tile', 'grid', 'collection', 'plp']):
                    interesting_divs.append((div, class_str))
        
        for i, (div, class_str) in enumerate(interesting_divs[:10]):
            print(f"        {i+1}. Classes: {class_str}")
            # Show any data attributes
            data_attrs = {k: v for k, v in div.attrs.items() if k.startswith('data-')}
            if data_attrs:
                print(f"           Data attributes: {data_attrs}")