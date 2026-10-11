# scraper/sites/__init__.py
"""Site scrapers package."""
from .base import BaseSiteScraper
from .ai_fashionphile import AIFashionphileScraper
from .ai_therealreal import AITheRealRealScraper
from .ai_vestiaire import AIVestiaireScraper
# Luxury E-commerce Sites
from .ai_farfetch import AIFarfetchScraper
# Sneaker/Streetwear Sites
from .ai_stockx import AIStockXScraper  # NEW: Updated import
# Resale Sites
from .ai_rebag import AIRebagScraper

__all__ = [
    'BaseSiteScraper',
    'AIFashionphileScraper',
    'AITheRealRealScraper', 
    'AIVestiaireScraper',
    'AIFarfetchScraper',
    'AIStockXScraper',  # NEW: Updated name
    'AIRebagScraper'
]