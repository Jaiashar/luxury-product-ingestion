# scraper/core.py


"""Main scraper orchestration."""

import asyncio
import os
import shutil
from typing import List, Dict, Any, Optional
from scrapfly import ScrapflyClient
from rich.console import Console
from rich.progress import Progress, TaskID
from rich.table import Table

from .config import ScraperConfig
from .utils.data_models import Product
from .utils.optimized_image_handler import ImageHandler
from .sites import TheRealRealScraper, VestiaireScraper, FashionphileScraper

class BrandScraper:
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.console = Console()
        
        # Initialize services
        self.scrapfly_client = ScrapflyClient(key=config.scrapfly.api_key)
        self.image_handler = ImageHandler(config.image_dir)
        
        # Initialize site scrapers
        self.scrapers = {
            'therealreal': TheRealRealScraper(self.scrapfly_client, config.scrapfly.rate_limit),
            'vestiaire': VestiaireScraper(self.scrapfly_client, config.scrapfly.rate_limit),
            'fashionphile': FashionphileScraper(self.scrapfly_client, config.scrapfly.rate_limit)
        }
        
        # Storage for processed products
        self.processed_products: List[Product] = []
    
    async def scrape_brand(self, brand: str, sites: Optional[List[str]] = None, force_rescrape: bool = False) -> List[Product]:
        """
        Scrape all products for a brand from specified sites.
        
        Args:
            brand: Brand name to scrape
            sites: List of site names to scrape from (defaults to all)
            force_rescrape: Whether to force re-scrape even if completed
        
        Returns:
            List of unique products found
        """
        if sites is None:
            sites = list(self.scrapers.keys())
        
        self.console.print(f"\n[bold blue]Starting scraping for brand: {brand}[/bold blue]")
        self.console.print(f"Sites to scrape: {', '.join(sites)}")
        
        brand_products = []
        
        with Progress() as progress:
            main_task = progress.add_task(f"Scraping {brand}", total=len(sites))
            
            for site_name in sites:
                if site_name not in self.scrapers:
                    self.console.print(f"[red]Unknown site: {site_name}[/red]")
                    continue
                
                # Check if site already completed (unless forcing)
                if not force_rescrape and self.progress_tracker.is_site_completed(brand, site_name):
                    self.console.print(f"[yellow]Skipping {site_name} - already completed (use --force to override)[/yellow]")
                    progress.advance(main_task)
                    continue
                
                try:
                    scraper = self.scrapers[site_name]
                    site_task = progress.add_task(f"Scraping {site_name}", total=None)
                    
                    # Scrape products from this site
                    raw_products = await scraper.scrape_brand(brand)
                    
                    self.console.print(f"[green]Found {len(raw_products)} products from {site_name}[/green]")
                    
                    # Process each product
                    for product in raw_products:
                        processed_product = await self._process_product(product, brand)
                        if processed_product:
                            brand_products.append(processed_product)
                    
                    # Mark site as completed
                    self.progress_tracker.mark_site_completed(brand, site_name)
                    progress.remove_task(site_task)
                    
                except Exception as e:
                    self.console.print(f"[red]Error scraping {site_name}: {e}[/red]")
                    self.progress_tracker.mark_site_failed(brand, site_name, str(e))
                
                progress.advance(main_task)
        
        # Update final progress
        self.progress_tracker.update_brand_progress(
            brand,
            products_found=len(brand_products),
            products_processed=len(self.processed_products),
            products_stored=len([p for p in self.processed_products if p.brand.lower() == brand.lower()])
        )
        
        self.console.print(f"\n[bold green]Completed scraping {brand}![/bold green]")
        self.console.print(f"Total unique products found: {len(brand_products)}")
        
        return brand_products
    
    async def _process_product(self, product: Product, brand: str) -> Optional[Product]:
        """Process a single product: deduplicate, categorize, and download images."""
        try:
            # Check for duplicates
            duplicate = await self.deduplication_service.is_duplicate(product, self.processed_products)
            if duplicate:
                self.console.print(f"[yellow]Duplicate found: {product.model} -> {duplicate.product_id}[/yellow]")
                # Merge data from duplicate
                await self._merge_product_data(duplicate, product)
                return None
            
            # Categorize product if not already categorized
            if not product.category:
                product.category = await self.deduplication_service.categorize_product(product)
            
            # Download images
            if product.images:
                image_urls = [img.url for img in product.images]
                downloaded_images = self.image_handler.download_images(
                    image_urls, 
                    brand, 
                    product.product_id,
                    max_images=10
                )
                product.images = downloaded_images
            
            # Add to processed products
            self.processed_products.append(product)
            
            self.console.print(f"[green]Processed: {product.model} ({len(product.images)} images)[/green]")
            return product
            
        except Exception as e:
            self.console.print(f"[red]Error processing product {product.model}: {e}[/red]")
            return None
    
    async def _merge_product_data(self, existing_product: Product, new_product: Product):
        """Merge data from a duplicate product into existing product."""
        # Merge SKUs
        for sku in new_product.sku:
            if sku not in existing_product.sku:
                existing_product.sku.append(sku)
        
        # Merge source URLs
        for url in new_product.source_url:
            if url not in existing_product.source_url:
                existing_product.source_url.append(url)
        
        # Merge images (download new ones)
        new_image_urls = [img.url for img in new_product.images]
        existing_image_urls = [img.url for img in existing_product.images]
        
        urls_to_download = [url for url in new_image_urls if url not in existing_image_urls]
        
        if urls_to_download:
            new_images = self.image_handler.download_images(
                urls_to_download,
                existing_product.brand,
                existing_product.product_id,
                max_images=10 - len(existing_product.images)
            )
            existing_product.images.extend(new_images)
        
        # Merge raw data
        for site, data in new_product.raw_data.items():
            existing_product.raw_data[site] = data
    
    def get_scraping_summary(self, brand: str) -> Table:
        """Generate a summary table of scraping results."""
        progress = self.progress_tracker.get_brand_progress(brand)
        brand_products = [p for p in self.processed_products if p.brand.lower() == brand.lower()]
        
        table = Table(title=f"Scraping Summary for {brand}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        
        table.add_row("Sites Completed", ", ".join(progress.sites_completed))
        table.add_row("Products Found", str(progress.products_found))
        table.add_row("Unique Products", str(len(brand_products)))
        table.add_row("Total Images", str(sum(len(p.images) for p in brand_products)))
        table.add_row("Failed URLs", str(len(progress.failed_urls)))
        table.add_row("Last Updated", progress.last_updated)
        
        # Category breakdown
        categories = {}
        for product in brand_products:
            cat = product.category or 'unknown'
            categories[cat] = categories.get(cat, 0) + 1
        
        for category, count in categories.items():
            table.add_row(f"  {category.title()}", str(count))
        
        return table
    
    def export_products_to_dict(self, brand: str) -> List[Dict[str, Any]]:
        """Export products for a brand to dictionary format (ready for database)."""
        brand_products = [p for p in self.processed_products if p.brand.lower() == brand.lower()]
        return [product.to_dict() for product in brand_products]
    
    def reset_brand_progress(self, brand: str):
        """Reset progress for a specific brand."""
        # Reset progress tracking
        if brand in self.progress_tracker.progress:
            del self.progress_tracker.progress[brand]
            self.progress_tracker.save_progress()
        
        # Clear processed products for this brand
        self.processed_products = [p for p in self.processed_products if p.brand.lower() != brand.lower()]
        
        # Clean up images for this brand
        brand_image_dir = os.path.join(self.config.image_dir, brand.lower().replace(' ', '_'))
        if os.path.exists(brand_image_dir):
            try:
                shutil.rmtree(brand_image_dir)
                self.console.print(f"[green]Cleaned up images for {brand}[/green]")
            except Exception as e:
                self.console.print(f"[yellow]Could not clean up images: {e}[/yellow]")
    
    async def close(self):
        """Clean up resources."""
        # Skip closing for now - ScrapFly client handles cleanup automatically
        pass