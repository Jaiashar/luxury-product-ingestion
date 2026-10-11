# scraper/sites/base.py - Updated configuration for StockX
"""Enhanced base class for site scrapers with advanced session management."""

import re
import random
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from scrapfly import ScrapeConfig, ScrapflyClient
from ..utils.data_models import Product, ProductImage
from ..utils.session_manager import session_manager, SessionStatus

class BaseSiteScraper(ABC):
    def __init__(self, scrapfly_client: ScrapflyClient, rate_limit: float = 1.0):
        self.client = scrapfly_client
        self.rate_limit = rate_limit
        self.site_name = self.get_site_name()
        
        # Session management
        self.current_session = None
        self.session_request_count = 0
        self.max_requests_per_session = 40  # Conservative limit
        
        # Enhanced error tracking
        self.error_counts = {
            'session_errors': 0,
            'timeout_errors': 0,
            'asp_errors': 0,
            'total_errors': 0
        }
    
    @abstractmethod
    def get_site_name(self) -> str:
        """Return the name of the site."""
        pass
    
    @abstractmethod
    async def scrape_brand_products(self, brand: str, max_products: int = 5) -> List[Product]:
        """Main method to scrape products from a brand. Must return Product objects."""
        pass
    
    async def get_or_create_session(self, brand: str, operation: str = "scrape") -> str:
        """Get existing session or create new one with rotation logic."""
        # Check if current session needs rotation
        if (self.current_session is None or 
            session_manager.should_rotate_session(self.current_session) or
            self.session_request_count >= self.max_requests_per_session):
            
            if self.current_session:
                print(f"🔄 Rotating session (requests: {self.session_request_count})")
            
            # Create new session
            self.current_session = await session_manager.create_session(
                self.site_name, brand, operation
            )
            self.session_request_count = 0
        
        return self.current_session
    
    async def make_request_with_session(self, url: str, brand: str, 
                                    operation: str = "scrape", 
                                    render_js: bool = True,
                                    **config_kwargs) -> Any:
        """Make a request with proper session management - simplified to match working approach."""
        
        # Ensure proper request spacing
        await session_manager.wait_for_request_gap()
        
        # Get or create session
        session_name = await self.get_or_create_session(brand, operation)
        
        # Create config with session - let ScrapFly handle retries
        config = self._get_scrape_config(
            url, session_name, render_js, **config_kwargs
        )
        
        try:
            # Make the request - ScrapFly handles retries automatically
            result = await self.client.async_scrape(config)
            
            # Record successful request
            session_manager.record_session_request(session_name, success=True)
            self.session_request_count += 1
            
            # Check for success
            if result.status_code == 200:
                return result
            else:
                # Handle non-200 status codes
                error_msg = f"HTTP {result.status_code}"
                session_manager.record_session_request(session_name, success=False)
                self._handle_request_error(session_name, error_msg)
                return None
                
        except Exception as e:
            error_msg = str(e)
            
            # Handle request errors
            session_manager.record_session_error(session_name, error_msg)
            self._handle_request_error(session_name, error_msg)
            
            # Check if we should retry with new session (one-time retry)
            if self._should_retry_with_new_session(error_msg):
                print(f"🔄 Retrying with new session due to: {error_msg[:100]}...")
                self.current_session = None  # Force new session
                
                # Wait a bit before retry
                await asyncio.sleep(2)
                
                # Single retry with new session
                try:
                    session_name = await self.get_or_create_session(brand, operation)
                    config = self._get_scrape_config(url, session_name, render_js, **config_kwargs)
                    result = await self.client.async_scrape(config)
                    
                    if result.status_code == 200:
                        session_manager.record_session_request(session_name, success=True)
                        self.session_request_count += 1
                        return result
                    else:
                        session_manager.record_session_request(session_name, success=False)
                        return None
                        
                except Exception as retry_e:
                    print(f"❌ Retry also failed: {str(retry_e)[:100]}...")
                    session_manager.record_session_error(session_name, str(retry_e))
                    return None
            
            return None

    def _should_retry_with_new_session(self, error_msg: str) -> bool:
        """Determine if error warrants retry with new session."""
        retry_keywords = [
            'concurrent_access', 'session', 'shield_protection_failed',
            'asp_timeout', 'operation_timeout', 'upstream_timeout'
        ]
    
        return any(keyword in error_msg.lower() for keyword in retry_keywords)
    
    def _handle_request_error(self, session_name: str, error_msg: str):
        """Handle and categorize request errors."""
        error_lower = error_msg.lower()
        
        if any(keyword in error_lower for keyword in ['session', 'concurrent']):
            self.error_counts['session_errors'] += 1
        elif any(keyword in error_lower for keyword in ['timeout', 'time']):
            self.error_counts['timeout_errors'] += 1
        elif any(keyword in error_lower for keyword in ['asp', 'shield', 'protection']):
            self.error_counts['asp_errors'] += 1
        
        self.error_counts['total_errors'] += 1
        
        # Log error with context
        print(f"❌ Request error ({session_name}): {error_msg}")
    
    def _get_scrape_config(self, url: str, session_name: str = None, 
                        render_js: bool = True, **kwargs) -> ScrapeConfig:
        """Create enhanced ScrapeConfig with session management - mimics working approach."""
        
        # Get enhanced headers from session manager
        headers = session_manager.get_enhanced_headers(self.site_name)
        
        # Filter out problematic parameters that cause conflicts
        safe_kwargs = {
            key: value for key, value in kwargs.items() 
            if key not in ['retry', 'retries', 'timeout', 'js_timeout', 'rendering_timeout']
        }
        
        # Base config parameters - match your working approach
        config_params = {
            'url': url,
            'render_js': render_js,
            'country': "US",
            'asp': True,
            'headers': headers,
        }
        
        # Add session if provided
        if session_name:
            config_params['session'] = session_name
        
        # Site-specific enhancements - NO TIMEOUT PARAMETERS (this was the key to your working code)
        if self.site_name == "farfetch":
            config_params.update({
                'rendering_wait': random.randint(6000, 10000),
                'auto_scroll': True,
                # NO timeout parameters - let ScrapFly use defaults with retry
            })
            
        elif self.site_name == "net-a-porter":
            config_params.update({
                'rendering_wait': random.randint(4000, 7000),
                'auto_scroll': True,
                # NO timeout parameters - let ScrapFly use defaults with retry
            })
        
        elif self.site_name == "stockx":  # NEW: StockX-specific configuration
            config_params.update({
                'rendering_wait': random.randint(8000, 15000),  # Conservative rendering wait
                'auto_scroll': True,
                # NO timeout parameters - let ScrapFly use defaults with retry
            })
        
        elif self.site_name == "rebag":
            config_params.update({
                'rendering_wait': random.randint(7000, 12000),  # Conservative rendering wait
                'auto_scroll': True,
                # NO timeout parameters - let ScrapFly use defaults with retry
            })

        elif self.site_name == "therealreal":
            config_params.update({
                'rendering_wait': random.randint(5000, 8000),  # Match your working values
                'auto_scroll': True,
                # NO timeout parameters - let ScrapFly use defaults with retry
            })
        
        # Add safe kwargs
        config_params.update(safe_kwargs)
        
        # Create the config - this should work like your original code
        config = ScrapeConfig(**config_params)
        
        return config
    
    def create_product_from_data(self, data: Dict[str, Any], brand: str, url: str) -> Optional[Product]:
        """Create standardized Product object from scraped data."""
        try:
            # Convert image data to ProductImage objects
            images = []
            image_data = data.get('images', [])
            
            for img_data in image_data:
                if isinstance(img_data, dict):
                    # Handle both URL-only and full image data
                    image_url = img_data.get('image_url') or img_data.get('url')
                    if image_url:
                        product_image = ProductImage(
                            image_id=img_data.get('image_id', ''),
                            url=image_url,
                            local_path=img_data.get('local_path'),
                            file_size=img_data.get('file_size')
                        )
                        images.append(product_image)
                elif isinstance(img_data, str):
                    # Handle simple URL strings
                    product_image = ProductImage(
                        image_id='',
                        url=img_data
                    )
                    images.append(product_image)
            
            # Use brand from data if available, otherwise use provided brand
            product_brand = data.get('brand') or brand
            
            # Create Product object
            product = Product(
                product_id=data.get('product_id', ''),
                brand=product_brand,
                model=data.get('model', '').strip(),
                sku=[data.get('sku')] if data.get('sku') else [],
                category=data.get('category'),
                product_name=data.get('product_name'),
                source_url=[url],
                images=images
            )
            
            return product
            
        except Exception as e:
            print(f"[{self.site_name}] Error creating product from data: {e}")
            return None
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """Get comprehensive scraping statistics."""
        session_stats = session_manager.get_session_stats()
        
        return {
            'site': self.site_name,
            'current_session': self.current_session,
            'session_requests': self.session_request_count,
            'error_counts': self.error_counts.copy(),
            'session_stats': session_stats
        }
    
    def reset_stats(self):
        """Reset scraping statistics."""
        self.error_counts = {
            'session_errors': 0,
            'timeout_errors': 0,
            'asp_errors': 0,
            'total_errors': 0
        }
        self.session_request_count = 0
    
    # Common utility methods
    def _is_valid_product_url(self, url: str) -> bool:
        """Basic URL validation - can be overridden by specific scrapers."""
        return bool(url and 'http' in url)
    
    async def _categorize_product(self, product_name: str, brand: str = "", description: str = "") -> str:
        """AI-powered product categorization with fallback."""
        from ..utils.ai_categorizer import ai_categorizer
        return await ai_categorizer.categorize_product(product_name, brand, description)