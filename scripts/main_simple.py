"""Fixed main_simple.py - Enhanced with duplicate checking and S3 image fix + Rebag concurrency."""

import asyncio
import sys
import os

# Add the parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use optimized AWS storage
from optimized_aws_storage import OptimizedAWSStorage

# Import your existing scrapers
from scraper.sites.ai_farfetch import AIFarfetchScraper
from scraper.sites.ai_fashionphile import AIFashionphileScraper
from scraper.sites.ai_stockx import AIStockXScraper
from scraper.sites.ai_vestiaire import AIVestiaireScraper
from scraper.sites.ai_therealreal import AITheRealRealScraper
from scraper.sites.ai_rebag import AIRebagScraper
from scrapfly import ScrapflyClient

# Available scrapers
SCRAPERS = {
    'farfetch': AIFarfetchScraper,
    'fashionphile': AIFashionphileScraper,
    'stockx': AIStockXScraper,
    'vestiaire': AIVestiaireScraper,
    'therealreal': AITheRealRealScraper,
    'rebag': AIRebagScraper
}

# All brands to scrape
BRANDS = [
    'Balenciaga', 'Adidas', 'Bottega Veneta', 'Asics', 'Burberry', 'Common Projects',
    'Chanel', 'Converse', 'Chloé', 'Jordan Brand', 'Christian Louboutin', 'New Balance',
    'Coach', 'Nike', 'Céline', 'Off-White', 'Dior', 'Puma', 'Dolce & Gabbana', 'Reebok',
    'Fendi', 'Vans', 'Givenchy', 'Yeezy', 'Goyard', 'Gucci', 'Hermès', 'Loewe',
    'Louis Vuitton', 'MCM', 'Prada', 'Saint Laurent', 'Salvatore Ferragamo', 'Valentino'
]

async def scrape_and_store_simple(site: str, brand: str, max_products: int = None, 
                                skip_duplicates: bool = True, use_local_images: bool = False):
    """
    Enhanced scraping function with duplicate checking BEFORE image downloading
    and AI categorization to save processing time and resources.
    """
    print(f"🚀 Scraping {brand} from {site}")
    
    # Initialize AWS storage
    aws_storage = OptimizedAWSStorage()
    
    try:
        # Initialize scraper (just like your main.py)
        scrapfly_client = ScrapflyClient(key=os.getenv('SCRAPFLY_API_KEY'))
        scraper_class = SCRAPERS[site]
        
        # Create scraper with appropriate settings
        if site == "stockx":
            scraper = scraper_class(scrapfly_client, rate_limit=2.5, download_images=use_local_images)
        elif site == "therealreal":
            scraper = scraper_class(scrapfly_client, rate_limit=1.5, download_images=use_local_images)
        elif site == "farfetch":
            scraper = scraper_class(scrapfly_client, rate_limit=0.5, download_images=use_local_images)
        else:
            scraper = scraper_class(scrapfly_client, rate_limit=2.0, download_images=use_local_images)
        
        # This is the key - let the scraper handle pagination automatically
        # When max_products=None, it will scrape ALL pages
        # When max_products is set, it will limit the results
        print(f"🔍 Scraping {brand} - {'ALL pages' if max_products is None else f'up to {max_products} products'}")
        
        products = await scraper.scrape_brand_products(brand, max_products)
        
        if not products:
            print(f"❌ No products found for {brand} on {site}")
            aws_storage.log_failure(
                failure_type='no_products_found',
                brand=brand,
                site=site,
                error_details=f"No products found for {brand} on {site}"
            )
            return {'products': 0, 'stored': 0, 'images': 0, 'skipped': 0}
        
        print(f"✅ Found {len(products)} products for {brand} on {site}")
        
        # ===== NEW: DUPLICATE CHECKING BEFORE IMAGE PROCESSING =====
        print(f"🔍 Checking for duplicates among {len(products)} products...")
        
        # Check which products already exist
        product_check_result = check_products_for_duplicates(products, site, aws_storage, skip_duplicates)
        
        # Extract the filtered products
        products_to_process = product_check_result['new_products']
        skipped_duplicates = product_check_result['skipped_count']
        
        print(f"📊 Duplicate check results:")
        print(f"   - New products to process: {len(products_to_process)}")
        print(f"   - Skipped duplicates: {skipped_duplicates}")
        
        # If no new products, return early
        if not products_to_process:
            print(f"⏭️  All products are duplicates, skipping image processing and storage")
            return {'products': len(products), 'stored': 0, 'images': 0, 'skipped': skipped_duplicates}
        
        print(f"🎯 Processing {len(products_to_process)} new products")
        
        # ===== PROCESS ONLY NEW PRODUCTS =====
        
        # Handle images for NEW products only
        if use_local_images:
            # Upload local images to S3
            s3_result = await aws_storage.upload_local_images_to_s3_batch(products_to_process, site)
        else:
            # Upload directly to S3 with FIXED matching
            s3_result = await aws_storage.upload_images_to_s3_optimized(products_to_process, site)
        
        # Store in DynamoDB (duplicates already filtered out)
        db_result = aws_storage.store_products(products_to_process, site, skip_duplicates=False)  # No need to check again
        
        result = {
            'products': len(products),
            'stored': db_result['successful'],
            'images': s3_result['uploaded'],
            'skipped': skipped_duplicates
        }
        
        print(f"📊 {brand} on {site}: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Error scraping {brand} from {site}: {e}")
        aws_storage.log_failure(
            failure_type='scraping_error',
            brand=brand,
            site=site,
            error_details=str(e)
        )
        return {'products': 0, 'stored': 0, 'images': 0, 'skipped': 0}

def check_products_for_duplicates(products: list, site: str, aws_storage, skip_duplicates: bool = True) -> dict:
    """
    Check products for duplicates BEFORE image processing and AI categorization.
    Returns dict with 'new_products' and 'skipped_count'.
    """
    if not skip_duplicates:
        print(f"⏭️  Duplicate checking disabled - processing all {len(products)} products")
        return {'new_products': products, 'skipped_count': 0}
    
    new_products = []
    skipped_count = 0
    
    print(f"🔍 Checking {len(products)} products for existing entries in DynamoDB...")
    
    # Track progress for large batches
    check_interval = max(10, len(products) // 10)
    
    for i, product in enumerate(products, 1):
        # Progress logging
        if i % check_interval == 0 or i == len(products):
            print(f"   📊 Checked {i}/{len(products)} products... (Found {skipped_count} duplicates so far)")
        
        # Get source URL - handle both single URL and list
        if hasattr(product, 'source_url') and product.source_url:
            if isinstance(product.source_url, list):
                source_url = product.source_url[0] if product.source_url else ''
            else:
                source_url = product.source_url
        else:
            source_url = ''
        
        if not source_url:
            # No URL to check, consider it new
            new_products.append(product)
            print(f"   ℹ️  Product {i} has no source URL, treating as new")
            continue
        
        try:
            # Check if product exists in DynamoDB
            response = aws_storage.products_table.get_item(
                Key={
                    'source_url': source_url,
                    'site': site
                }
            )
            
            if 'Item' in response:
                # Product exists - log more details
                skipped_count += 1
                existing_item = response['Item']
                created_at = existing_item.get('created_at', 'unknown')
                product_name = getattr(product, 'product_name', 'Unknown Product')
                print(f"   ⚠️  DUPLICATE {skipped_count}: {product_name}")
                print(f"      URL: {source_url[:80]}...")
                print(f"      Originally scraped: {created_at[:19] if created_at != 'unknown' else 'unknown'}")
            else:
                # Product is new
                new_products.append(product)
                
        except Exception as e:
            # If check fails, assume it's new to be safe
            print(f"   ❌ Error checking product {i}: {e}")
            new_products.append(product)
    
    print(f"\n📊 DUPLICATE CHECK SUMMARY:")
    print(f"   ✅ New products: {len(new_products)}")
    print(f"   ⚠️  Duplicates found: {skipped_count}")
    print(f"   📈 Duplicate rate: {(skipped_count / len(products) * 100):.1f}%")
    
    return {
        'new_products': new_products,
        'skipped_count': skipped_count
    }

async def scrape_all_brands_from_site(site: str, max_products: int = None, 
                                    skip_duplicates: bool = True, use_local_images: bool = False):
    """Scrape all brands from a site, one at a time (like your original main.py)"""
    print(f"🌟 Scraping ALL brands from {site}")
    
    aws_storage = OptimizedAWSStorage()
    total_results = {'products': 0, 'stored': 0, 'images': 0, 'skipped': 0}
    successful_brands = []
    failed_brands = []
    
    # Process each brand sequentially (like your original main.py)
    for i, brand in enumerate(BRANDS, 1):
        print(f"\n📋 Brand {i}/{len(BRANDS)}: {brand}")
        
        try:
            # Scrape this brand completely before moving to next
            result = await scrape_and_store_simple(site, brand, max_products, skip_duplicates, use_local_images)
            
            # Update totals
            total_results['products'] += result['products']
            total_results['stored'] += result['stored']
            total_results['images'] += result['images']
            total_results['skipped'] += result['skipped']
            
            if result['products'] > 0:
                successful_brands.append(brand)
            else:
                failed_brands.append(brand)
                
        except Exception as e:
            print(f"❌ Error with {brand}: {e}")
            failed_brands.append(brand)
            continue
    
    # Summary
    print(f"\n🎯 FINAL RESULTS for {site}:")
    print(f"📊 Total products: {total_results['products']}")
    print(f"📄 Stored in DB: {total_results['stored']}")
    print(f"📸 Images uploaded: {total_results['images']}")
    print(f"⏭️  Skipped duplicates: {total_results['skipped']}")
    print(f"✅ Successful brands: {len(successful_brands)}")
    print(f"❌ Failed brands: {len(failed_brands)}")
    
    if failed_brands:
        print(f"Failed: {', '.join(failed_brands)}")
    
    return total_results

async def scrape_all_brands_from_site_concurrent(site: str, max_products: int = None, 
                                               skip_duplicates: bool = True, use_local_images: bool = False,
                                               max_concurrent: int = 20):
    """Scrape all brands from a site concurrently"""
    print(f"🌟 Scraping ALL brands from {site} with {max_concurrent} concurrent sessions")
    
    aws_storage = OptimizedAWSStorage()
    total_results = {'products': 0, 'stored': 0, 'images': 0, 'skipped': 0}
    successful_brands = []
    failed_brands = []
    
    # Create semaphore to limit concurrent scrapers
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def scrape_single_brand_with_session(brand: str, brand_index: int):
        """Scrape a single brand with its own session"""
        async with semaphore:  # Limit concurrency
            print(f"🚀 [{brand_index}/{len(BRANDS)}] Starting {brand} (concurrent)")
            
            try:
                # Each brand gets its own scraper instance and session
                result = await scrape_and_store_simple(site, brand, max_products, skip_duplicates, use_local_images)
                
                if result['products'] > 0:
                    successful_brands.append(brand)
                    print(f"✅ [{brand_index}/{len(BRANDS)}] {brand} completed: {result}")
                else:
                    failed_brands.append(brand)
                    print(f"❌ [{brand_index}/{len(BRANDS)}] {brand} failed: No products")
                
                return result
                
            except Exception as e:
                print(f"❌ [{brand_index}/{len(BRANDS)}] {brand} error: {e}")
                failed_brands.append(brand)
                return {'products': 0, 'stored': 0, 'images': 0, 'skipped': 0}
    
    # Create tasks for all brands
    tasks = []
    for i, brand in enumerate(BRANDS, 1):
        task = scrape_single_brand_with_session(brand, i)
        tasks.append(task)
    
    print(f"🎯 Starting {len(tasks)} concurrent brand scraping tasks...")
    
    # Run all tasks concurrently
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            brand = BRANDS[i]
            if isinstance(result, Exception):
                print(f"❌ {brand} failed with exception: {result}")
                failed_brands.append(brand)
            else:
                # Update totals
                total_results['products'] += result['products']
                total_results['stored'] += result['stored']
                total_results['images'] += result['images']
                total_results['skipped'] += result['skipped']
        
    except Exception as e:
        print(f"❌ Concurrent execution failed: {e}")
    
    # Summary
    print(f"\n🎯 CONCURRENT RESULTS for {site}:")
    print(f"📊 Total products: {total_results['products']}")
    print(f"📄 Stored in DB: {total_results['stored']}")
    print(f"📸 Images uploaded: {total_results['images']}")
    print(f"⏭️  Skipped duplicates: {total_results['skipped']}")
    print(f"✅ Successful brands: {len(successful_brands)}")
    print(f"❌ Failed brands: {len(failed_brands)}")
    
    if failed_brands:
        print(f"Failed: {', '.join(failed_brands)}")
    
    return total_results

async def scrape_multiple_sites_parallel(sites: list, max_products: int = None, 
                                       skip_duplicates: bool = True, use_local_images: bool = False):
    """
    Run multiple sites in parallel - each site processes its brands sequentially
    This is the only parallelization we do - keep it simple
    """
    print(f"🚀 Running {len(sites)} sites in parallel")
    
    # Create tasks for each site
    tasks = []
    for site in sites:
        task = scrape_all_brands_from_site(site, max_products, skip_duplicates, use_local_images)
        tasks.append(task)
    
    # Run sites in parallel
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        total_all = {'products': 0, 'stored': 0, 'images': 0, 'skipped': 0}
        
        for i, result in enumerate(results):
            site = sites[i]
            if isinstance(result, Exception):
                print(f"❌ Site {site} failed: {result}")
            else:
                print(f"✅ Site {site} completed successfully")
                total_all['products'] += result['products']
                total_all['stored'] += result['stored']
                total_all['images'] += result['images']
                total_all['skipped'] += result['skipped']
        
        print(f"\n🎯 TOTAL ACROSS ALL SITES:")
        print(f"📊 Products: {total_all['products']}")
        print(f"📄 Stored: {total_all['stored']}")
        print(f"📸 Images: {total_all['images']}")
        print(f"⏭️  Skipped: {total_all['skipped']}")
        
        return total_all
        
    except Exception as e:
        print(f"❌ Parallel execution failed: {e}")
        return {'products': 0, 'stored': 0, 'images': 0, 'skipped': 0}

async def main():
    """Simple main function - just like your original main.py but with AWS storage"""
    print("🎯 Simple Luxury Scraper - AWS Edition (Enhanced)")
    
    # Check API keys
    if not os.getenv('SCRAPFLY_API_KEY'):
        print("❌ Missing SCRAPFLY_API_KEY")
        return
    
    if not os.getenv('ANTHROPIC_API_KEY'):
        print("❌ Missing ANTHROPIC_API_KEY")
        return
    
    # Setup AWS
    aws_storage = OptimizedAWSStorage()
    aws_storage.setup_infrastructure()
    
    # Choose image handling
    print("\n🖼️  Image handling:")
    print("1. Direct S3 (faster, fixed)")
    print("2. Local then S3 (compatible)")
    
    img_choice = input("Choice (1-2, default 1): ").strip() or "1"
    use_local_images = img_choice == "2"
    
    # Choose what to scrape
    print("\n🎯 What to scrape:")
    print("1. Single brand from single site")
    print("2. All brands from single site")
    print("3. All brands from multiple sites (parallel)")
    print("4. All brands from ALL sites (parallel)")
    print("5. Show stats")
    
    choice = input("Choice (1-5): ").strip()
    
    if choice == "1":
        # Single brand, single site
        print(f"\nSites: {', '.join(SCRAPERS.keys())}")
        site = input("Site: ").lower()
        if site not in SCRAPERS:
            print("❌ Invalid site")
            return
        
        brand = input("Brand: ")
        production = input("Production mode (all products)? (y/n): ").lower() == 'y'
        max_products = None if production else int(input("Max products (50): ") or 50)
        
        result = await scrape_and_store_simple(site, brand, max_products, True, use_local_images)
        print(f"Final: {result}")
        
    elif choice == "2":
        # All brands from single site - NOW WITH CONCURRENT OPTION
        print(f"\nSites: {', '.join(SCRAPERS.keys())}")
        site = input("Site: ").lower()
        if site not in SCRAPERS:
            print("❌ Invalid site")
            return
        
        production = input("Production mode (all products per brand)? (y/n): ").lower() == 'y'
        max_products = None if production else int(input("Max products per brand (50): ") or 50)
        
        # NEW: Ask about concurrent mode for Rebag
        if site == 'rebag':
            concurrent = input("Use concurrent mode (20 sessions)? (y/n): ").lower() == 'y'
            if concurrent:
                result = await scrape_all_brands_from_site_concurrent(site, max_products, True, use_local_images, 20)
            else:
                result = await scrape_all_brands_from_site(site, max_products, True, use_local_images)
        else:
            result = await scrape_all_brands_from_site(site, max_products, True, use_local_images)
        
        print(f"Final: {result}")
        
    elif choice == "3":
        # Multiple sites (user choice)
        print(f"\nSites: {', '.join(SCRAPERS.keys())}")
        sites_input = input("Sites (comma separated): ").lower()
        sites = [s.strip() for s in sites_input.split(',')]
        
        invalid = [s for s in sites if s not in SCRAPERS]
        if invalid:
            print(f"❌ Invalid sites: {invalid}")
            return
        
        production = input("Production mode? (y/n): ").lower() == 'y'
        max_products = None if production else int(input("Max products per brand (50): ") or 50)
        
        result = await scrape_multiple_sites_parallel(sites, max_products, True, use_local_images)
        print(f"Final: {result}")
        
    elif choice == "4":
        # All sites
        production = input("Production mode? (y/n): ").lower() == 'y'
        max_products = None if production else int(input("Max products per brand (50): ") or 50)
        
        print(f"\nThis will scrape {len(BRANDS)} brands from {len(SCRAPERS)} sites")
        if input("Continue? (y/n): ").lower() != 'y':
            return
        
        all_sites = list(SCRAPERS.keys())
        result = await scrape_multiple_sites_parallel(all_sites, max_products, True, use_local_images)
        print(f"Final: {result}")
        
    elif choice == "5":
        # Show stats
        aws_storage.print_monitoring_report()
        
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    asyncio.run(main())