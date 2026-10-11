"""Monitoring dashboard for the luxury scraper."""

import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from optimized_aws_storage import AWSStorage

load_dotenv()

class ScraperMonitor:
    """Monitor scraper performance and failures."""
    
    def __init__(self):
        self.aws_storage = AWSStorage()
    
    def daily_report(self):
        """Generate daily monitoring report."""
        print("📊 DAILY SCRAPER REPORT")
        print("=" * 50)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get comprehensive stats
        stats = self.aws_storage.get_stats()
        
        # Overall metrics
        print(f"\n📈 OVERALL METRICS:")
        print(f"   Total Products: {stats.get('total_products', 0):,}")
        print(f"   Total Images: {stats.get('total_s3_objects', 0):,}")
        
        # Products by site
        print(f"\n🏢 PRODUCTS BY SITE:")
        site_stats = stats.get('products_by_site', {})
        for site, count in sorted(site_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"   {site.ljust(15)}: {count:,}")
        
        # Products by brand
        print(f"\n🏷️  TOP BRANDS:")
        brand_stats = stats.get('products_by_brand', {})
        top_brands = sorted(brand_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        for brand, count in top_brands:
            print(f"   {brand.ljust(20)}: {count:,}")
        
        # Failure analysis
        failure_summary = stats.get('failure_summary', {})
        total_failures = failure_summary.get('total_failures', 0)
        
        print(f"\n❌ FAILURES (24h): {total_failures}")
        if total_failures > 0:
            for failure_type, count in failure_summary.get('failure_types', {}).items():
                print(f"   {failure_type.ljust(20)}: {count}")
            
            print(f"\n🔥 MOST PROBLEMATIC:")
            brand_failures = failure_summary.get('brand_failures', {})
            if brand_failures:
                top_failed_brands = sorted(brand_failures.items(), key=lambda x: x[1], reverse=True)[:5]
                for brand, count in top_failed_brands:
                    print(f"   {brand.ljust(20)}: {count} failures")
        
        # Success rate calculation
        if stats.get('total_products', 0) > 0:
            success_rate = (stats.get('total_products', 0) / (stats.get('total_products', 0) + total_failures)) * 100
            print(f"\n📊 SUCCESS RATE: {success_rate:.1f}%")
        
        # Retry candidates
        retry_candidates = self.aws_storage.get_retry_candidates()
        print(f"\n🔄 RETRY QUEUE: {len(retry_candidates)} items")
        
        print("=" * 50)
    
    def failure_analysis(self, hours: int = 24):
        """Detailed failure analysis."""
        print(f"🔍 FAILURE ANALYSIS (Last {hours}h)")
        print("=" * 40)
        
        failure_summary = self.aws_storage.get_failure_summary(hours)
        
        if failure_summary.get('total_failures', 0) == 0:
            print("✅ No failures in this period!")
            return
        
        print(f"Total Failures: {failure_summary.get('total_failures', 0)}")
        
        # Failure types
        print(f"\n📋 BY TYPE:")
        for failure_type, count in failure_summary.get('failure_types', {}).items():
            print(f"   {failure_type}: {count}")
        
        # By brand
        print(f"\n🏷️  BY BRAND:")
        brand_failures = failure_summary.get('brand_failures', {})
        for brand, count in sorted(brand_failures.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {brand}: {count}")
        
        # By site
        print(f"\n🏢 BY SITE:")
        site_failures = failure_summary.get('site_failures', {})
        for site, count in sorted(site_failures.items(), key=lambda x: x[1], reverse=True):
            print(f"   {site}: {count}")
    
    def health_check(self):
        """Quick health check of the scraper system."""
        print("🏥 SYSTEM HEALTH CHECK")
        print("=" * 30)
        
        try:
            # Check AWS connectivity
            stats = self.aws_storage.get_stats()
            if 'error' in stats:
                print("❌ AWS Connection: FAILED")
                return False
            else:
                print("✅ AWS Connection: OK")
            
            # Check recent activity
            recent_failures = self.aws_storage.get_failure_summary(hours=1)
            recent_failure_count = recent_failures.get('total_failures', 0)
            
            if recent_failure_count > 50:  # Threshold for concern
                print(f"⚠️  Recent Failures: HIGH ({recent_failure_count})")
            elif recent_failure_count > 10:
                print(f"⚠️  Recent Failures: MODERATE ({recent_failure_count})")
            else:
                print(f"✅ Recent Failures: LOW ({recent_failure_count})")
            
            # Check for stuck processes (simplified)
            retry_queue = len(self.aws_storage.get_retry_candidates())
            if retry_queue > 100:
                print(f"⚠️  Retry Queue: HIGH ({retry_queue})")
            else:
                print(f"✅ Retry Queue: OK ({retry_queue})")
            
            return True
            
        except Exception as e:
            print(f"❌ Health Check Failed: {e}")
            return False
    
    def recommend_actions(self):
        """Recommend actions based on current state."""
        print("💡 RECOMMENDED ACTIONS")
        print("=" * 25)
        
        # Get current stats
        stats = self.aws_storage.get_stats()
        failure_summary = stats.get('failure_summary', {})
        
        # Check for high failure rates
        total_failures = failure_summary.get('total_failures', 0)
        if total_failures > 100:
            print("🚨 HIGH FAILURE RATE:")
            print("   - Check network connectivity")
            print("   - Review rate limiting settings")
            print("   - Consider reducing concurrent requests")
        
        # Check for specific failure types
        failure_types = failure_summary.get('failure_types', {})
        
        if failure_types.get('image_download', 0) > 20:
            print("🖼️  IMAGE DOWNLOAD ISSUES:")
            print("   - Increase image download timeout")
            print("   - Check image URLs are valid")
            print("   - Consider image CDN issues")
        
        if failure_types.get('scraping_error', 0) > 20:
            print("🕷️  SCRAPING ISSUES:")
            print("   - Check if sites changed structure")
            print("   - Review scraper selectors")
            print("   - Consider IP blocking")
        
        # Check retry queue
        retry_candidates = self.aws_storage.get_retry_candidates()
        if len(retry_candidates) > 50:
            print("🔄 LARGE RETRY QUEUE:")
            print("   - Run retry process")
            print("   - python main_simple.py (option 5)")
        
        # Check for missing data
        total_products = stats.get('total_products', 0)
        if total_products < 1000:  # Assuming you expect more
            print("📊 LOW PRODUCT COUNT:")
            print("   - Run full scrape")
            print("   - Check brand mappings")
            print("   - Verify scraper functionality")

async def main():
    """Main monitoring interface."""
    monitor = ScraperMonitor()
    
    print("🔍 LUXURY SCRAPER MONITOR")
    print("=" * 30)
    print("1. Daily Report")
    print("2. Failure Analysis")
    print("3. Health Check")
    print("4. Recommended Actions")
    print("5. Live Monitoring (every 5 minutes)")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        monitor.daily_report()
    elif choice == "2":
        hours = int(input("Hours to analyze (default 24): ") or 24)
        monitor.failure_analysis(hours)
    elif choice == "3":
        monitor.health_check()
    elif choice == "4":
        monitor.recommend_actions()
    elif choice == "5":
        print("🔄 Starting live monitoring (Ctrl+C to stop)...")
        try:
            while True:
                print(f"\n⏰ {datetime.now().strftime('%H:%M:%S')}")
                monitor.health_check()
                print("Sleeping for 5 minutes...")
                await asyncio.sleep(300)  # 5 minutes
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped")
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    asyncio.run(main())