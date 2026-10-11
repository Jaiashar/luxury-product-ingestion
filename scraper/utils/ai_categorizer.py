# scraper/utils/ai_categorizer.py
"""AI-powered product categorization service with robust rate limiting and retry logic."""

import os
import asyncio
import json
import time
import random
from typing import Optional, List, Dict, Any
from collections import deque
from anthropic import Anthropic

class AIProductCategorizer:
    """AI-only service for categorizing luxury products with advanced error handling."""
    
    def __init__(self):
        api_key = os.getenv('ANTHROPIC_API_KEY')
        self.anthropic = Anthropic(api_key=api_key) if api_key else None
        
        if not self.anthropic:
            raise RuntimeError("ANTHROPIC_API_KEY is required - no fallbacks allowed for data accuracy")
        
        # Conservative settings for stability
        self.max_batch_size = 25  # Reduced from 25 for better stability
        self.delay_between_batches = 2.0  # Increased from 0.5 for rate limiting
        self.max_concurrent_requests = 3  # Limit concurrent requests
        self.requests_per_minute = 50  # Conservative API rate limit
        
        # Retry and backoff settings
        self.max_retries = 3
        self.base_retry_delay = 1.0
        self.max_retry_delay = 30.0
        
        # Circuit breaker settings
        self.consecutive_failures = 0
        self.max_failures = 5
        self.circuit_breaker_delay = 30  # seconds
        self.last_failure_time = 0
        
        # Rate limiting tracking
        self.request_times = deque()
        
        # Caching system for identical products
        self.category_cache = {}
        
        # Performance tracking
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'ai_calls': 0,
            'batch_processing_time': 0,
            'failed_categorizations': 0,
            'retry_attempts': 0,
            'rate_limit_hits': 0,
            'circuit_breaker_activations': 0
        }
        
        # Define our category schema
        self.categories = {
            "bags": "Handbags, purses, clutches, totes, backpacks, shoulder bags, crossbody bags, messenger bags, duffel bags, travel bags, evening bags, mini bags, belt bags, saddlebags",
            "shoes": "All footwear including heels, flats, sneakers, boots, sandals, loafers, oxfords, pumps, wedges, platforms, mary janes, mules, slip-ons, athletic shoes, dress shoes",
            "clothing": "Dresses, tops, pants, skirts, shorts, shirts, blouses, t-shirts, jeans, coats, jackets, blazers, cardigans, sweaters, hoodies, vests, outerwear, activewear, sleepwear, underwear, suits, formal wear",
            "jewelry": "Necklaces, rings, earrings, bracelets, watches, brooches, anklets, chains, pendants, charms, cufflinks, tie clips, body jewelry",
            "accessories": "Belts, scarves, hats, sunglasses, wallets, phone cases, keychains, gloves, hair accessories, tech accessories, travel accessories",
            "beauty": "Makeup, skincare, fragrances, nail polish, brushes, beauty tools, perfumes, cosmetics, serums, creams, foundations"
        }
        
        print("🤖 AI Categorizer initialized with robust rate limiting and retry logic")
    
    async def _wait_for_rate_limit(self):
        """Ensure we don't exceed rate limits."""
        now = time.time()
        
        # Remove requests older than 1 minute
        while self.request_times and now - self.request_times[0] > 60:
            self.request_times.popleft()
        
        # If we're at the limit, wait
        if len(self.request_times) >= self.requests_per_minute:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                print(f"  ⏳ Rate limit reached, waiting {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time)
                self.stats['rate_limit_hits'] += 1
        
        # Record this request
        self.request_times.append(now)
    
    async def _check_circuit_breaker(self):
        """Check if we should temporarily stop making requests."""
        if self.consecutive_failures >= self.max_failures:
            time_since_failure = time.time() - self.last_failure_time
            if time_since_failure < self.circuit_breaker_delay:
                remaining = self.circuit_breaker_delay - time_since_failure
                print(f"  🚫 Circuit breaker active, waiting {remaining:.1f}s")
                await asyncio.sleep(remaining)
                self.consecutive_failures = 0
                self.stats['circuit_breaker_activations'] += 1
    
    def _is_rate_limit_error(self, error_str: str) -> bool:
        """Check if error is related to rate limiting."""
        error_lower = str(error_str).lower()
        return any(keyword in error_lower for keyword in [
            'overloaded', '529', 'rate limit', 'too many requests', 
            'quota exceeded', 'throttled'
        ])
    
    async def categorize_products_batch(self, products_data: List[dict]) -> List[str]:
        """
        AI-ONLY: Categorize multiple products using only AI with robust error handling.
        """
        start_time = time.time()
        print(f"🤖 AI categorizing {len(products_data)} products with enhanced stability...")
        
        # Check cache first
        cached_results = {}
        uncached_products = []
        uncached_indices = []
        
        for i, product_data in enumerate(products_data):
            product_name = product_data.get('model', '')
            brand = product_data.get('brand', '')
            
            # Check cache
            cache_key = f"{brand}:{product_name}".lower()
            if cache_key in self.category_cache:
                cached_results[i] = self.category_cache[cache_key]
                self.stats['cache_hits'] += 1
            else:
                uncached_products.append(product_data)
                uncached_indices.append(i)
        
        print(f"  💾 Cache hits: {len(cached_results)}/{len(products_data)} ({len(cached_results)/len(products_data)*100:.1f}%)")
        print(f"  🤖 AI processing: {len(uncached_products)} products")
        
        # Process uncached products with AI in conservative batches
        ai_categories = []
        if uncached_products:
            ai_categories = await self._process_ai_batches_with_retry(uncached_products)
        
        # Merge results
        all_categories = [''] * len(products_data)
        
        # Fill cached results
        for idx, category in cached_results.items():
            all_categories[idx] = category
        
        # Fill AI results
        for i, category in enumerate(ai_categories):
            if i < len(uncached_indices):
                all_categories[uncached_indices[i]] = category
        
        # Verify all products were categorized
        uncategorized_count = sum(1 for cat in all_categories if not cat)
        if uncategorized_count > 0:
            print(f"⚠️  Warning: {uncategorized_count} products failed AI categorization")
            self.stats['failed_categorizations'] += uncategorized_count
            
            # For failed categorizations, use 'unknown'
            for i, category in enumerate(all_categories):
                if not category:
                    all_categories[i] = 'unknown'
        
        # Update stats
        total_time = time.time() - start_time
        self.stats['total_requests'] += len(products_data)
        self.stats['batch_processing_time'] += total_time
        
        print(f"✅ AI categorization completed in {total_time:.1f}s!")
        self._print_stats()
        
        return all_categories
    
    async def _process_ai_batches_with_retry(self, products_data: List[dict]) -> List[str]:
        """Process AI requests in batches with comprehensive retry logic."""
        all_categories = []
        
        for i in range(0, len(products_data), self.max_batch_size):
            batch = products_data[i:i + self.max_batch_size]
            batch_num = (i // self.max_batch_size) + 1
            total_batches = (len(products_data) + self.max_batch_size - 1) // self.max_batch_size
            
            print(f"  🤖 AI batch {batch_num}/{total_batches} ({len(batch)} products)")
            
            # Check circuit breaker before processing
            await self._check_circuit_breaker()
            
            # Process batch with retry logic
            batch_categories = await self._categorize_batch_with_retry(batch)
            all_categories.extend(batch_categories)
            
            self.stats['ai_calls'] += len(batch)
            
            # Delay between batches (except for the last batch)
            if i + self.max_batch_size < len(products_data):
                await asyncio.sleep(self.delay_between_batches)
        
        return all_categories
    
    async def _categorize_batch_with_retry(self, products_batch: List[dict]) -> List[str]:
        """Categorize a batch with exponential backoff retry logic."""
        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit before making request
                await self._wait_for_rate_limit()
                
                # Make the API call
                batch_categories = await self._categorize_mega_batch(products_batch)
                
                # Success - reset failure counter
                self.consecutive_failures = 0
                return batch_categories
                
            except Exception as e:
                error_str = str(e)
                self.stats['retry_attempts'] += 1
                
                if self._is_rate_limit_error(error_str):
                    # Rate limit error - implement exponential backoff
                    if attempt < self.max_retries - 1:
                        # Calculate backoff delay with jitter
                        delay = min(
                            self.base_retry_delay * (2 ** attempt) + random.uniform(0, 1),
                            self.max_retry_delay
                        )
                        print(f"  🔄 Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        print(f"  ❌ Max retries exceeded for rate limit: {error_str}")
                        self.consecutive_failures += 1
                        self.last_failure_time = time.time()
                        return ['unknown'] * len(products_batch)
                else:
                    # Non-rate-limit error - fail fast
                    print(f"  ❌ Non-rate-limit error: {error_str}")
                    self.consecutive_failures += 1
                    self.last_failure_time = time.time()
                    return ['unknown'] * len(products_batch)
        
        # If we get here, all retries failed
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        return ['unknown'] * len(products_batch)
    
    async def _categorize_mega_batch(self, products_batch: List[dict]) -> List[str]:
        """Send multiple products in a single AI request."""
        # Build mega prompt with all products
        categories_text = "\n".join([
            f"- {cat}: {desc}"
            for cat, desc in self.categories.items()
        ])
        
        products_text = ""
        for i, product_data in enumerate(products_batch):
            brand = product_data.get('brand', '')
            product_name = product_data.get('model', '')
            description = product_data.get('description', '')
            if description:
                products_text += f"{i+1}. {brand} {product_name} - {description}\n"
            else:
                products_text += f"{i+1}. {brand} {product_name}\n"
        
        response = self.anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=300,  # Increased for larger batches
            messages=[{
                "role": "user",
                "content": f"""Categorize these {len(products_batch)} luxury products into the most accurate categories:

AVAILABLE CATEGORIES:
{categories_text}

PRODUCTS TO CATEGORIZE:
{products_text}

CRITICAL INSTRUCTIONS:
1. Return ONLY a numbered list with category names
2. Format: "1. bags\n2. shoes\n3. clothing\n..." etc.
3. Use ONLY these exact category names: {', '.join(self.categories.keys())}
4. Analyze each product carefully for maximum accuracy
5. Consider brand context and product descriptions
6. Return exactly {len(products_batch)} categories, numbered 1-{len(products_batch)}

RESPONSE (category names only):"""
            }]
        )
        
        # Parse the response
        response_text = response.content[0].text.strip()
        categories = self._parse_mega_response(response_text, len(products_batch))
        
        # Cache all successful results
        for i, product_data in enumerate(products_batch):
            if i < len(categories) and categories[i] != 'unknown':
                brand = product_data.get('brand', '')
                product_name = product_data.get('model', '')
                cache_key = f"{brand}:{product_name}".lower()
                self.category_cache[cache_key] = categories[i]
        
        return categories
    
    def _parse_mega_response(self, response_text: str, expected_count: int) -> List[str]:
        """Parse AI response for multiple products with strict validation."""
        lines = response_text.strip().split('\n')
        categories = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Extract category from numbered line
            found_category = None
            line_lower = line.lower()
            
            # Look for exact category matches
            for category in self.categories.keys():
                if category in line_lower:
                    found_category = category
                    break
            
            if found_category:
                categories.append(found_category)
            else:
                # AI returned invalid category
                categories.append('unknown')
        
        # Ensure we have the right number of categories
        while len(categories) < expected_count:
            categories.append('unknown')
        
        return categories[:expected_count]
    
    async def categorize_product(self, product_name: str, brand: str = "", description: str = "") -> str:
        """Single product categorization using AI with retry logic."""
        # Check cache first
        cache_key = f"{brand}:{product_name}".lower()
        if cache_key in self.category_cache:
            return self.category_cache[cache_key]
        
        # Use batch processing for consistency
        product_data = {
            'model': product_name,
            'brand': brand,
            'description': description
        }
        
        categories = await self.categorize_products_batch([product_data])
        return categories[0] if categories else 'unknown'
    
    def _print_stats(self):
        """Print current performance statistics."""
        print(f"  📊 Stats - Cache: {self.stats['cache_hits']}, AI: {self.stats['ai_calls']}, "
              f"Retries: {self.stats['retry_attempts']}, Rate Limits: {self.stats['rate_limit_hits']}, "
              f"Circuit Breaker: {self.stats['circuit_breaker_activations']}, Failed: {self.stats['failed_categorizations']}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get detailed performance statistics."""
        total_requests = self.stats['total_requests']
        if total_requests == 0:
            return self.stats
        
        cache_hit_rate = (self.stats['cache_hits'] / total_requests) * 100
        failure_rate = (self.stats['failed_categorizations'] / total_requests) * 100
        
        return {
            **self.stats,
            'cache_hit_rate': cache_hit_rate,
            'failure_rate': failure_rate,
            'cache_size': len(self.category_cache),
            'accuracy': 100 - failure_rate,
            'avg_batch_time': self.stats['batch_processing_time'] / max(1, total_requests)
        }
    
    def reset_stats(self):
        """Reset performance statistics."""
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'ai_calls': 0,
            'batch_processing_time': 0,
            'failed_categorizations': 0,
            'retry_attempts': 0,
            'rate_limit_hits': 0,
            'circuit_breaker_activations': 0
        }
    
    def adjust_rate_limits(self, requests_per_minute: int = None, max_batch_size: int = None, 
                          delay_between_batches: float = None):
        """Dynamically adjust rate limiting parameters."""
        if requests_per_minute is not None:
            self.requests_per_minute = requests_per_minute
            print(f"🔧 Adjusted requests per minute to {requests_per_minute}")
        
        if max_batch_size is not None:
            self.max_batch_size = max_batch_size
            print(f"🔧 Adjusted max batch size to {max_batch_size}")
        
        if delay_between_batches is not None:
            self.delay_between_batches = delay_between_batches
            print(f"🔧 Adjusted delay between batches to {delay_between_batches}s")


# Global instance for easy importing
ai_categorizer = AIProductCategorizer()