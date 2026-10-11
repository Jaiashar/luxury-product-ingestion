# main.py - Enhanced entry point supporting multiple scrapers including TheRealReal and Vestiaire
"""Enhanced CLI for the AI-powered brand scraper with multi-site support."""

import asyncio
import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from scraper.sites.ai_farfetch import AIFarfetchScraper
from scraper.sites.ai_fashionphile import AIFashionphileScraper
from scraper.sites.ai_stockx import AIStockXScraper
from scraper.sites.ai_rebag import AIRebagScraper
from scraper.sites.ai_vestiaire import AIVestiaireScraper  # NEW: Import Vestiaire scraper
from scraper.sites.ai_therealreal import AITheRealRealScraper  # NEW: Import TheRealReal scraper
from scraper.mappings.brand_urls import brand_mappings
from scrapfly import ScrapflyClient

console = Console()

# Available scrapers
AVAILABLE_SCRAPERS = {
    "farfetch": {
        "class": AIFarfetchScraper,
        "name": "Farfetch",
        "description": "Luxury fashion marketplace (new & pre-owned)",
        "specialties": ["High-end fashion", "Designer brands", "Global inventory"]
    },
    "fashionphile": {
        "class": AIFashionphileScraper,
        "name": "Fashionphile",
        "description": "Ultra-luxury pre-owned marketplace",
        "specialties": ["Pre-owned luxury", "Authentication experts", "Rare pieces"]
    },
    "stockx": {
        "class": AIStockXScraper,
        "name": "StockX",
        "description": "Live marketplace for sneakers, streetwear & collectibles",
        "specialties": ["Sneakers", "Streetwear", "Collectibles", "Live pricing", "Authentication"]
    },
    "rebag": {
        "class": AIRebagScraper,
        "name": "Rebag",
        "description": "Luxury handbag & accessories resale marketplace",
        "specialties": ["Luxury handbags", "Designer accessories", "Authentication", "Pre-owned luxury"]
    },
    "vestiaire": {  # NEW: Vestiaire scraper
        "class": AIVestiaireScraper,
        "name": "Vestiaire Collective",
        "description": "Global marketplace for pre-owned designer fashion",
        "specialties": ["Pre-owned luxury", "Vintage fashion", "Designer pieces", "Global sellers"]
    },
    "therealreal": {  # NEW: TheRealReal scraper
        "class": AITheRealRealScraper,
        "name": "The RealReal",
        "description": "Authenticated luxury consignment marketplace",
        "specialties": ["Authenticated luxury", "Consignment", "Designer fashion", "Fine jewelry", "Art"]
    }
}

def display_available_scrapers():
    """Display available scrapers in a nice table."""
    table = Table(title="Available Scrapers")
    table.add_column("Site", style="cyan", no_wrap=True)
    table.add_column("Name", style="magenta")
    table.add_column("Description", style="green")
    table.add_column("Specialties", style="yellow")
    
    for site_key, scraper_info in AVAILABLE_SCRAPERS.items():
        specialties = ", ".join(scraper_info["specialties"])
        table.add_row(
            site_key,
            scraper_info["name"],
            scraper_info["description"],
            specialties
        )
    
    console.print("\n")
    console.print(table)
    console.print("\n")

def get_supported_brands_for_site(site: str) -> list:
    """Get supported brands for a specific site."""
    try:
        return brand_mappings.get_supported_brands(site)
    except Exception as e:
        console.print(f"[red]Error getting brands for {site}: {e}[/red]")
        return []

def display_supported_brands(site: str, limit: int = 10):
    """Display supported brands for a site."""
    brands = get_supported_brands_for_site(site)
    if not brands:
        console.print(f"[yellow]No brand mappings found for {site}[/yellow]")
        return
    
    console.print(f"\n[bold cyan]Supported brands for {site.title()}:[/bold cyan]")
    
    # Show first 'limit' brands
    display_brands = brands[:limit]
    for i, brand in enumerate(display_brands, 1):
        console.print(f"  {i:2d}. {brand}")
    
    if len(brands) > limit:
        console.print(f"  ... and {len(brands) - limit} more brands")
    
    console.print(f"\n[dim]Total: {len(brands)} brands supported[/dim]")

async def scrape_single_site(site: str, brand: str, max_products: int = None, download_images: bool = True) -> tuple:
    """Scrape a single site and return results and stats."""
    console.print(f"\n[bold blue]🚀 Starting {site.title()} scraper for {brand}[/bold blue]")
    
    # Get scraper class
    scraper_info = AVAILABLE_SCRAPERS.get(site)
    if not scraper_info:
        console.print(f"[red]❌ Unknown scraper: {site}[/red]")
        return [], {}
    
    # Initialize environment
    scrapfly_key = os.getenv('SCRAPFLY_API_KEY')
    if not scrapfly_key:
        console.print(f"[red]❌ SCRAPFLY_API_KEY not found[/red]")
        return [], {}
    
    try:
        # Initialize scraper with site-specific settings
        scrapfly_client = ScrapflyClient(key=scrapfly_key)
        scraper_class = scraper_info["class"]
        
        # Site-specific rate limits and settings
        if site == "stockx":
            scraper = scraper_class(
                scrapfly_client, 
                rate_limit=2.5,  # Conservative for StockX
                download_images=download_images
            )
        elif site == "rebag":
            scraper = scraper_class(
                scrapfly_client, 
                rate_limit=2.0,  # Conservative for Rebag
                download_images=download_images
            )
        elif site == "vestiaire":  # NEW: Vestiaire-specific settings
            # Vestiaire needs conservative settings for stability
            scraper = scraper_class(
                scrapfly_client, 
                rate_limit=2.0,  # Conservative for Vestiaire
                download_images=download_images
            )
        elif site == "therealreal":  # NEW: TheRealReal-specific settings
            # TheRealReal needs conservative settings similar to other luxury sites
            scraper = scraper_class(
                scrapfly_client, 
                rate_limit=1.5,  # Conservative for TheRealReal
                download_images=download_images
            )
        elif site == "farfetch":
            scraper = scraper_class(
                scrapfly_client, 
                rate_limit=0.5, 
                download_images=download_images
            )
        else:
            # Default settings
            scraper = scraper_class(
                scrapfly_client, 
                rate_limit=1.0, 
                download_images=download_images
            )
        
        # Start timing
        start_time = time.time()
        start_datetime = datetime.now()
        
        # Scrape products
        console.print(f"[bold]🔍 Scraping {brand} from {scraper_info['name']}...[/bold]")
        products = await scraper.scrape_brand_products(brand, max_products)
        
        # Calculate timing
        total_time = time.time() - start_time
        end_datetime = datetime.now()
        
        # Get final stats
        stats = scraper.get_scraping_stats()
        stats.update({
            'site': site,
            'brand': brand,
            'total_products': len(products),
            'start_time': start_datetime.strftime('%H:%M:%S'),
            'end_time': end_datetime.strftime('%H:%M:%S'),
            'total_duration': total_time,
            'products_per_minute': (len(products) / (total_time/60)) if products else 0
        })
        
        if products:
            console.print(f"[green]✅ {scraper_info['name']}: Found {len(products)} products in {total_time:.1f}s[/green]")
        else:
            console.print(f"[yellow]⚠️  {scraper_info['name']}: No products found[/yellow]")
        
        return products, stats
        
    except Exception as e:
        console.print(f"[red]❌ Error with {scraper_info['name']}: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return [], {}

async def scrape_multiple_sites(sites: list, brand: str, max_products: int = None, download_images: bool = True) -> tuple:
    """Scrape multiple sites concurrently."""
    console.print(f"\n[bold magenta]🚀 Multi-site scraping for {brand}[/bold magenta]")
    console.print(f"[dim]Sites: {', '.join(sites)}[/dim]")
    
    # Create tasks for each site
    tasks = []
    for site in sites:
        task = scrape_single_site(site, brand, max_products, download_images)
        tasks.append(task)
    
    # Run all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    all_products = []
    all_stats = []
    
    for i, result in enumerate(results):
        site = sites[i]
        if isinstance(result, Exception):
            console.print(f"[red]❌ {site.title()} failed: {result}[/red]")
            all_stats.append({'site': site, 'error': str(result)})
        else:
            products, stats = result
            all_products.extend(products)
            all_stats.append(stats)
    
    return all_products, all_stats

def display_scraping_summary(products: list, stats_list: list):
    """Display a comprehensive scraping summary."""
    console.print(f"\n[bold]📊 SCRAPING SUMMARY[/bold]")
    
    # Overall stats
    total_products = len(products)
    successful_sites = len([s for s in stats_list if s.get('total_products', 0) > 0])
    total_sites = len(stats_list)
    
    console.print(f"🎯 Total Products: [bold green]{total_products}[/bold green]")
    console.print(f"🏪 Successful Sites: [bold cyan]{successful_sites}/{total_sites}[/bold cyan]")
    
    # Per-site breakdown
    if len(stats_list) > 1:
        console.print(f"\n[bold]📋 Per-Site Breakdown:[/bold]")
        for stats in stats_list:
            if 'error' in stats:
                console.print(f"  ❌ {stats['site'].title()}: [red]{stats['error']}[/red]")
            else:
                site_products = stats.get('total_products', 0)
                duration = stats.get('total_duration', 0)
                rate = stats.get('products_per_minute', 0)
                console.print(f"  ✅ {stats['site'].title()}: {site_products} products in {duration:.1f}s ({rate:.1f}/min)")
    
    # Category breakdown
    if products:
        categories = {}
        for product in products:
            cat = product.category or 'unknown'
            categories[cat] = categories.get(cat, 0) + 1
        
        console.print(f"\n[bold]🏷️  Category Breakdown:[/bold]")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {cat}: {count}")
    
    # Brand breakdown (useful for multi-site)
    if products and len(stats_list) > 1:
        brands = {}
        for product in products:
            brand = product.brand or 'unknown'
            brands[brand] = brands.get(brand, 0) + 1
        
        console.print(f"\n[bold]🏷️  Brand Breakdown:[/bold]")
        for brand, count in sorted(brands.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {brand}: {count}")
    
    # Image stats
    if products:
        total_images = sum(len(p.images) for p in products)
        downloaded_images = sum(1 for p in products for img in p.images if img.local_path)
        console.print(f"\n[bold]📸 Image Stats:[/bold]")
        console.print(f"  Total Image URLs: {total_images}")
        console.print(f"  Downloaded Images: {downloaded_images}")

async def main():
    """Main entry point for the enhanced multi-scraper."""
    console.print("[bold blue]🔍 AI-Powered Multi-Site Brand Scraper[/bold blue]\n")
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
        console.print("[dim]✅ Loaded .env file[/dim]")
    except ImportError:
        console.print("[yellow]⚠️  python-dotenv not installed. Install with: pip install python-dotenv[/yellow]")
        console.print("[dim]Trying to read environment variables directly...[/dim]")
    
    # Verify API keys
    scrapfly_key = os.getenv('SCRAPFLY_API_KEY')
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    
    if not scrapfly_key:
        console.print("[red]❌ SCRAPFLY_API_KEY not found in environment variables[/red]")
        console.print("[yellow]Please set your ScrapFly API key as an environment variable or in .env file[/yellow]")
        return 1
    
    if not anthropic_key:
        console.print("[yellow]⚠️  ANTHROPIC_API_KEY not found - will use pattern matching only[/yellow]")
    else:
        console.print("[dim]✅ Anthropic API key found[/dim]")
    
    # Display available scrapers
    display_available_scrapers()
    
    # Get scraper selection with updated choices (now includes vestiaire and therealreal)
    scraper_choice = Prompt.ask(
        "Select scraper(s)",
        choices=["farfetch", "fashionphile", "stockx", "rebag", "vestiaire", "therealreal", "all", "list-brands"],
        default="vestiaire"  # NEW: Default to Vestiaire for testing
    )
    
    # Handle list-brands option
    if scraper_choice == "list-brands":
        site_to_list = Prompt.ask(
            "Which site's brands would you like to see?",
            choices=list(AVAILABLE_SCRAPERS.keys()),
            default="vestiaire"  # NEW: Default to Vestiaire
        )
        display_supported_brands(site_to_list, limit=20)  # Show more brands
        return 0
    
    # Determine which sites to scrape
    if scraper_choice == "all":
        selected_sites = list(AVAILABLE_SCRAPERS.keys())
        console.print("[bold yellow]🌐 Multi-site mode: Will scrape all available sites[/bold yellow]")
    else:
        selected_sites = [scraper_choice]
        console.print(f"[bold blue]🎯 Single-site mode: Will scrape {scraper_choice.title()}[/bold blue]")
    
    # Get brand from user
    brand = Prompt.ask("Enter brand name to scrape")
    
    # Show which sites support this brand
    console.print(f"\n[bold]🔍 Checking brand support for '{brand}':[/bold]")
    for site in selected_sites:
        mapping = brand_mappings.find_brand_mapping(site, brand)
        if mapping:
            console.print(f"  ✅ {site.title()}: {mapping.brand_name}")
        else:
            console.print(f"  ⚠️  {site.title()}: No specific mapping (will try fallback)")
    
    # Production vs Development mode
    production_mode = Confirm.ask("Production mode (scrape ALL products)?", default=False)
    
    # Ask about image downloads
    download_images = Confirm.ask("Download product images?", default=True)
    
    # Set max products based on mode
    if production_mode:
        max_products = None  # Scrape all products
        console.print("[bold yellow]🏭 Production Mode: Will scrape ALL available products[/bold yellow]")
    else:
        max_products = int(Prompt.ask("How many products to scrape per site?", default="5"))
        console.print(f"[bold blue]🧪 Development Mode: Will scrape {max_products} products per site[/bold blue]")
    
    try:
        # START OVERALL TIMING
        overall_start_time = time.time()
        overall_start_datetime = datetime.now()
        
        console.print(f"\n[bold]🚀 Starting scrape for {brand}...[/bold]")
        console.print(f"⏰ Started at: {overall_start_datetime.strftime('%H:%M:%S')}")
        
        # Scrape sites
        if len(selected_sites) == 1:
            # Single site scraping
            products, stats = await scrape_single_site(
                selected_sites[0], brand, max_products, download_images
            )
            all_stats = [stats] if stats else []
        else:
            # Multi-site scraping
            products, all_stats = await scrape_multiple_sites(
                selected_sites, brand, max_products, download_images
            )
        
        if not products:
            console.print(f"[red]❌ No products found for {brand} across selected sites[/red]")
            return 1
        
        # Display comprehensive summary
        display_scraping_summary(products, all_stats)
        
        # Export results
        if Confirm.ask("\nExport results to JSON?", default=True):
            # Create output directory
            output_dir = "./output"
            os.makedirs(output_dir, exist_ok=True)
            
            # Convert Product objects to dictionaries
            products_data = [product.to_dict() for product in products]
            
            # Create filename with site info
            brand_slug = brand.lower().replace(' ', '_').replace('&', 'and')
            if len(selected_sites) == 1:
                filename = f"{output_dir}/{brand_slug}_{selected_sites[0]}_products.json"
            else:
                sites_str = "_".join(selected_sites)
                filename = f"{output_dir}/{brand_slug}_multi_{sites_str}_products.json"
            
            # Include metadata in export
            export_data = {
                "metadata": {
                    "brand": brand,
                    "sites_scraped": selected_sites,
                    "scrape_datetime": overall_start_datetime.isoformat(),
                    "total_products": len(products),
                    "production_mode": production_mode,
                    "max_products_per_site": max_products,
                    "images_downloaded": download_images,
                    "stats": all_stats
                },
                "products": products_data
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            console.print(f"[green]💾 Exported to {filename}[/green]")
            
            # Show file stats
            file_size = os.path.getsize(filename) / 1024  # KB
            console.print(f"[dim]File size: {file_size:.1f} KB[/dim]")
        
        # OVERALL TIMING SUMMARY
        overall_total_time = time.time() - overall_start_time
        overall_end_datetime = datetime.now()

        console.print(f"\n[bold]⏰ OVERALL TIMING:[/bold]")
        console.print(f"🕐 Started: {overall_start_datetime.strftime('%H:%M:%S')}")
        console.print(f"🕐 Ended: {overall_end_datetime.strftime('%H:%M:%S')}")
        console.print(f"⏱️  Total Runtime: {overall_total_time:.1f}s ({overall_total_time/60:.1f} minutes)")
        if products:
            console.print(f"📊 Overall rate: {(len(products) / (overall_total_time/60)):.1f} products/minute")
        
        # Show per-site efficiency if multiple sites
        if len(selected_sites) > 1:
            console.print(f"\n[bold]⚡ Site Efficiency:[/bold]")
            for stats in all_stats:
                if 'error' not in stats and stats.get('total_products', 0) > 0:
                    site_rate = stats.get('products_per_minute', 0)
                    console.print(f"  {stats['site'].title()}: {site_rate:.1f} products/minute")

        console.print(f"\n[bold]🎉 Multi-site scraping completed successfully![/bold]")
        console.print(f"[dim]Total products from {len(selected_sites)} site(s): {len(products)}[/dim]")
        return 0
        
    except KeyboardInterrupt:
        console.print("\n[yellow]⏹️  Scraping interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1

def show_help():
    """Show help information."""
    help_text = """
[bold cyan]AI-Powered Multi-Site Brand Scraper[/bold cyan]

This tool scrapes luxury brand products from multiple e-commerce sites:

[bold]Available Sites:[/bold]
• Farfetch: Luxury fashion marketplace (new & pre-owned)
• Fashionphile: Ultra-luxury pre-owned marketplace
• StockX: Live marketplace for sneakers, streetwear & collectibles
• Rebag: Luxury handbag & accessories resale marketplace
• Vestiaire Collective: Global marketplace for pre-owned designer fashion
• The RealReal: Authenticated luxury consignment marketplace

[bold]Usage Examples:[/bold]
• Single site: Choose 'farfetch', 'fashionphile', 'stockx', 'rebag', 'vestiaire', or 'therealreal'
• Multi-site: Choose 'all' to scrape all sites concurrently
• List brands: Choose 'list-brands' to see supported brands

[bold]Site Specialties:[/bold]
• Farfetch: High-end fashion, designer brands, global inventory
• Fashionphile: Pre-owned luxury, authentication experts, rare pieces
• StockX: Sneakers, streetwear, collectibles, live pricing, authentication
• Rebag: Luxury handbags, designer accessories, authentication, pre-owned luxury
• Vestiaire Collective: Pre-owned luxury, vintage fashion, designer pieces, global sellers
• The RealReal: Authenticated luxury, consignment, designer fashion, fine jewelry, art

[bold]Features:[/bold]
• AI-powered product categorization
• Concurrent multi-site scraping
• Image downloading with optimization
• Comprehensive export with metadata
• Rate limiting and session management
• Site-specific optimization

[bold]Requirements:[/bold]
• SCRAPFLY_API_KEY (required)
• ANTHROPIC_API_KEY (optional, for AI categorization)

[bold]StockX-Specific Features:[/bold]
• Specialized for sneakers, streetwear, and collectibles
• Supports all major sneaker brands (Nike, Adidas, Jordan, etc.)
• Conservative scraping approach for site stability
• Optimized for streetwear and sneaker categorization
• Live marketplace pricing support
"""
    console.print(help_text)

if __name__ == "__main__":
    if len(os.sys.argv) > 1 and os.sys.argv[1] in ['--help', '-h']:
        show_help()
    else:
        asyncio.run(main())