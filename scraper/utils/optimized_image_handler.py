# scraper/utils/optimized_image_handler.py
"""Optimized image handler for large-scale operations with concurrent downloads and smart batching."""

import os
import hashlib
import aiohttp
import asyncio
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import logging
import re

class OptimizedImageHandler:
    """Highly optimized image handler for large-scale operations with proper session management."""
    
    def __init__(self, base_image_dir: str = "images", max_concurrent: int = 25, 
                max_images_per_product: int = 2, timeout: int = 30):  # Increased timeout
        self.base_image_dir = Path(base_image_dir)
        self.base_image_dir.mkdir(exist_ok=True)
        
        # More conservative settings for stability
        self.max_concurrent = max_concurrent  # Reduced concurrent downloads
        self.max_images_per_product = max_images_per_product
        self.timeout = timeout  # Increased timeout for reliability
        
        # Session will be created in __aenter__
        self.session = None
        self.connector = None
        
        # Enhanced headers with rotation
        self.headers_pool = [
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/avif,image/apng,image/*,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'DNT': '1',
                'Referer': 'https://www.farfetch.com/',
            },
            {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/avif,image/apng,image/*,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'DNT': '1',
                'Referer': 'https://www.farfetch.com/',
            }
        ]
        
        self.current_header_index = 0
        
        # Performance tracking
        self.download_stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'total_size': 0,
            'total_time': 0
        }
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        print(f"🖼️  Image handler initialized (max {max_images_per_product} images per product, {max_concurrent} concurrent)")

    def get_rotating_headers(self) -> dict:
        """Get headers with rotation to avoid detection."""
        headers = self.headers_pool[self.current_header_index].copy()
        self.current_header_index = (self.current_header_index + 1) % len(self.headers_pool)
        return headers

    # Also update the connector settings in __aenter__:
    async def __aenter__(self):
        """Async context manager entry - create session with optimized settings."""
        # Create connector with more conservative settings
        self.connector = aiohttp.TCPConnector(
            limit=60,  # Reduced total connection pool size
            limit_per_host=20,  # Reduced max connections per host
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=60,  # Increased keepalive
            enable_cleanup_closed=True,
            force_close=False,
            ssl=False
        )
        
        # Create session with longer timeouts
        timeout = aiohttp.ClientTimeout(
            total=self.timeout,  # Now 30 seconds
            connect=15,  # Increased connect timeout
            sock_read=20  # Increased read timeout
        )
        
        self.session = aiohttp.ClientSession(
            connector=self.connector,
            headers=self.get_rotating_headers(),  # Use rotating headers
            timeout=timeout,
            trust_env=True
        )
        
        # Reset stats for this session
        self.download_stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'total_size': 0,
            'total_time': 0
        }
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - properly close session."""
        if self.session and not self.session.closed:
            await self.session.close()
        
        if self.connector:
            await self.connector.close()
            
        # Small delay to ensure cleanup
        await asyncio.sleep(0.1)
    
    def generate_image_id(self, product_id: str, image_url: str, index: int, thread_context: str = None) -> str:
        """Generate a unique image ID efficiently with optional thread context."""
        url_hash = hashlib.md5(image_url.encode()).hexdigest()[-8:]
        
        # ✅ FIX: Add thread context to image ID for uniqueness without affecting directory
        if thread_context:
            return f"{product_id}_t{thread_context}_img_{index+1}_{url_hash}"
        return f"{product_id}_img_{index+1}_{url_hash}"
    
    def get_file_extension(self, image_url: str, content_type: Optional[str] = None) -> str:
        """Get appropriate file extension quickly."""
        if content_type:
            if 'webp' in content_type.lower():
                return '.webp'
            elif 'png' in content_type.lower():
                return '.png'
            elif 'gif' in content_type.lower():
                return '.gif'
            elif 'jpeg' in content_type.lower() or 'jpg' in content_type.lower():
                return '.jpg'
        
        # Fallback to URL analysis
        if '.webp' in image_url.lower():
            return '.webp'
        elif '.png' in image_url.lower():
            return '.png'
        elif '.gif' in image_url.lower():
            return '.gif'
        else:
            return '.jpg'  # Default to jpg
    
    def create_brand_directory(self, brand: str) -> Path:
        """Create brand directory efficiently - FIXED to handle thread-polluted brand names."""
        # ✅ FIX: Clean thread pollution from brand name
        clean_brand = brand.lower()
        
        # Remove thread pollution patterns like "_thread_0", "_thread_1", etc.
        clean_brand = re.sub(r'_thread_\d+', '', clean_brand)
        
        # Standard cleaning
        clean_brand = clean_brand.replace(' ', '_').replace('-', '_')[:30]
        clean_brand = re.sub(r'[^a-zA-Z0-9_]', '_', clean_brand)
        
        brand_dir = self.base_image_dir / clean_brand
        brand_dir.mkdir(exist_ok=True)
        return brand_dir
    
    async def download_single_image_optimized(self, image_url: str, image_id: str, 
                                            brand_dir: Path) -> Optional[Dict[str, Any]]:
        """Download a single image with maximum optimization and proper error handling."""
        if not self.session or self.session.closed:
            self.logger.error("Session is closed or not initialized")
            self.download_stats['failed_downloads'] += 1
            return None
        
        start_time = time.time()
        
        try:
            # Quick file existence check with multiple extensions
            for ext in ['.jpg', '.png', '.webp', '.gif']:
                potential_file = brand_dir / f"{image_id}{ext}"
                if potential_file.exists():
                    return {
                        'image_id': image_id,
                        'image_url': image_url,
                        'local_path': str(potential_file.relative_to(self.base_image_dir)),
                        'filename': potential_file.name,
                        'file_size': potential_file.stat().st_size,
                        'downloaded': True,
                        'cached': True
                    }
            
            # Download with error handling and retries
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    async with self.session.get(image_url) as response:
                        if response.status != 200:
                            if attempt == max_retries - 1:  # Last attempt
                                self.logger.warning(f"HTTP {response.status} for {image_url}")
                                self.download_stats['failed_downloads'] += 1
                                return None
                            continue
                        
                        # Get content efficiently
                        content = await response.read()
                        
                        if len(content) < 1000:  # Skip tiny images
                            if attempt == max_retries - 1:
                                self.logger.warning(f"Image too small ({len(content)} bytes): {image_url}")
                                self.download_stats['failed_downloads'] += 1
                                return None
                            continue
                        
                        # Determine file extension
                        content_type = response.headers.get('content-type', '')
                        file_extension = self.get_file_extension(image_url, content_type)
                        
                        # Save file
                        filename = f"{image_id}{file_extension}"
                        file_path = brand_dir / filename
                        
                        # Write file efficiently
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        
                        # Update stats
                        download_time = time.time() - start_time
                        self.download_stats['successful_downloads'] += 1
                        self.download_stats['total_size'] += len(content)
                        self.download_stats['total_time'] += download_time
                        
                        return {
                            'image_id': image_id,
                            'image_url': image_url,
                            'local_path': str(file_path.relative_to(self.base_image_dir)),
                            'filename': filename,
                            'file_size': len(content),
                            'downloaded': True,
                            'download_time': download_time,
                            'cached': False
                        }
                        
                except aiohttp.ClientError as e:
                    if attempt == max_retries - 1:
                        self.logger.warning(f"Client error downloading {image_url}: {e}")
                        self.download_stats['failed_downloads'] += 1
                        return None
                    await asyncio.sleep(0.5)  # Brief delay before retry
                    continue
                
        except asyncio.TimeoutError:
            self.download_stats['failed_downloads'] += 1
            self.logger.warning(f"Timeout downloading {image_url}")
            return None
        except Exception as e:
            self.download_stats['failed_downloads'] += 1
            self.logger.warning(f"Unexpected error downloading {image_url}: {e}")
            return None
    
    async def download_images_batch(self, products_batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Download images for a batch of products concurrently with proper session management."""
        if not self.session or self.session.closed:
            raise RuntimeError("Session is not properly initialized. Use async context manager: async with OptimizedImageHandler() as handler:")
        
        # Collect all download tasks
        download_tasks = []
        product_image_mapping = {}  # Track which images belong to which product
        
        for product_idx, product in enumerate(products_batch):
            brand = product.get('brand', 'unknown')
            product_id = product.get('product_id', f'product_{product_idx}')
            image_urls = product.get('image_urls', [])
            
            # Strictly limit images per product to max_images_per_product (default 2)
            limited_urls = image_urls[:self.max_images_per_product]
            
            if not limited_urls:
                continue
            
            # Create brand directory
            brand_dir = self.create_brand_directory(brand)
            
            # Create download tasks for this product
            for img_idx, image_url in enumerate(limited_urls):
                image_id = self.generate_image_id(product_id, image_url, img_idx)
                
                task = self.download_single_image_optimized(image_url, image_id, brand_dir)
                download_tasks.append(task)
                
                # Track mapping
                product_image_mapping[len(download_tasks) - 1] = (product_idx, img_idx)
        
        if not download_tasks:
            return products_batch
        
        # Execute downloads with concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def controlled_download(task):
            async with semaphore:
                return await task
        
        # Run all downloads concurrently
        print(f"🚀 Downloading {len(download_tasks)} images across {len(products_batch)} products (max {self.max_images_per_product} per product)...")
        start_time = time.time()
        
        results = await asyncio.gather(*[controlled_download(task) for task in download_tasks], 
                                     return_exceptions=True)
        
        download_time = time.time() - start_time
        successful_downloads = sum(1 for r in results if isinstance(r, dict) and r.get('downloaded'))
        print(f"⚡ Downloaded {len(download_tasks)} images in {download_time:.1f}s ({successful_downloads} successful, {len(download_tasks)/download_time:.1f} imgs/sec)")
        
        # Map results back to products
        enhanced_products = []
        for product_idx, product in enumerate(products_batch):
            enhanced_product = product.copy()
            enhanced_product['images'] = []
            
            # Find images for this product
            for result_idx, result in enumerate(results):
                if result_idx in product_image_mapping:
                    mapped_product_idx, mapped_img_idx = product_image_mapping[result_idx]
                    
                    if mapped_product_idx == product_idx:
                        if isinstance(result, dict) and result.get('image_id'):  # Successful download
                            enhanced_product['images'].append(result)
                        # Skip failed downloads (exceptions or None)
            
            enhanced_products.append(enhanced_product)
        
        return enhanced_products
    
    async def download_images_streaming(self, products: List[Dict[str, Any]], 
                                      batch_size: int = 100) -> List[Dict[str, Any]]:
        """Download images in streaming batches for memory efficiency."""
        total_products = len(products)
        all_enhanced_products = []
        
        print(f"📦 Processing {total_products} products in batches of {batch_size} (max {self.max_images_per_product} images per product)")
        
        for batch_start in range(0, total_products, batch_size):
            batch_end = min(batch_start + batch_size, total_products)
            batch = products[batch_start:batch_end]
            
            print(f"🔄 Processing batch {batch_start//batch_size + 1}: products {batch_start+1}-{batch_end}")
            
            # Process batch
            enhanced_batch = await self.download_images_batch(batch)
            all_enhanced_products.extend(enhanced_batch)
            
            # Show progress
            completed = len(all_enhanced_products)
            progress = (completed / total_products) * 100
            print(f"📊 Progress: {completed}/{total_products} ({progress:.1f}%)")
            
            # Brief pause between batches to prevent overwhelming
            if batch_end < total_products:
                await asyncio.sleep(0.1)
        
        return all_enhanced_products
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get detailed performance statistics."""
        stats = self.download_stats.copy()
        
        if stats['total_downloads'] > 0:
            stats['success_rate'] = (stats['successful_downloads'] / stats['total_downloads']) * 100
            stats['average_download_time'] = stats['total_time'] / stats['successful_downloads'] if stats['successful_downloads'] > 0 else 0
            stats['average_file_size'] = stats['total_size'] / stats['successful_downloads'] if stats['successful_downloads'] > 0 else 0
            stats['download_speed_mb_per_sec'] = (stats['total_size'] / (1024 * 1024)) / stats['total_time'] if stats['total_time'] > 0 else 0
        
        return stats
    
    def reset_stats(self):
        """Reset performance statistics."""
        self.download_stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'total_size': 0,
            'total_time': 0
        }


# Convenience function for quick usage with 2 images per product by default
async def download_images_fast(products: List[Dict[str, Any]], 
                              max_concurrent: int = 15,
                              max_images_per_product: int = 2,  # Default to 2 images
                              batch_size: int = 50) -> List[Dict[str, Any]]:
    """Fast batch image download for multiple products with proper session management."""
    
    async with OptimizedImageHandler(
        max_concurrent=max_concurrent,
        max_images_per_product=max_images_per_product,
        timeout=15  # Longer timeout for reliability
    ) as handler:
        
        enhanced_products = await handler.download_images_streaming(
            products, batch_size=batch_size
        )
        
        # Print final stats
        stats = handler.get_performance_stats()
        print(f"\n📊 FINAL DOWNLOAD STATISTICS:")
        print(f"✅ Successful: {stats.get('successful_downloads', 0)}")
        print(f"❌ Failed: {stats.get('failed_downloads', 0)}")
        print(f"📈 Success Rate: {stats.get('success_rate', 0):.1f}%")
        print(f"💾 Total Size: {(stats.get('total_size', 0) / (1024*1024)):.2f} MB")
        print(f"⚡ Speed: {stats.get('download_speed_mb_per_sec', 0):.2f} MB/sec")
        print(f"🖼️  Max images per product: {max_images_per_product}")
        
        return enhanced_products


# Performance test function
async def test_optimized_performance():
    """Test the optimized image handler performance with 2 images per product."""
    
    # Create test data
    test_products = []
    for i in range(20):  # Test with 20 products
        test_products.append({
            'product_id': f'test_product_{i}',
            'brand': f'TestBrand{i % 3}',  # 3 different brands
            'image_urls': [
                f'https://via.placeholder.com/400x400/FF0000/FFFFFF?text=Product{i}_Image{j}'
                for j in range(4)  # 4 images per product, but will be limited to 2
            ]
        })
    
    print(f"🧪 Testing optimized image handler with {len(test_products)} products (max 2 images per product)")
    
    start_time = time.time()
    
    enhanced_products = await download_images_fast(
        test_products,
        max_concurrent=15,
        max_images_per_product=2,  # Limit to 2 images
        batch_size=10
    )
    
    total_time = time.time() - start_time
    
    # Count results
    total_images = sum(len(p.get('images', [])) for p in enhanced_products)
    downloaded_images = sum(
        len([img for img in p.get('images', []) if img.get('downloaded')]) 
        for p in enhanced_products
    )
    
    print(f"\n🎯 PERFORMANCE TEST RESULTS:")
    print(f"⏱️  Total Time: {total_time:.1f} seconds")
    print(f"📦 Products: {len(enhanced_products)}")
    print(f"📸 Images: {total_images} ({downloaded_images} downloaded)")
    print(f"🚀 Speed: {len(enhanced_products)/total_time:.1f} products/sec")
    print(f"⚡ Image Speed: {downloaded_images/total_time:.1f} images/sec")
    print(f"🖼️  Average images per product: {total_images / len(enhanced_products) if enhanced_products else 0:.1f}")


if __name__ == "__main__":
    asyncio.run(test_optimized_performance())