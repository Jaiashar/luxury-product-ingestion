"""Enhanced AWS storage with fixed S3 upload and better product matching."""

import boto3
import json
import os
import random
import time
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path

class OptimizedAWSStorage:
    """Enhanced AWS storage with fixed S3 upload and better product matching."""
    
    def __init__(self):
        # Initialize AWS clients
        self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        self.s3 = boto3.client('s3', region_name='us-east-1')
        
        # Configuration from environment variables
        self.products_table_name = os.environ['DYNAMODB_TABLE_NAME']
        self.failures_table_name = os.environ['FAILURES_TABLE_NAME']
        self.bucket_name = os.environ['S3_BUCKET_NAME']
        
        # Get or create tables
        self.products_table = self.dynamodb.Table(self.products_table_name)
        self.failures_table = self.dynamodb.Table(self.failures_table_name)
        
        # Batch processing settings - REDUCED for better reliability
        self.MAX_CONCURRENT_UPLOADS = 25  # Reduced from 50 to prevent timeouts
        self.BATCH_SIZE = 50  # Reduced from 100
        self.MAX_RETRIES = 3
        self.UPLOAD_TIMEOUT = 90  # Increased from 60 seconds
        
        # Statistics
        self.upload_stats = {
            'total_attempted': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'total_size': 0,
            'total_time': 0
        }
        
        print(f"📄 Products table: {self.products_table_name}")
        print(f"📄 Failures table: {self.failures_table_name}")
        print(f"📦 S3 bucket: {self.bucket_name}")
        print(f"⚙️  Max concurrent uploads: {self.MAX_CONCURRENT_UPLOADS}")
    
    def setup_infrastructure(self):
        """Create DynamoDB tables and S3 bucket if they don't exist."""
        # Create Products table with URL-based key
        try:
            self.dynamodb.create_table(
                TableName=self.products_table_name,
                KeySchema=[
                    {'AttributeName': 'source_url', 'KeyType': 'HASH'},
                    {'AttributeName': 'site', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'source_url', 'AttributeType': 'S'},
                    {'AttributeName': 'site', 'AttributeType': 'S'},
                    {'AttributeName': 'brand', 'AttributeType': 'S'},
                    {'AttributeName': 'created_at', 'AttributeType': 'S'}
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'BrandIndex',
                        'KeySchema': [
                            {'AttributeName': 'brand', 'KeyType': 'HASH'},
                            {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            print("✅ Created Products table with URL-based keys")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("✅ Products table already exists")
            else:
                print(f"❌ Products table error: {e}")
        
        # Create Failures table
        try:
            self.dynamodb.create_table(
                TableName=self.failures_table_name,
                KeySchema=[
                    {'AttributeName': 'failure_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'failure_id', 'AttributeType': 'S'},
                    {'AttributeName': 'brand', 'AttributeType': 'S'},
                    {'AttributeName': 'site', 'AttributeType': 'S'},
                    {'AttributeName': 'created_at', 'AttributeType': 'S'}
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'BrandSiteIndex',
                        'KeySchema': [
                            {'AttributeName': 'brand', 'KeyType': 'HASH'},
                            {'AttributeName': 'site', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    },
                    {
                        'IndexName': 'TimeIndex',
                        'KeySchema': [
                            {'AttributeName': 'created_at', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            print("✅ Created Failures table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("✅ Failures table already exists")
            else:
                print(f"❌ Failures table error: {e}")
        
        # Create S3 bucket
        try:
            self.s3.create_bucket(Bucket=self.bucket_name)
            print("✅ Created S3 bucket")
        except Exception as e:
            if "already exists" in str(e).lower() or "already owned" in str(e).lower():
                print("✅ S3 bucket already exists")
            else:
                print(f"❌ S3 error: {e}")
    
    async def upload_images_to_s3_optimized_fixed(self, products: List[Any], site: str) -> Dict[str, int]:
        """
        FIXED S3 upload that properly matches products with their uploaded images.
        This version ensures the S3 URLs are correctly associated with the right products.
        """
        print(f"☁️  Starting FIXED optimized S3 upload for {len(products)} products...")
        
        # Reset stats
        self.upload_stats = {
            'total_attempted': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'total_size': 0,
            'total_time': 0
        }
        
        start_time = time.time()
        
        # Create a mapping between products and their upload tasks
        product_image_mapping = []
        
        # Process products in batches
        for batch_start in range(0, len(products), self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, len(products))
            batch = products[batch_start:batch_end]
            
            print(f"📦 Processing batch {batch_start//self.BATCH_SIZE + 1}: products {batch_start+1}-{batch_end}")
            
            # Process this batch and get the mapping results
            batch_mapping = await self._upload_batch_to_s3_fixed(batch, site)
            product_image_mapping.extend(batch_mapping)
            
            # Brief pause between batches
            if batch_end < len(products):
                await asyncio.sleep(0.5)
        
        # Update products with their S3 URLs using the mapping
        self._update_products_with_s3_urls_fixed(products, product_image_mapping)
        
        total_time = time.time() - start_time
        self.upload_stats['total_time'] = total_time
        
        # Print final statistics
        print(f"\n📊 FIXED S3 UPLOAD STATISTICS:")
        print(f"✅ Successful uploads: {self.upload_stats['successful_uploads']}")
        print(f"❌ Failed uploads: {self.upload_stats['failed_uploads']}")
        print(f"📈 Success rate: {(self.upload_stats['successful_uploads'] / max(1, self.upload_stats['total_attempted'])) * 100:.1f}%")
        print(f"💾 Total size: {self.upload_stats['total_size'] / (1024*1024):.2f} MB")
        print(f"⏱️  Total time: {total_time:.1f}s")
        print(f"⚡ Upload speed: {(self.upload_stats['total_size'] / (1024*1024)) / max(1, total_time):.2f} MB/s")
        
        return {
            'uploaded': self.upload_stats['successful_uploads'],
            'failed': self.upload_stats['failed_uploads']
        }
    
    async def _upload_batch_to_s3_fixed(self, products_batch: List[Any], site: str) -> List[Dict[str, Any]]:
        """Upload a batch of products' images with FIXED product-image association."""
        
        # FIXED: Create connector with more conservative settings for Shopify CDN
        connector = aiohttp.TCPConnector(
            limit=15,           # Reduced from 25 to prevent CDN overload
            limit_per_host=5,   # Further reduced from 8 to prevent rate limiting
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=60,   # Increased from 30 for better connection reuse
            enable_cleanup_closed=True
        )
        
        # FIXED: Create timeout configuration with much longer timeouts for Shopify
        timeout = aiohttp.ClientTimeout(
            total=180,      # Increased from 90 to 180 seconds for Shopify CDN
            connect=45,     # Increased from 20 to 45 seconds
            sock_read=120   # Increased from 45 to 120 seconds
        )
        
        # Enhanced headers for better Shopify CDN compatibility
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/avif,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site'
        }
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers
        ) as session:
            
            # Collect all upload tasks with proper mapping
            upload_tasks = []
            task_metadata = []
            
            for product_index, product in enumerate(products_batch):
                # Get product identifier for reliable matching
                product_identifier = self._get_product_identifier(product)
                
                if hasattr(product, 'images') and product.images:
                    for image_index, image in enumerate(product.images):
                        if hasattr(image, 'url') and image.url:
                            s3_key = f"{product.brand.lower().replace(' ', '-')}/{product.product_id}/image_{image_index+1}.jpg"
                            
                            task = self._upload_single_image_to_s3_fixed(
                                session, image.url, s3_key, product, site, image_index
                            )
                            upload_tasks.append(task)
                            
                            # Store detailed metadata for mapping
                            task_metadata.append({
                                'product_identifier': product_identifier,
                                'product_index': product_index,
                                'image_index': image_index,
                                's3_key': s3_key,
                                'original_url': image.url
                            })
            
            if not upload_tasks:
                return []
            
            # FIXED: Execute uploads with much lower concurrency for Shopify CDN
            semaphore = asyncio.Semaphore(5)  # Further reduced from 15 to 5 for Shopify CDN
            
            async def controlled_upload(task):
                async with semaphore:
                    # Add small delay between requests to avoid CDN rate limiting
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    return await task
            
            print(f"🚀 Uploading {len(upload_tasks)} images with reduced concurrency (max 5 concurrent) for Shopify CDN stability...")
            
            results = await asyncio.gather(
                *[controlled_upload(task) for task in upload_tasks],
                return_exceptions=True
            )
            
            # Process results and create product-image mapping
            product_image_mapping = []
            successful_uploads = 0
            failed_uploads = 0
            
            for i, result in enumerate(results):
                metadata = task_metadata[i]
                
                if isinstance(result, Exception):
                    print(f"❌ Upload failed for {metadata['product_identifier']}: {result}")
                    failed_uploads += 1
                    self.upload_stats['failed_uploads'] += 1
                elif isinstance(result, dict) and result.get('success'):
                    product_image_mapping.append({
                        'product_identifier': metadata['product_identifier'],
                        'product_index': metadata['product_index'],
                        'image_index': metadata['image_index'],
                        's3_key': result['s3_key'],
                        's3_url': result['s3_url'],
                        'original_url': metadata['original_url'],
                        'size': result.get('size', 0)
                    })
                    successful_uploads += 1
                    self.upload_stats['successful_uploads'] += 1
                    self.upload_stats['total_size'] += result.get('size', 0)
                else:
                    failed_uploads += 1
                    self.upload_stats['failed_uploads'] += 1
            
            self.upload_stats['total_attempted'] += len(upload_tasks)
            
            print(f"✅ Batch complete: {successful_uploads} successful, {failed_uploads} failed")
            
            return product_image_mapping
    
    def _get_product_identifier(self, product) -> str:
        """Get a reliable identifier for a product for mapping purposes."""
        # Use source_url as primary identifier
        if hasattr(product, 'source_url') and product.source_url:
            if isinstance(product.source_url, list):
                return product.source_url[0] if product.source_url else ''
            return product.source_url
        elif hasattr(product, 'product_id') and product.product_id:
            return f"id_{product.product_id}"
        else:
            # Fallback to a combination of brand and model
            brand = getattr(product, 'brand', 'unknown')
            model = getattr(product, 'model', 'unknown')
            return f"{brand}_{model}_{id(product)}"
    
    async def _upload_single_image_to_s3_fixed(self, session: aiohttp.ClientSession, 
                                            image_url: str, s3_key: str, 
                                            product: Any, site: str, image_index: int) -> Dict[str, Any]:
        """Upload a single image with enhanced error handling and retry logic."""
        
        max_retries = self.MAX_RETRIES
        
        for attempt in range(max_retries):
            try:
                # Enhanced image URL validation
                if not self._is_valid_image_url(image_url):
                    raise Exception(f"Invalid image URL: {image_url}")
                
                # Add delay between retries and for CDN rate limiting
                if attempt > 0:
                    wait_time = min(2 ** attempt + random.uniform(0.5, 2.0), 15)  # Cap at 15 seconds
                    print(f"      ⏱️  Retry {attempt + 1}, waiting {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                
                # FIXED: Create a new timeout just for this request with longer values
                request_timeout = aiohttp.ClientTimeout(
                    total=120,      # Increased from 90 to 120 seconds
                    connect=30,     # Increased from 20 to 30 seconds  
                    sock_read=90    # Increased from 45 to 90 seconds
                )
                
                # Download image data with enhanced error handling
                async with session.get(image_url, timeout=request_timeout) as response:
                    if response.status != 200:
                        if response.status == 404:
                            raise Exception(f"Image not found (404): {image_url}")
                        elif response.status == 403:
                            raise Exception(f"Access forbidden (403): {image_url}")
                        elif response.status == 429:  # Rate limited
                            if attempt < max_retries - 1:
                                wait_time = 5 + (2 ** attempt)
                                print(f"      🚫 Rate limited (429), waiting {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue
                            raise Exception(f"Rate limited (429): {image_url}")
                        elif response.status >= 500:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            raise Exception(f"Server error ({response.status}): {image_url}")
                        else:
                            raise Exception(f"HTTP {response.status}: {image_url}")
                    
                    # Check content type
                    content_type = response.headers.get('content-type', '').lower()
                    if content_type and not any(ct in content_type for ct in ['image', 'jpeg', 'jpg', 'png', 'webp']):
                        raise Exception(f"Invalid content type: {content_type}")
                    
                    # FIXED: Read image data with progress tracking for large files
                    image_data = bytearray()
                    chunk_size = 8192  # 8KB chunks
                    total_size = 0
                    
                    async for chunk in response.content.iter_chunked(chunk_size):
                        image_data.extend(chunk)
                        total_size += len(chunk)
                        
                        # Log progress for large files
                        if total_size > 1024 * 1024:  # > 1MB
                            print(f"      📥 Downloaded {total_size / (1024*1024):.1f}MB...")
                        
                        # Prevent extremely large downloads
                        if total_size > 50 * 1024 * 1024:  # 50MB limit
                            raise Exception(f"Image too large: {total_size / (1024*1024):.1f}MB")
                    
                    image_data = bytes(image_data)
                    
                    # Enhanced image data validation
                    if len(image_data) < 500:  # Increased minimum size
                        raise Exception(f"Image too small: {len(image_data)} bytes")
                    
                    # Check for common error responses in image data
                    if b'<!DOCTYPE html>' in image_data[:1000] or b'<html' in image_data[:1000]:
                        raise Exception("Received HTML instead of image data")
                
                # Upload to S3 using thread pool with enhanced error handling
                loop = asyncio.get_event_loop()
                
                def upload_to_s3():
                    try:
                        # Determine content type
                        if image_url.lower().endswith('.png'):
                            content_type = 'image/png'
                        elif image_url.lower().endswith('.webp'):
                            content_type = 'image/webp'
                        else:
                            content_type = 'image/jpeg'
                        
                        return self.s3.put_object(
                            Bucket=self.bucket_name,
                            Key=s3_key,
                            Body=image_data,
                            ContentType=content_type,
                            Metadata={
                                'brand': str(product.brand)[:100],  # Limit metadata length
                                'product_id': str(product.product_id)[:100],
                                'original_url': image_url[:500],  # Limit URL length
                                'site': site,
                                'image_index': str(image_index),
                                'upload_timestamp': str(int(time.time()))
                            }
                        )
                    except Exception as s3_error:
                        # Log specific S3 errors
                        error_msg = str(s3_error)
                        if 'MetadataTooLarge' in error_msg:
                            # Retry with minimal metadata
                            return self.s3.put_object(
                                Bucket=self.bucket_name,
                                Key=s3_key,
                                Body=image_data,
                                ContentType=content_type,
                                Metadata={
                                    'brand': str(product.brand)[:50],
                                    'site': site
                                }
                            )
                        else:
                            raise s3_error
                
                # Execute S3 upload in thread pool
                with ThreadPoolExecutor(max_workers=1) as executor:
                    s3_response = await loop.run_in_executor(executor, upload_to_s3)
                
                # Generate S3 URL
                s3_url = f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"
                
                print(f"      ✅ Successfully uploaded {len(image_data) / 1024:.1f}KB to S3")
                
                return {
                    'success': True,
                    's3_key': s3_key,
                    's3_url': s3_url,
                    'size': len(image_data),
                    'original_url': image_url,
                    'content_type': response.headers.get('content-type', 'unknown')
                }
                
            except asyncio.TimeoutError as e:
                error_msg = f"Connection timeout after {request_timeout.total}s: {str(e)}"
                print(f"⚠️  Image upload timeout (attempt {attempt + 1}): {image_url[:60]}...")
                print(f"    💡 Consider increasing timeout values or checking network connectivity")
                
            except Exception as e:
                error_msg = str(e)
                
                # Log specific error details for debugging
                if attempt == 0:  # Log on first attempt
                    print(f"⚠️  Image upload attempt {attempt + 1} failed: {error_msg[:100]}...")
                
                # Don't retry certain errors
                if any(no_retry in error_msg.lower() for no_retry in ['404', '403', 'invalid image url', 'invalid content type']):
                    detailed_error = f"Non-retryable error: {error_msg}"
                    self.log_failure(
                        failure_type='s3_upload',
                        brand=product.brand,
                        site=site,
                        error_details=detailed_error,
                        product_url=self._get_product_identifier(product)
                    )
                    return {'success': False, 'error': detailed_error}
                
                if attempt == max_retries - 1:
                    # Log failure with more details
                    detailed_error = f"Failed after {max_retries} attempts. Final error: {error_msg}"
                    self.log_failure(
                        failure_type='s3_upload',
                        brand=product.brand,
                        site=site,
                        error_details=detailed_error,
                        product_url=self._get_product_identifier(product)
                    )
                    return {'success': False, 'error': detailed_error}
        
        return {'success': False, 'error': 'Max retries exceeded'}
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Enhanced image URL validation."""
        if not url or not isinstance(url, str):
            return False
        
        # Must be HTTP/HTTPS
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Check for common invalid patterns
        invalid_patterns = [
            'javascript:', 'data:', 'blob:', 'about:',
            'example.com', 'placeholder', 'blank.gif',
            'spacer.gif', '1x1.gif', 'pixel.gif'
        ]
        
        url_lower = url.lower()
        if any(pattern in url_lower for pattern in invalid_patterns):
            return False
        
        # Should look like an image URL
        return any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', 'image'])
    
    def _update_products_with_s3_urls_fixed(self, products: List[Any], product_image_mapping: List[Dict[str, Any]]):
        """Update product image objects with S3 URLs using fixed mapping."""
        
        # Create lookup by product identifier and image index
        mapping_lookup = {}
        for mapping in product_image_mapping:
            key = f"{mapping['product_identifier']}_{mapping['image_index']}"
            mapping_lookup[key] = mapping
        
        # Update products using multiple strategies
        updated_count = 0
        
        for product_index, product in enumerate(products):
            product_identifier = self._get_product_identifier(product)
            
            if hasattr(product, 'images') and product.images:
                for image_index, image in enumerate(product.images):
                    # Strategy 1: Use product identifier + image index
                    lookup_key = f"{product_identifier}_{image_index}"
                    
                    if lookup_key in mapping_lookup:
                        mapping = mapping_lookup[lookup_key]
                        self._update_image_with_s3_info(image, mapping)
                        updated_count += 1
                        continue
                    
                    # Strategy 2: Use product index + image index (fallback)
                    fallback_key = f"index_{product_index}_{image_index}"
                    for mapping in product_image_mapping:
                        if (mapping.get('product_index') == product_index and 
                            mapping.get('image_index') == image_index):
                            self._update_image_with_s3_info(image, mapping)
                            updated_count += 1
                            break
        
        print(f"📸 Updated {updated_count} images with S3 URLs")
    
    def _update_image_with_s3_info(self, image, mapping: Dict[str, Any]):
        """Update a single image object with S3 information."""
        # Add S3 information to image object
        if hasattr(image, 's3_key'):
            image.s3_key = mapping['s3_key']
        else:
            setattr(image, 's3_key', mapping['s3_key'])
        
        if hasattr(image, 's3_url'):
            image.s3_url = mapping['s3_url']
        else:
            setattr(image, 's3_url', mapping['s3_url'])
        
        # Add file size if available
        if hasattr(image, 'file_size'):
            image.file_size = mapping.get('size', 0)
        else:
            setattr(image, 'file_size', mapping.get('size', 0))
    
    # Keep the original method for backward compatibility
    async def upload_images_to_s3_optimized(self, products: List[Any], site: str) -> Dict[str, int]:
        """
        Original method - now calls the fixed version.
        """
        return await self.upload_images_to_s3_optimized_fixed(products, site)
    
    async def upload_local_images_to_s3_batch(self, products: List[Any], site: str) -> Dict[str, int]:
        """
        Upload local images to S3 in batches (for compatibility with existing scrapers).
        This method handles products that already have local images downloaded.
        """
        print(f"📁 Uploading local images to S3 for {len(products)} products...")
        
        # Reset stats
        self.upload_stats = {
            'total_attempted': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'total_size': 0,
            'total_time': 0
        }
        
        start_time = time.time()
        
        # Process products in batches
        for batch_start in range(0, len(products), self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, len(products))
            batch = products[batch_start:batch_end]
            
            print(f"📦 Processing batch {batch_start//self.BATCH_SIZE + 1}: products {batch_start+1}-{batch_end}")
            
            # Upload batch using thread pool for local file operations
            await self._upload_local_batch_to_s3(batch, site)
            
            # Brief pause between batches
            if batch_end < len(products):
                await asyncio.sleep(0.5)
        
        total_time = time.time() - start_time
        self.upload_stats['total_time'] = total_time
        
        # Print final statistics
        print(f"\n📊 LOCAL -> S3 UPLOAD STATISTICS:")
        print(f"✅ Successful uploads: {self.upload_stats['successful_uploads']}")
        print(f"❌ Failed uploads: {self.upload_stats['failed_uploads']}")
        print(f"📈 Success rate: {(self.upload_stats['successful_uploads'] / max(1, self.upload_stats['total_attempted'])) * 100:.1f}%")
        print(f"💾 Total size: {self.upload_stats['total_size'] / (1024*1024):.2f} MB")
        print(f"⏱️  Total time: {total_time:.1f}s")
        
        return {
            'uploaded': self.upload_stats['successful_uploads'],
            'failed': self.upload_stats['failed_uploads']
        }
    
    async def _upload_local_batch_to_s3(self, products_batch: List[Any], site: str):
        """Upload local images from a batch of products to S3."""
        
        # Use thread pool for file operations
        loop = asyncio.get_event_loop()
        
        with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT_UPLOADS) as executor:
            upload_tasks = []
            
            for product in products_batch:
                if hasattr(product, 'images') and product.images:
                    for i, image in enumerate(product.images):
                        # Check if image has local path
                        if hasattr(image, 'local_path') and image.local_path:
                            local_path = Path(image.local_path)
                            
                            # Check if local file exists
                            if local_path.exists():
                                s3_key = f"{product.brand.lower().replace(' ', '-')}/{product.product_id}/image_{i+1}.jpg"
                                
                                task = loop.run_in_executor(
                                    executor,
                                    self._upload_local_file_to_s3,
                                    str(local_path),
                                    s3_key,
                                    product,
                                    site,
                                    i
                                )
                                upload_tasks.append(task)
                            else:
                                print(f"⚠️  Local file not found: {local_path}")
                                self.upload_stats['failed_uploads'] += 1
                        else:
                            print(f"⚠️  No local path for image in product {product.product_id}")
                            self.upload_stats['failed_uploads'] += 1
            
            if upload_tasks:
                # Wait for all uploads to complete
                results = await asyncio.gather(*upload_tasks, return_exceptions=True)
                
                # Process results
                for result in results:
                    if isinstance(result, Exception):
                        print(f"❌ Upload failed: {result}")
                        self.upload_stats['failed_uploads'] += 1
                    elif isinstance(result, dict) and result.get('success'):
                        self.upload_stats['successful_uploads'] += 1
                        self.upload_stats['total_size'] += result.get('size', 0)
                    else:
                        self.upload_stats['failed_uploads'] += 1
                
                self.upload_stats['total_attempted'] += len(upload_tasks)
    
    def _upload_local_file_to_s3(self, local_path: str, s3_key: str, product: Any, site: str, image_index: int) -> Dict[str, Any]:
        """Upload a single local file to S3 (synchronous function for thread pool)."""
        try:
            # Read local file
            with open(local_path, 'rb') as file:
                file_data = file.read()
            
            if len(file_data) < 1000:
                raise Exception(f"File too small: {len(file_data)} bytes")
            
            # Determine content type
            if local_path.lower().endswith('.png'):
                content_type = 'image/png'
            elif local_path.lower().endswith('.webp'):
                content_type = 'image/webp'
            else:
                content_type = 'image/jpeg'
            
            # Upload to S3
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
                Metadata={
                    'brand': str(product.brand)[:100],
                    'product_id': str(product.product_id)[:100],
                    'local_path': local_path[:500],
                    'site': site,
                    'image_index': str(image_index)
                }
            )
            
            # Generate S3 URL
            s3_url = f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"
            
            # Update the image object with S3 info
            if hasattr(product.images[image_index], 's3_key'):
                product.images[image_index].s3_key = s3_key
            else:
                setattr(product.images[image_index], 's3_key', s3_key)
            
            if hasattr(product.images[image_index], 's3_url'):
                product.images[image_index].s3_url = s3_url
            else:
                setattr(product.images[image_index], 's3_url', s3_url)
            
            return {
                'success': True,
                's3_key': s3_key,
                's3_url': s3_url,
                'size': len(file_data)
            }
            
        except Exception as e:
            # Log failure
            self.log_failure(
                failure_type='local_s3_upload',
                brand=product.brand,
                site=site,
                error_details=f"Failed to upload local file {local_path} to {s3_key}: {str(e)}",
                product_url=self._get_product_identifier(product)
            )
            return {'success': False, 'error': str(e)}
    
    def check_existing_products(self, products: List[Any], site: str) -> Dict[str, List[Any]]:
        """Check which products already exist to avoid duplicates."""
        existing_products = []
        new_products = []
        
        print(f"🔍 Checking for existing products in {site}...")
        
        for product in products:
            # Get source URL
            if hasattr(product, 'source_url') and product.source_url:
                if isinstance(product.source_url, list):
                    source_url = product.source_url[0] if product.source_url else ''
                else:
                    source_url = product.source_url
            else:
                source_url = ''
            
            if not source_url:
                new_products.append(product)
                continue
            
            try:
                # Check if product exists
                response = self.products_table.get_item(
                    Key={
                        'source_url': source_url,
                        'site': site
                    }
                )
                
                if 'Item' in response:
                    existing_products.append(product)
                    print(f"⚠️  Product already exists: {source_url[:50]}...")
                else:
                    new_products.append(product)
                    
            except Exception as e:
                # If check fails, assume it's new
                new_products.append(product)
                print(f"❌ Error checking product existence: {e}")
        
        print(f"📊 Found {len(existing_products)} existing, {len(new_products)} new products")
        return {
            'existing': existing_products,
            'new': new_products
        }
    
    def store_products(self, products: List[Any], site: str, skip_duplicates: bool = True) -> Dict[str, int]:
        """Store products in DynamoDB with duplicate checking."""
        successful = 0
        failed = 0
        skipped = 0
        
        if skip_duplicates:
            product_check = self.check_existing_products(products, site)
            products_to_store = product_check['new']
            skipped = len(product_check['existing'])
        else:
            products_to_store = products
        
        print(f"📄 Storing {len(products_to_store)} products in DynamoDB...")
        
        for product in products_to_store:
            try:
                # Get source URL
                if hasattr(product, 'source_url') and product.source_url:
                    if isinstance(product.source_url, list):
                        source_url = product.source_url[0] if product.source_url else ''
                    else:
                        source_url = product.source_url
                else:
                    source_url = ''
                
                # Build S3 URLs for images
                s3_image_urls = []
                for image in product.images:
                    if hasattr(image, 's3_url') and image.s3_url:
                        s3_image_urls.append(image.s3_url)
                
                # Convert product to DynamoDB item
                item = {
                    'source_url': source_url,  # Primary key
                    'site': site,              # Sort key
                    'product_id': product.product_id,
                    'brand': product.brand,
                    'model': product.model,
                    'category': getattr(product, 'category', 'unknown'),
                    'product_name': getattr(product, 'product_name', ''),
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'image_count': len(product.images),
                    's3_image_urls': s3_image_urls,
                    'sku': product.sku[0] if product.sku else '',
                    'scrape_success': True
                }
                
                # Store in DynamoDB
                self.products_table.put_item(Item=item)
                successful += 1
                
            except Exception as e:
                print(f"❌ Failed to store product: {e}")
                failed += 1
                
                # Log the failure
                self.log_failure(
                    failure_type='product_storage',
                    brand=product.brand,
                    site=site,
                    error_details=str(e),
                    product_url=source_url
                )
        
        print(f"✅ Stored {successful} products, {failed} failed, {skipped} skipped (duplicates)")
        return {'successful': successful, 'failed': failed, 'skipped': skipped}
    
    def log_failure(self, failure_type: str, brand: str, site: str, error_details: str, 
                   product_url: Optional[str] = None, retry_count: int = 0):
        """Log failure to failures table."""
        try:
            failure_id = hashlib.sha256(
                f"{failure_type}_{brand}_{site}_{int(time.time())}".encode()
            ).hexdigest()[:16]
            
            failure_item = {
                'failure_id': failure_id,
                'failure_type': failure_type,
                'brand': brand,
                'site': site,
                'error_details': error_details[:500],  # Truncate long errors
                'product_url': product_url or '',
                'retry_count': retry_count,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'status': 'failed'
            }
            
            self.failures_table.put_item(Item=failure_item)
            print(f"📝 Logged failure: {failure_type} for {brand} on {site}")
            
        except Exception as e:
            print(f"❌ Failed to log failure: {e}")
    
    def get_failure_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get failure summary for the last N hours."""
        try:
            from datetime import timedelta
            
            cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            
            response = self.failures_table.scan(
                FilterExpression='created_at > :cutoff_time',
                ExpressionAttributeValues={':cutoff_time': cutoff_time}
            )
            
            failures = response.get('Items', [])
            
            # Analyze failures
            failure_types = {}
            brand_failures = {}
            site_failures = {}
            
            for failure in failures:
                failure_type = failure.get('failure_type', 'unknown')
                brand = failure.get('brand', 'unknown')
                site = failure.get('site', 'unknown')
                
                failure_types[failure_type] = failure_types.get(failure_type, 0) + 1
                brand_failures[brand] = brand_failures.get(brand, 0) + 1
                site_failures[site] = site_failures.get(site, 0) + 1
            
            return {
                'total_failures': len(failures),
                'failure_types': failure_types,
                'brand_failures': brand_failures,
                'site_failures': site_failures,
                'time_period_hours': hours
            }
            
        except Exception as e:
            print(f"❌ Error getting failure summary: {e}")
            return {'error': str(e)}
    
    def get_retry_candidates(self, failure_type: str = None, max_retries: int = 3) -> List[Dict]:
        """Get failed items that can be retried."""
        try:
            filter_expression = 'retry_count < :max_retries'
            expression_values = {':max_retries': max_retries}
            
            if failure_type:
                filter_expression += ' AND failure_type = :failure_type'
                expression_values[':failure_type'] = failure_type
            
            response = self.failures_table.scan(
                FilterExpression=filter_expression,
                ExpressionAttributeValues=expression_values
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            print(f"❌ Error getting retry candidates: {e}")
            return []
    
    def query_products(self, site: str = None, brand: str = None, limit: int = 10) -> List[Dict]:
        """Query products from DynamoDB."""
        try:
            if brand:
                # Use the brand index for efficient querying
                response = self.products_table.query(
                    IndexName='BrandIndex',
                    KeyConditionExpression='brand = :brand',
                    ExpressionAttributeValues={':brand': brand},
                    Limit=limit,
                    ScanIndexForward=False  # Most recent first
                )
                items = response.get('Items', [])
                
                # Filter by site if specified
                if site:
                    items = [item for item in items if item.get('site') == site]
                
                return items
            elif site:
                # Scan with site filter
                response = self.products_table.scan(
                    FilterExpression='site = :site',
                    ExpressionAttributeValues={':site': site},
                    Limit=limit
                )
                return response.get('Items', [])
            else:
                # Scan all
                response = self.products_table.scan(Limit=limit)
                return response.get('Items', [])
                
        except Exception as e:
            print(f"❌ Query error: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive storage statistics."""
        try:
            # Get total products
            products_response = self.products_table.scan(Select='COUNT')
            total_products = products_response.get('Count', 0)
            
            # Get failure summary
            failure_summary = self.get_failure_summary(hours=24)
            
            # Get products by site and brand
            sites = {}
            brands = {}
            response = self.products_table.scan()
            for item in response.get('Items', []):
                site = item.get('site', 'unknown')
                brand = item.get('brand', 'unknown')
                sites[site] = sites.get(site, 0) + 1
                brands[brand] = brands.get(brand, 0) + 1
            
            # Get S3 stats
            s3_response = self.s3.list_objects_v2(Bucket=self.bucket_name)
            s3_objects = len(s3_response.get('Contents', []))
            
            return {
                'total_products': total_products,
                'products_by_site': sites,
                'products_by_brand': brands,
                'total_s3_objects': s3_objects,
                'failure_summary': failure_summary,
                'tables': {
                    'products': self.products_table_name,
                    'failures': self.failures_table_name
                },
                'bucket': self.bucket_name
            }
            
        except Exception as e:
            print(f"❌ Stats error: {e}")
            return {'error': str(e)}
    
    def print_monitoring_report(self):
        """Print a comprehensive monitoring report."""
        print("\n" + "="*60)
        print("📊 SCRAPING MONITORING REPORT")
        print("="*60)
        
        stats = self.get_stats()
        
        print(f"\n📈 OVERALL STATS:")
        print(f"   Total Products: {stats.get('total_products', 0)}")
        print(f"   Total S3 Images: {stats.get('total_s3_objects', 0)}")
        
        print(f"\n🏢 PRODUCTS BY SITE:")
        for site, count in stats.get('products_by_site', {}).items():
            print(f"   {site}: {count}")
        
        print(f"\n🏷️  PRODUCTS BY BRAND:")
        for brand, count in stats.get('products_by_brand', {}).items():
            print(f"   {brand}: {count}")
        
        failure_summary = stats.get('failure_summary', {})
        print(f"\n❌ FAILURES (Last 24h): {failure_summary.get('total_failures', 0)}")
        
        for failure_type, count in failure_summary.get('failure_types', {}).items():
            print(f"   {failure_type}: {count}")
        
        print(f"\n🔄 RETRY CANDIDATES:")
        retry_candidates = self.get_retry_candidates()
        print(f"   Total items to retry: {len(retry_candidates)}")
        
        print("="*60 + "\n")


# Convenience function for easy migration
async def upload_images_optimized(products: List[Any], site: str) -> Dict[str, int]:
    """
    Convenience function for optimized image upload.
    This replaces the old upload_images_to_s3 method.
    """
    storage = OptimizedAWSStorage()
    return await storage.upload_images_to_s3_optimized_fixed(products, site)