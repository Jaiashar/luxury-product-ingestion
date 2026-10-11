# scraper/mappings/brand_urls.py
"""Brand URL mappings for all supported sites."""

from typing import Dict, List, Optional, Union
from dataclasses import dataclass

@dataclass
class BrandMapping:
    """Brand mapping for a specific site."""
    brand_name: str
    url: Union[str, List[str]]  # Now supports both single URL and list of URLs
    gender: str = "women"  # "women", "men", "unisex"
    category: Optional[str] = None  # Optional category hint
    active: bool = True  # Whether this mapping is currently working

class BrandURLMappings:
    """Centralized brand URL mappings for all sites."""
    
    def __init__(self):
        # Core luxury brands we want to support
        self.CORE_BRANDS = [
            # LVMH Group
            "Louis Vuitton", "Dior", "Céline", "Loewe", "Fendi",
            
            # Kering Group  
            "Gucci", "Saint Laurent", "Bottega Veneta", "Balenciaga", "Prada",
            
            # Other Luxury
            "Chanel", "Hermès", "Valentino", "Burberry", "Chloé",
            "Christian Louboutin", "Dolce & Gabbana", "Givenchy", "Goyard",
            "MCM", "Coach", "Salvatore Ferragamo",
            
            # Sports/Streetwear
            "Nike", "Adidas", "Jordan Brand", "New Balance", "Puma", 
            "Reebok", "Vans", "Converse", "Asics", "Yeezy",
            
            # Contemporary
            "Off-White", "Common Projects"
        ]
        
        # Brand mappings by site
        self.mappings = {
            "farfetch": self._get_farfetch_mappings(),
            "net_a_porter": self._get_nap_mappings(),
            "fashionphile": self._get_fashionphile_mappings(),
            "stockx": self._get_stockx_mappings(),
            "therealreal": self._get_therealreal_mappings(),
            "rebag": self._get_rebag_mappings(),  # NEW: Rebag mappings
            "vestiaire": self._get_vestiaire_mappings(),  # NEW: Vestiaire Collective mappings
            # Add more sites as we build them
        }

    def find_brand_mapping(self, site: str, brand_query: str) -> Optional[BrandMapping]:
        """Find brand mapping with flexible matching."""
        site_mappings = self.mappings.get(site.lower(), {})
        brand_query_lower = brand_query.lower()
        
        # 1. Try exact match first
        if brand_query_lower in site_mappings and site_mappings[brand_query_lower].active:
            return site_mappings[brand_query_lower]
        
        # 2. Try partial matching - brand query contains mapping key
        for key, mapping in site_mappings.items():
            if mapping.active and key in brand_query_lower:
                return mapping
        
        # 3. Try reverse matching - mapping brand name is in query
        for key, mapping in site_mappings.items():
            if mapping.active:
                # Extract base brand name (remove "Pre-Owned", "Women", "Men")
                base_brand = mapping.brand_name.lower()
                base_brand = base_brand.replace(' pre-owned', '').replace(' women', '').replace(' men', '')
                
                if base_brand in brand_query_lower:
                    return mapping
        
        # 4. Try key contains brand query
        for key, mapping in site_mappings.items():
            if mapping.active and brand_query_lower in key:
                return mapping
        
        return None

    def _get_rebag_mappings(self) -> Dict[str, BrandMapping]:
        """Rebag brand URL mappings - luxury handbags and accessories focused."""
        return {
            # LVMH Group Brands
            "louis vuitton": BrandMapping(
                brand_name="Louis Vuitton",
                url="https://shop.rebag.com/collections/louis-vuitton",
                gender="unisex",
                category="luxury-handbags"
            ),
            "christian dior": BrandMapping(
                brand_name="Christian Dior",
                url="https://shop.rebag.com/collections/christian-dior",
                gender="unisex",
                category="luxury-handbags"
            ),
            "dior": BrandMapping(
                brand_name="Christian Dior",
                url="https://shop.rebag.com/collections/christian-dior",
                gender="unisex",
                category="luxury-handbags"
            ),
            "fendi": BrandMapping(
                brand_name="Fendi",
                url="https://shop.rebag.com/collections/fendi",
                gender="unisex",
                category="luxury-handbags"
            ),
            "celine": BrandMapping(
                brand_name="Celine",
                url="https://shop.rebag.com/collections/celine",
                gender="unisex",
                category="luxury-handbags"
            ),
            "loewe": BrandMapping(
                brand_name="Loewe",
                url="https://shop.rebag.com/collections/loewe",
                gender="unisex",
                category="luxury-handbags"
            ),
            "givenchy": BrandMapping(
                brand_name="Givenchy",
                url="https://shop.rebag.com/collections/givenchy",
                gender="unisex",
                category="luxury-handbags"
            ),
            
            # Kering Group Brands
            "gucci": BrandMapping(
                brand_name="Gucci",
                url="https://shop.rebag.com/collections/gucci",
                gender="unisex",
                category="luxury-handbags"
            ),
            "saint laurent": BrandMapping(
                brand_name="Saint Laurent",
                url="https://shop.rebag.com/collections/saint-laurent",
                gender="unisex",
                category="luxury-handbags"
            ),
            "yves saint laurent": BrandMapping(
                brand_name="Yves Saint Laurent",
                url="https://shop.rebag.com/collections/saint-laurent",
                gender="unisex",
                category="luxury-handbags"
            ),
            "bottega veneta": BrandMapping(
                brand_name="Bottega Veneta",
                url="https://shop.rebag.com/collections/bottega-veneta",
                gender="unisex",
                category="luxury-handbags"
            ),
            "balenciaga": BrandMapping(
                brand_name="Balenciaga",
                url="https://shop.rebag.com/collections/balenciaga",
                gender="unisex",
                category="luxury-handbags"
            ),
            "alexander mcqueen": BrandMapping(
                brand_name="Alexander McQueen",
                url="https://shop.rebag.com/collections/alexander-mcqueen",
                gender="unisex",
                category="luxury-handbags"
            ),
            
            # Independent Luxury Brands
            "chanel": BrandMapping(
                brand_name="Chanel",
                url="https://shop.rebag.com/collections/chanel",
                gender="unisex",
                category="luxury-handbags"
            ),
            "hermes": BrandMapping(
                brand_name="Hermès",
                url="https://shop.rebag.com/collections/hermes",
                gender="unisex",
                category="luxury-handbags"
            ),
            "hermès": BrandMapping(
                brand_name="Hermès",
                url="https://shop.rebag.com/collections/hermes",
                gender="unisex",
                category="luxury-handbags"
            ),
            "prada": BrandMapping(
                brand_name="Prada",
                url="https://shop.rebag.com/collections/prada",
                gender="unisex",
                category="luxury-handbags"
            ),
            "miu miu": BrandMapping(
                brand_name="Miu Miu",
                url="https://shop.rebag.com/collections/miu-miu",
                gender="unisex",
                category="luxury-handbags"
            ),
            "valentino": BrandMapping(
                brand_name="Valentino",
                url="https://shop.rebag.com/collections/valentino",
                gender="unisex",
                category="luxury-handbags"
            ),
            "burberry": BrandMapping(
                brand_name="Burberry",
                url="https://shop.rebag.com/collections/burberry",
                gender="unisex",
                category="luxury-handbags"
            ),
            "versace": BrandMapping(
                brand_name="Versace",
                url="https://shop.rebag.com/collections/versace",
                gender="unisex",
                category="luxury-handbags"
            ),
            "dolce gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://shop.rebag.com/collections/dolce-gabbana",
                gender="unisex",
                category="luxury-handbags"
            ),
            "dolce & gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://shop.rebag.com/collections/dolce-gabbana",
                gender="unisex",
                category="luxury-handbags"
            ),
            
            # Contemporary Luxury
            "chloe": BrandMapping(
                brand_name="Chloé",
                url="https://shop.rebag.com/collections/chloe",
                gender="unisex",
                category="luxury-handbags"
            ),
            "chloé": BrandMapping(
                brand_name="Chloé",
                url="https://shop.rebag.com/collections/chloe",
                gender="unisex",
                category="luxury-handbags"
            ),
            "marc jacobs": BrandMapping(
                brand_name="Marc Jacobs",
                url="https://shop.rebag.com/collections/marc-jacobs",
                gender="unisex",
                category="luxury-handbags"
            ),
            "tom ford": BrandMapping(
                brand_name="Tom Ford",
                url="https://shop.rebag.com/collections/tom-ford",
                gender="unisex",
                category="luxury-handbags"
            ),
            "stella mccartney": BrandMapping(
                brand_name="Stella McCartney",
                url="https://shop.rebag.com/collections/stella-mccartney",
                gender="unisex",
                category="luxury-handbags"
            ),
            "jacquemus": BrandMapping(
                brand_name="Jacquemus",
                url="https://shop.rebag.com/collections/jacquemus",
                gender="unisex",
                category="luxury-handbags"
            ),
            "mansur gavriel": BrandMapping(
                brand_name="Mansur Gavriel",
                url="https://shop.rebag.com/collections/mansur-gavriel",
                gender="unisex",
                category="luxury-handbags"
            ),
            
            # Accessible Luxury
            "coach": BrandMapping(
                brand_name="Coach",
                url="https://shop.rebag.com/collections/coach",
                gender="unisex",
                category="accessible-luxury"
            ),
            "michael kors": BrandMapping(
                brand_name="Michael Kors",
                url="https://shop.rebag.com/collections/michael-kors",
                gender="unisex",
                category="accessible-luxury"
            ),
            "kate spade": BrandMapping(
                brand_name="Kate Spade",
                url="https://shop.rebag.com/collections/kate-spade",
                gender="unisex",
                category="accessible-luxury"
            ),
            "tory burch": BrandMapping(
                brand_name="Tory Burch",
                url="https://shop.rebag.com/collections/tory-burch",
                gender="unisex",
                category="accessible-luxury"
            ),
            "furla": BrandMapping(
                brand_name="Furla",
                url="https://shop.rebag.com/collections/furla",
                gender="unisex",
                category="accessible-luxury"
            ),
            "polene": BrandMapping(
                brand_name="Polene",
                url="https://shop.rebag.com/collections/polene",
                gender="unisex",
                category="contemporary"
            ),
            
            # Jewelry & Watch Brands (if available on Rebag)
            "cartier": BrandMapping(
                brand_name="Cartier",
                url="https://shop.rebag.com/collections/cartier",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://shop.rebag.com/collections/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany & co": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://shop.rebag.com/collections/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "van cleef arpels": BrandMapping(
                brand_name="Van Cleef & Arpels",
                url="https://shop.rebag.com/collections/van-cleef-arpels",
                gender="unisex",
                category="jewelry"
            ),
            "bulgari": BrandMapping(
                brand_name="Bulgari",
                url="https://shop.rebag.com/collections/bulgari",
                gender="unisex",
                category="jewelry"
            ),
            
            # Watch Brands
            "rolex": BrandMapping(
                brand_name="Rolex",
                url="https://shop.rebag.com/collections/rolex",
                gender="unisex",
                category="watches"
            ),
            "omega": BrandMapping(
                brand_name="Omega",
                url="https://shop.rebag.com/collections/omega",
                gender="unisex",
                category="watches"
            ),
            "patek philippe": BrandMapping(
                brand_name="Patek Philippe",
                url="https://shop.rebag.com/collections/patek-philippe",
                gender="unisex",
                category="watches"
            ),
            "audemars piguet": BrandMapping(
                brand_name="Audemars Piguet",
                url="https://shop.rebag.com/collections/audemars-piguet",
                gender="unisex",
                category="watches"
            ),
            
            # Emerging Contemporary Brands
            "staud": BrandMapping(
                brand_name="Staud",
                url="https://shop.rebag.com/collections/staud",
                gender="unisex",
                category="contemporary"
            ),
            "cult gaia": BrandMapping(
                brand_name="Cult Gaia",
                url="https://shop.rebag.com/collections/cult-gaia",
                gender="unisex",
                category="contemporary"
            ),
            "wandler": BrandMapping(
                brand_name="Wandler",
                url="https://shop.rebag.com/collections/wandler",
                gender="unisex",
                category="contemporary"
            ),
            "by far": BrandMapping(
                brand_name="By Far",
                url="https://shop.rebag.com/collections/by-far",
                gender="unisex",
                category="contemporary"
            ),
            "jw anderson": BrandMapping(
                brand_name="JW Anderson",
                url="https://shop.rebag.com/collections/jw-anderson",
                gender="unisex",
                category="contemporary"
            ),
            "ganni": BrandMapping(
                brand_name="Ganni",
                url="https://shop.rebag.com/collections/ganni",
                gender="unisex",
                category="contemporary"
            ),
        }
    
    def _get_farfetch_mappings(self) -> Dict[str, BrandMapping]:
        """Farfetch brand URL mappings with both new and pre-owned options for women and men."""
        return {
            # LVMH Brands - Louis Vuitton (Pre-owned only)
            "louis vuitton women": BrandMapping(
                brand_name="Louis Vuitton Women",
                url=["https://www.farfetch.com/shopping/women/louis-vuitton-pre-owned/items.aspx"],
                gender="women",
                category="pre-owned"
            ),
            "louis vuitton men": BrandMapping(
                brand_name="Louis Vuitton Men",
                url=["https://www.farfetch.com/shopping/men/louis-vuitton-pre-owned/items.aspx"],
                gender="men",
                category="pre-owned"
            ),
            
            # Dior (Pre-owned only)
            "dior women": BrandMapping(
                brand_name="Dior Women",
                url=["https://www.farfetch.com/shopping/women/christian-dior-pre-owned/items.aspx"],
                gender="women",
                category="pre-owned"
            ),
            "dior men": BrandMapping(
                brand_name="Dior Men",
                url=["https://www.farfetch.com/shopping/men/christian-dior-pre-owned/items.aspx"],
                gender="men",
                category="pre-owned"
            ),
            
            # Céline (Pre-owned only)
            "celine women": BrandMapping(
                brand_name="Céline Women",
                url=["https://www.farfetch.com/shopping/women/celine-pre-owned/items.aspx"], 
                gender="women",
                category="pre-owned"
            ),
            "celine men": BrandMapping(
                brand_name="Céline Men",
                url=["https://www.farfetch.com/shopping/men/celine-pre-owned/items.aspx"], 
                gender="men",
                category="pre-owned"
            ),
            
            # Loewe (Both new and pre-owned - combined into single entries per gender)
            "loewe women": BrandMapping(
                brand_name="Loewe Women",
                url=[
                    "https://www.farfetch.com/shopping/women/designer-loewe/items.aspx",
                    "https://www.farfetch.com/shopping/women/loewe-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "loewe men": BrandMapping(
                brand_name="Loewe Men",
                url=[
                    "https://www.farfetch.com/shopping/men/designer-loewe/items.aspx",
                    "https://www.farfetch.com/shopping/men/loewe-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Fendi (Both new and pre-owned - combined)
            "fendi women": BrandMapping(
                brand_name="Fendi Women",
                url=[
                    "https://www.farfetch.com/shopping/women/designer-fendi/items.aspx",
                    "https://www.farfetch.com/shopping/women/fendi-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "fendi men": BrandMapping(
                brand_name="Fendi Men",
                url=[
                    "https://www.farfetch.com/shopping/men/designer-fendi/items.aspx",
                    "https://www.farfetch.com/shopping/men/fendi-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Kering Brands - Gucci (Both new and pre-owned - combined)
            "gucci women": BrandMapping(
                brand_name="Gucci Women",
                url=[
                    "https://www.farfetch.com/shopping/women/gucci/items.aspx",
                    "https://www.farfetch.com/shopping/women/gucci-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "gucci men": BrandMapping(
                brand_name="Gucci Men",
                url=[
                    "https://www.farfetch.com/shopping/men/gucci/items.aspx",
                    "https://www.farfetch.com/shopping/men/gucci-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Saint Laurent (Both new and pre-owned - combined)
            "saint laurent women": BrandMapping(
                brand_name="Saint Laurent Women",
                url=[
                    "https://www.farfetch.com/shopping/women/saint-laurent/items.aspx",
                    "https://www.farfetch.com/shopping/women/designer-saint-laurent-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "saint laurent men": BrandMapping(
                brand_name="Saint Laurent Men",
                url=[
                    "https://www.farfetch.com/shopping/men/saint-laurent/items.aspx",
                    "https://www.farfetch.com/shopping/men/designer-saint-laurent-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Premium Brands with Pre-Owned Options
            "chanel women": BrandMapping(
                brand_name="Chanel Women",
                url=["https://www.farfetch.com/shopping/women/designer-chanel-pre-owned/items.aspx"],
                gender="women",
                category="pre-owned"
            ),
            "chanel men": BrandMapping(
                brand_name="Chanel Men",
                url=["https://www.farfetch.com/shopping/men/designer-chanel-pre-owned/items.aspx"],
                gender="men",
                category="pre-owned"
            ),
            "hermes women": BrandMapping(
                brand_name="Hermès Women",
                url=["https://www.farfetch.com/shopping/women/hermes-pre-owned/items.aspx"],
                gender="women",
                category="pre-owned"
            ),
            "hermes men": BrandMapping(
                brand_name="Hermès Men",
                url=["https://www.farfetch.com/shopping/men/hermes-pre-owned/items.aspx"],
                gender="men",
                category="pre-owned"
            ),
            
            # Bottega Veneta (pre-owned only)
            "bottega veneta women": BrandMapping(
                brand_name="Bottega Veneta Women", 
                url=["https://www.farfetch.com/shopping/women/bottega-veneta-pre-owned/items.aspx"],
                gender="women",
                category="pre-owned"
            ),
            "bottega veneta men": BrandMapping(
                brand_name="Bottega Veneta Men", 
                url=["https://www.farfetch.com/shopping/men/bottega-veneta-pre-owned/items.aspx"],
                gender="men",
                category="pre-owned"
            ),
            
            # Balenciaga (Both new and pre-owned - combined)
            "balenciaga women": BrandMapping(
                brand_name="Balenciaga Women",
                url=[
                    "https://www.farfetch.com/shopping/women/balenciaga/items.aspx",
                    "https://www.farfetch.com/shopping/women/balenciaga-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "balenciaga men": BrandMapping(
                brand_name="Balenciaga Men",
                url=[
                    "https://www.farfetch.com/shopping/men/balenciaga/items.aspx",
                    "https://www.farfetch.com/shopping/men/balenciaga-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Prada (Both new and pre-owned - combined)
            "prada women": BrandMapping(
                brand_name="Prada Women",
                url=[
                    "https://www.farfetch.com/shopping/women/prada/items.aspx",
                    "https://www.farfetch.com/shopping/women/prada-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "prada men": BrandMapping(
                brand_name="Prada Men",
                url=[
                    "https://www.farfetch.com/shopping/men/prada/items.aspx",
                    "https://www.farfetch.com/shopping/men/prada-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Valentino (Both new and pre-owned - combined)
            "valentino women": BrandMapping(
                brand_name="Valentino Women",
                url=[
                    "https://www.farfetch.com/shopping/women/designer-valentino-garavani/items.aspx",
                    "https://www.farfetch.com/shopping/women/designer-valentino-garavani-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "valentino men": BrandMapping(
                brand_name="Valentino Men",
                url=[
                    "https://www.farfetch.com/shopping/men/designer-valentino-garavani/items.aspx",
                    "https://www.farfetch.com/shopping/men/designer-valentino-garavani-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Burberry (Both new and pre-owned - combined)
            "burberry women": BrandMapping(
                brand_name="Burberry Women",
                url=[
                    "https://www.farfetch.com/shopping/women/burberry/items.aspx",
                    "https://www.farfetch.com/shopping/women/burberry-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "burberry men": BrandMapping(
                brand_name="Burberry Men",
                url=[
                    "https://www.farfetch.com/shopping/men/burberry/items.aspx",
                    "https://www.farfetch.com/shopping/men/burberry-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Off-White (Both new and pre-owned - combined)
            "off-white women": BrandMapping(
                brand_name="Off-White Women",
                url=[
                    "https://www.farfetch.com/shopping/women/off-white/items.aspx",
                    "https://www.farfetch.com/shopping/women/designer-off-white-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "off-white men": BrandMapping(
                brand_name="Off-White Men",
                url=[
                    "https://www.farfetch.com/shopping/men/off-white/items.aspx",
                    "https://www.farfetch.com/shopping/men/designer-off-white-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Common Projects (new only)
            "common projects women": BrandMapping(
                brand_name="Common Projects Women",
                url=["https://www.farfetch.com/shopping/women/common-projects/items.aspx"],
                gender="women"
            ),
            "common projects men": BrandMapping(
                brand_name="Common Projects Men",
                url=["https://www.farfetch.com/shopping/men/common-projects/items.aspx"],
                gender="men"
            ),
            
            # Chloé (Both new and pre-owned - combined)
            "chloe women": BrandMapping(
                brand_name="Chloé Women",
                url=[
                    "https://www.farfetch.com/shopping/women/chloe/items.aspx",
                    "https://www.farfetch.com/shopping/women/designer-chloe-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "chloe men": BrandMapping(
                brand_name="Chloé Men",
                url=["https://www.farfetch.com/shopping/men/chloe/items.aspx"],
                gender="men"
            ),
            
            # Christian Louboutin (Both new and pre-owned - combined)
            "christian louboutin women": BrandMapping(
                brand_name="Christian Louboutin Women",
                url=[
                    "https://www.farfetch.com/shopping/women/christian-louboutin/items.aspx",
                    "https://www.farfetch.com/shopping/women/designer-christian-louboutin-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "christian louboutin men": BrandMapping(
                brand_name="Christian Louboutin Men",
                url=[
                    "https://www.farfetch.com/shopping/men/christian-louboutin/items.aspx",
                    "https://www.farfetch.com/shopping/men/designer-christian-louboutin-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Dolce & Gabbana (Both new and pre-owned - combined)
            "dolce gabbana women": BrandMapping(
                brand_name="Dolce & Gabbana Women",
                url=[
                    "https://www.farfetch.com/shopping/women/dolce-gabbana/items.aspx",
                    "https://www.farfetch.com/shopping/women/dolce-gabbana-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "dolce gabbana men": BrandMapping(
                brand_name="Dolce & Gabbana Men",
                url=[
                    "https://www.farfetch.com/shopping/men/dolce-gabbana/items.aspx",
                    "https://www.farfetch.com/shopping/men/dolce-gabbana-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Givenchy (Both new and pre-owned - combined)
            "givenchy women": BrandMapping(
                brand_name="Givenchy Women",
                url=[
                    "https://www.farfetch.com/shopping/women/designer-givenchy/items.aspx",
                    "https://www.farfetch.com/shopping/women/givenchy-pre-owned/items.aspx"
                ],
                gender="women"
            ),
            "givenchy men": BrandMapping(
                brand_name="Givenchy Men",
                url=[
                    "https://www.farfetch.com/shopping/men/designer-givenchy/items.aspx",
                    "https://www.farfetch.com/shopping/men/givenchy-pre-owned/items.aspx"
                ],
                gender="men"
            ),
            
            # Coach (Both new and pre-owned - combined)
            "coach women": BrandMapping(
                brand_name="Coach Women",
                url=[
                    "https://www.farfetch.com/shopping/women/coach/items.aspx",
                    "https://www.farfetch.com/shopping/women/coach-vintage/items.aspx"
                ],
                gender="women"
            ),
            "coach men": BrandMapping(
                brand_name="Coach Men",
                url=["https://www.farfetch.com/shopping/men/coach/items.aspx"],
                gender="men"
            ),
            
            # Adidas (new only)
            "adidas women": BrandMapping(
                brand_name="Adidas Women",
                url=["https://www.farfetch.com/shopping/women/adidas/items.aspx"],
                gender="women"
            ),
            "adidas men": BrandMapping(
                brand_name="Adidas Men",
                url=["https://www.farfetch.com/shopping/men/adidas/items.aspx"],
                gender="men"
            ),
        }
    
    def _get_fashionphile_mappings(self) -> Dict[str, BrandMapping]:
        """Fashionphile brand URL mappings - luxury pre-owned only."""
        return {
            # Top Luxury Brands - LVMH Group
            "chanel": BrandMapping(
                brand_name="Chanel",
                url="https://www.fashionphile.com/shop/brands/chanel",
                gender="unisex",
                category="pre-owned"
            ),
            "louis vuitton": BrandMapping(
                brand_name="Louis Vuitton",
                url="https://www.fashionphile.com/shop/brands/louis-vuitton",
                gender="unisex",
                category="pre-owned"
            ),
            "dior": BrandMapping(
                brand_name="Dior",
                url="https://www.fashionphile.com/shop/brands/christian-dior",
                gender="unisex",
                category="pre-owned"
            ),
            "christian dior": BrandMapping(
                brand_name="Christian Dior",
                url="https://www.fashionphile.com/shop/brands/christian-dior",
                gender="unisex",
                category="pre-owned"
            ),
            "fendi": BrandMapping(
                brand_name="Fendi",
                url="https://www.fashionphile.com/shop/brands/fendi",
                gender="unisex",
                category="pre-owned"
            ),
            "celine": BrandMapping(
                brand_name="Celine",
                url="https://www.fashionphile.com/shop/brands/celine",
                gender="unisex",
                category="pre-owned"
            ),
            "loewe": BrandMapping(
                brand_name="Loewe",
                url="https://www.fashionphile.com/shop/brands/loewe",
                gender="unisex",
                category="pre-owned"
            ),
            
            # Kering Group
            "gucci": BrandMapping(
                brand_name="Gucci",
                url="https://www.fashionphile.com/shop/brands/gucci",
                gender="unisex",
                category="pre-owned"
            ),
            "saint laurent": BrandMapping(
                brand_name="Saint Laurent",
                url="https://www.fashionphile.com/shop/brands/saint-laurent",
                gender="unisex",
                category="pre-owned"
            ),
            "yves saint laurent": BrandMapping(
                brand_name="Yves Saint Laurent",
                url="https://www.fashionphile.com/shop/brands/saint-laurent",
                gender="unisex",
                category="pre-owned"
            ),
            "bottega veneta": BrandMapping(
                brand_name="Bottega Veneta",
                url="https://www.fashionphile.com/shop/brands/bottega-veneta",
                gender="unisex",
                category="pre-owned"
            ),
            "balenciaga": BrandMapping(
                brand_name="Balenciaga",
                url="https://www.fashionphile.com/shop/brands/balenciaga",
                gender="unisex",
                category="pre-owned"
            ),
            
            # Independent Luxury Brands
            "hermes": BrandMapping(
                brand_name="Hermès",
                url="https://www.fashionphile.com/shop/brands/hermes",
                gender="unisex",
                category="pre-owned"
            ),
            "hermès": BrandMapping(
                brand_name="Hermès",
                url="https://www.fashionphile.com/shop/brands/hermes",
                gender="unisex",
                category="pre-owned"
            ),
            "prada": BrandMapping(
                brand_name="Prada",
                url="https://www.fashionphile.com/shop/brands/prada",
                gender="unisex",
                category="pre-owned"
            ),
            "miu miu": BrandMapping(
                brand_name="Miu Miu",
                url="https://www.fashionphile.com/shop/brands/miu-miu",
                gender="unisex",
                category="pre-owned"
            ),
            "valentino": BrandMapping(
                brand_name="Valentino",
                url="https://www.fashionphile.com/shop/brands/valentino",
                gender="unisex",
                category="pre-owned"
            ),
            "burberry": BrandMapping(
                brand_name="Burberry",
                url="https://www.fashionphile.com/shop/brands/burberry",
                gender="unisex",
                category="pre-owned"
            ),
            "givenchy": BrandMapping(
                brand_name="Givenchy",
                url="https://www.fashionphile.com/shop/brands/givenchy",
                gender="unisex",
                category="pre-owned"
            ),
            "versace": BrandMapping(
                brand_name="Versace",
                url="https://www.fashionphile.com/shop/brands/versace",
                gender="unisex",
                category="pre-owned"
            ),
            "dolce gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://www.fashionphile.com/shop/brands/dolce-gabbana",
                gender="unisex",
                category="pre-owned"
            ),
            "dolce & gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://www.fashionphile.com/shop/brands/dolce-gabbana",
                gender="unisex",
                category="pre-owned"
            ),
            
            # Contemporary Luxury
            "chloe": BrandMapping(
                brand_name="Chloé",
                url="https://www.fashionphile.com/shop/brands/chloe",
                gender="unisex",
                category="pre-owned"
            ),
            "chloé": BrandMapping(
                brand_name="Chloé",
                url="https://www.fashionphile.com/shop/brands/chloe",
                gender="unisex",
                category="pre-owned"
            ),
            "marc jacobs": BrandMapping(
                brand_name="Marc Jacobs",
                url="https://www.fashionphile.com/shop/brands/marc-jacobs",
                gender="unisex",
                category="pre-owned"
            ),
            "tom ford": BrandMapping(
                brand_name="Tom Ford",
                url="https://www.fashionphile.com/shop/brands/tom-ford",
                gender="unisex",
                category="pre-owned"
            ),
            "alexander mcqueen": BrandMapping(
                brand_name="Alexander McQueen",
                url="https://www.fashionphile.com/shop/brands/alexander-mcqueen",
                gender="unisex",
                category="pre-owned"
            ),
            "stella mccartney": BrandMapping(
                brand_name="Stella McCartney",
                url="https://www.fashionphile.com/shop/brands/stella-mccartney",
                gender="unisex",
                category="pre-owned"
            ),
            
            # Accessible Luxury
            "coach": BrandMapping(
                brand_name="Coach",
                url="https://www.fashionphile.com/shop/brands/coach",
                gender="unisex",
                category="pre-owned"
            ),
            "michael kors": BrandMapping(
                brand_name="Michael Kors",
                url="https://www.fashionphile.com/shop/brands/michael-kors",
                gender="unisex",
                category="pre-owned"
            ),
            "kate spade": BrandMapping(
                brand_name="Kate Spade",
                url="https://www.fashionphile.com/shop/brands/kate-spade",
                gender="unisex",
                category="pre-owned"
            ),
            "tory burch": BrandMapping(
                brand_name="Tory Burch",
                url="https://www.fashionphile.com/shop/brands/tory-burch",
                gender="unisex",
                category="pre-owned"
            ),
            
            # Jewelry Brands
            "cartier": BrandMapping(
                brand_name="Cartier",
                url="https://www.fashionphile.com/shop/brands/cartier",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://www.fashionphile.com/shop/brands/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany & co": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://www.fashionphile.com/shop/brands/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "van cleef arpels": BrandMapping(
                brand_name="Van Cleef & Arpels",
                url="https://www.fashionphile.com/shop/brands/van-cleef-arpels",
                gender="unisex",
                category="jewelry"
            ),
            "bulgari": BrandMapping(
                brand_name="Bulgari",
                url="https://www.fashionphile.com/shop/brands/bulgari",
                gender="unisex",
                category="jewelry"
            ),
            
            # Watch Brands
            "rolex": BrandMapping(
                brand_name="Rolex",
                url="https://www.fashionphile.com/shop/brands/rolex",
                gender="unisex",
                category="watches"
            ),
            "omega": BrandMapping(
                brand_name="Omega",
                url="https://www.fashionphile.com/shop/brands/omega",
                gender="unisex",
                category="watches"
            ),
            "patek philippe": BrandMapping(
                brand_name="Patek Philippe",
                url="https://www.fashionphile.com/shop/brands/patek-philippe",
                gender="unisex",
                category="watches"
            ),
            "audemars piguet": BrandMapping(
                brand_name="Audemars Piguet",
                url="https://www.fashionphile.com/shop/brands/audemars-piguet",
                gender="unisex",
                category="watches"
            ),
        }
    
    def _get_nap_mappings(self) -> Dict[str, BrandMapping]:
        """Net-A-Porter brand URL mappings."""
        return {
            "gucci": BrandMapping(
                brand_name="Gucci",
                url="https://www.net-a-porter.com/en-us/shop/designer/gucci",
                gender="women"
            ),
            "prada": BrandMapping(
                brand_name="Prada",
                url="https://www.net-a-porter.com/en-us/shop/designer/prada",
                gender="women"
            ),
            "saint laurent": BrandMapping(
                brand_name="Saint Laurent",
                url="https://www.net-a-porter.com/en-us/shop/designer/saint-laurent",
                gender="women"
            ),
            "bottega veneta": BrandMapping(
                brand_name="Bottega Veneta",
                url="https://www.net-a-porter.com/en-us/shop/designer/bottega-veneta",
                gender="women"
            ),
            "valentino": BrandMapping(
                brand_name="Valentino",
                url="https://www.net-a-porter.com/en-us/shop/designer/valentino",
                gender="women"
            ),
        }
    
    def _get_stockx_mappings(self) -> Dict[str, BrandMapping]:
        """StockX brand URL mappings - COMPLETE MAPPINGS FOR SNEAKERS/STREETWEAR."""
        return {
            # === MAJOR SNEAKER BRANDS ===
            "nike": BrandMapping(
                brand_name="Nike",
                url="https://stockx.com/brands/nike",
                gender="unisex",
                category="sneakers"
            ),
            "adidas": BrandMapping(
                brand_name="Adidas",
                url="https://stockx.com/brands/adidas",
                gender="unisex",
                category="sneakers"
            ),
            "jordan": BrandMapping(
                brand_name="Jordan",
                url="https://stockx.com/brands/jordan",
                gender="unisex",
                category="sneakers"
            ),
            "air jordan": BrandMapping(
                brand_name="Air Jordan",
                url="https://stockx.com/brands/jordan",
                gender="unisex",
                category="sneakers"
            ),
            "yeezy": BrandMapping(
                brand_name="Yeezy",
                url="https://stockx.com/brands/yeezy",
                gender="unisex",
                category="sneakers"
            ),
            
            # === OTHER MAJOR FOOTWEAR BRANDS ===
            "new balance": BrandMapping(
                brand_name="New Balance",
                url="https://stockx.com/brands/new-balance",
                gender="unisex",
                category="sneakers"
            ),
            "puma": BrandMapping(
                brand_name="Puma",
                url="https://stockx.com/brands/puma",
                gender="unisex",
                category="sneakers"
            ),
            "converse": BrandMapping(
                brand_name="Converse",
                url="https://stockx.com/brands/converse",
                gender="unisex",
                category="sneakers"
            ),
            "vans": BrandMapping(
                brand_name="Vans",
                url="https://stockx.com/brands/vans",
                gender="unisex",
                category="sneakers"
            ),
            "reebok": BrandMapping(
                brand_name="Reebok",
                url="https://stockx.com/brands/reebok",
                gender="unisex",
                category="sneakers"
            ),
            "asics": BrandMapping(
                brand_name="ASICS",
                url="https://stockx.com/brands/asics",
                gender="unisex",
                category="sneakers"
            ),
            "under armour": BrandMapping(
                brand_name="Under Armour",
                url="https://stockx.com/brands/under-armour",
                gender="unisex",
                category="sneakers"
            ),
            
            # === LUXURY SNEAKER BRANDS ===
            "fear of god": BrandMapping(
                brand_name="Fear of God",
                url="https://stockx.com/brands/fear-of-god",
                gender="unisex",
                category="luxury-sneakers"
            ),
            "off-white": BrandMapping(
                brand_name="Off-White",
                url="https://stockx.com/brands/off-white",
                gender="unisex",
                category="streetwear"
            ),
            "balenciaga": BrandMapping(
                brand_name="Balenciaga",
                url="https://stockx.com/brands/balenciaga",
                gender="unisex",
                category="luxury-sneakers"
            ),
            "golden goose": BrandMapping(
                brand_name="Golden Goose",
                url="https://stockx.com/brands/golden-goose",
                gender="unisex",
                category="luxury-sneakers"
            ),
            "gucci": BrandMapping(
                brand_name="Gucci",
                url="https://stockx.com/brands/gucci",
                gender="unisex",
                category="luxury-sneakers"
            ),
            "louis vuitton": BrandMapping(
                brand_name="Louis Vuitton",
                url="https://stockx.com/brands/louis-vuitton",
                gender="unisex",
                category="luxury-sneakers"
            ),
            "dior": BrandMapping(
                brand_name="Dior",
                url="https://stockx.com/brands/dior",
                gender="unisex",
                category="luxury-sneakers"
            ),
            "maison margiela": BrandMapping(
                brand_name="Maison Margiela",
                url="https://stockx.com/brands/maison-margiela",
                gender="unisex",
                category="luxury-sneakers"
            ),
            "rick owens": BrandMapping(
                brand_name="Rick Owens",
                url="https://stockx.com/brands/rick-owens",
                gender="unisex",
                category="luxury-sneakers"
            ),
            
            # === STREETWEAR BRANDS ===
            "supreme": BrandMapping(
                brand_name="Supreme",
                url="https://stockx.com/brands/supreme",
                gender="unisex",
                category="streetwear"
            ),
            "bape": BrandMapping(
                brand_name="BAPE",
                url="https://stockx.com/brands/bape",
                gender="unisex",
                category="streetwear"
            ),
            "stone island": BrandMapping(
                brand_name="Stone Island",
                url="https://stockx.com/brands/stone-island",
                gender="unisex",
                category="streetwear"
            ),
            "kith": BrandMapping(
                brand_name="Kith",
                url="https://stockx.com/brands/kith",
                gender="unisex",
                category="streetwear"
            ),
            "human made": BrandMapping(
                brand_name="Human Made",
                url="https://stockx.com/brands/human-made",
                gender="unisex",
                category="streetwear"
            ),
            "cdg": BrandMapping(
                brand_name="CDG",
                url="https://stockx.com/brands/comme-des-garcons",
                gender="unisex",
                category="streetwear"
            ),
            "comme des garcons": BrandMapping(
                brand_name="Comme des Garcons",
                url="https://stockx.com/brands/comme-des-garcons",
                gender="unisex",
                category="streetwear"
            ),
            
            # === COLLABORATION/ARTIST BRANDS ===
            "travis scott": BrandMapping(
                brand_name="Travis Scott",
                url="https://stockx.com/brands/travis-scott",
                gender="unisex",
                category="collaborations"
            ),
            "fragment": BrandMapping(
                brand_name="Fragment",
                url="https://stockx.com/brands/fragment",
                gender="unisex",
                category="collaborations"
            ),
            
            # === DESIGNER FASHION ON STOCKX ===
            "thom browne": BrandMapping(
                brand_name="Thom Browne",
                url="https://stockx.com/brands/thom-browne",
                gender="unisex",
                category="designer"
            ),
            "acne studios": BrandMapping(
                brand_name="Acne Studios",
                url="https://stockx.com/brands/acne-studios",
                gender="unisex",
                category="designer"
            ),
            
            # === EMERGING/HYPE BRANDS ===
            "gallery dept": BrandMapping(
                brand_name="Gallery Dept",
                url="https://stockx.com/brands/gallery-dept",
                gender="unisex",
                category="streetwear"
            ),
            "chrome hearts": BrandMapping(
                brand_name="Chrome Hearts",
                url="https://stockx.com/brands/chrome-hearts",
                gender="unisex",
                category="luxury-streetwear"
            ),
            "rhude": BrandMapping(
                brand_name="Rhude",
                url="https://stockx.com/brands/rhude",
                gender="unisex",
                category="streetwear"
            ),
            
            # === ALTERNATIVE NAMES/SPELLINGS ===
            "air jordan 1": BrandMapping(
                brand_name="Air Jordan 1",
                url="https://stockx.com/brands/jordan",
                gender="unisex",
                category="sneakers"
            ),
            "aj1": BrandMapping(
                brand_name="AJ1",
                url="https://stockx.com/brands/jordan",
                gender="unisex",
                category="sneakers"
            ),
            "kanye west": BrandMapping(
                brand_name="Kanye West",
                url="https://stockx.com/brands/yeezy",
                gender="unisex",
                category="sneakers"
            ),
            "virgil abloh": BrandMapping(
                brand_name="Virgil Abloh",
                url="https://stockx.com/brands/off-white",
                gender="unisex",
                category="streetwear"
            ),
        }
    
    def _get_therealreal_mappings(self) -> Dict[str, BrandMapping]:
        """TheRealReal brand URL mappings - luxury pre-owned marketplace."""
        return {
            # LVMH Group Brands
            "louis vuitton": BrandMapping(
                brand_name="Louis Vuitton",
                url="https://www.therealreal.com/designers/louis-vuitton",
                gender="unisex",
                category="luxury-fashion"
            ),
            "christian dior": BrandMapping(
                brand_name="Christian Dior",
                url="https://www.therealreal.com/designers/christian-dior",
                gender="unisex",
                category="luxury-fashion"
            ),
            "dior": BrandMapping(
                brand_name="Christian Dior",
                url="https://www.therealreal.com/designers/christian-dior",
                gender="unisex",
                category="luxury-fashion"
            ),
            "fendi": BrandMapping(
                brand_name="Fendi",
                url="https://www.therealreal.com/designers/fendi",
                gender="unisex",
                category="luxury-fashion"
            ),
            "celine": BrandMapping(
                brand_name="Celine",
                url="https://www.therealreal.com/designers/celine",
                gender="unisex",
                category="luxury-fashion"
            ),
            "loewe": BrandMapping(
                brand_name="Loewe",
                url="https://www.therealreal.com/designers/loewe",
                gender="unisex",
                category="luxury-fashion"
            ),
            "givenchy": BrandMapping(
                brand_name="Givenchy",
                url="https://www.therealreal.com/designers/givenchy",
                gender="unisex",
                category="luxury-fashion"
            ),
            
            # Kering Group Brands
            "gucci": BrandMapping(
                brand_name="Gucci",
                url="https://www.therealreal.com/designers/gucci",
                gender="unisex",
                category="luxury-fashion"
            ),
            "saint laurent": BrandMapping(
                brand_name="Saint Laurent",
                url="https://www.therealreal.com/designers/saint-laurent",
                gender="unisex",
                category="luxury-fashion"
            ),
            "yves saint laurent": BrandMapping(
                brand_name="Yves Saint Laurent",
                url="https://www.therealreal.com/designers/saint-laurent",
                gender="unisex",
                category="luxury-fashion"
            ),
            "bottega veneta": BrandMapping(
                brand_name="Bottega Veneta",
                url="https://www.therealreal.com/designers/bottega-veneta",
                gender="unisex",
                category="luxury-fashion"
            ),
            "balenciaga": BrandMapping(
                brand_name="Balenciaga",
                url="https://www.therealreal.com/designers/balenciaga",
                gender="unisex",
                category="luxury-fashion"
            ),
            "alexander mcqueen": BrandMapping(
                brand_name="Alexander McQueen",
                url="https://www.therealreal.com/designers/alexander-mcqueen",
                gender="unisex",
                category="luxury-fashion"
            ),
            
            # Independent Luxury Brands
            "chanel": BrandMapping(
                brand_name="Chanel",
                url="https://www.therealreal.com/designers/chanel",
                gender="unisex",
                category="luxury-fashion"
            ),
            "hermes": BrandMapping(
                brand_name="Hermès",
                url="https://www.therealreal.com/designers/hermes",
                gender="unisex",
                category="luxury-fashion"
            ),
            "hermès": BrandMapping(
                brand_name="Hermès",
                url="https://www.therealreal.com/designers/hermes",
                gender="unisex",
                category="luxury-fashion"
            ),
            "prada": BrandMapping(
                brand_name="Prada",
                url="https://www.therealreal.com/designers/prada",
                gender="unisex",
                category="luxury-fashion"
            ),
            "miu miu": BrandMapping(
                brand_name="Miu Miu",
                url="https://www.therealreal.com/designers/miu-miu",
                gender="unisex",
                category="luxury-fashion"
            ),
            "valentino": BrandMapping(
                brand_name="Valentino",
                url="https://www.therealreal.com/designers/valentino",
                gender="unisex",
                category="luxury-fashion"
            ),
            "burberry": BrandMapping(
                brand_name="Burberry",
                url="https://www.therealreal.com/designers/burberry",
                gender="unisex",
                category="luxury-fashion"
            ),
            "versace": BrandMapping(
                brand_name="Versace",
                url="https://www.therealreal.com/designers/versace",
                gender="unisex",
                category="luxury-fashion"
            ),
            "dolce gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://www.therealreal.com/designers/dolce-gabbana",
                gender="unisex",
                category="luxury-fashion"
            ),
            "dolce & gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://www.therealreal.com/designers/dolce-gabbana",
                gender="unisex",
                category="luxury-fashion"
            ),
            
            # Contemporary Luxury
            "chloe": BrandMapping(
                brand_name="Chloé",
                url="https://www.therealreal.com/designers/chloe",
                gender="unisex",
                category="luxury-fashion"
            ),
            "chloé": BrandMapping(
                brand_name="Chloé",
                url="https://www.therealreal.com/designers/chloe",
                gender="unisex",
                category="luxury-fashion"
            ),
            "marc jacobs": BrandMapping(
                brand_name="Marc Jacobs",
                url="https://www.therealreal.com/designers/marc-jacobs",
                gender="unisex",
                category="luxury-fashion"
            ),
            "tom ford": BrandMapping(
                brand_name="Tom Ford",
                url="https://www.therealreal.com/designers/tom-ford",
                gender="unisex",
                category="luxury-fashion"
            ),
            "stella mccartney": BrandMapping(
                brand_name="Stella McCartney",
                url="https://www.therealreal.com/designers/stella-mccartney",
                gender="unisex",
                category="luxury-fashion"
            ),
            "isabel marant": BrandMapping(
                brand_name="Isabel Marant",
                url="https://www.therealreal.com/designers/isabel-marant",
                gender="unisex",
                category="luxury-fashion"
            ),
            "jacquemus": BrandMapping(
                brand_name="Jacquemus",
                url="https://www.therealreal.com/designers/jacquemus",
                gender="unisex",
                category="luxury-fashion"
            ),
            
            # Accessible Luxury
            "coach": BrandMapping(
                brand_name="Coach",
                url="https://www.therealreal.com/designers/coach",
                gender="unisex",
                category="accessible-luxury"
            ),
            "michael kors": BrandMapping(
                brand_name="Michael Kors",
                url="https://www.therealreal.com/designers/michael-kors",
                gender="unisex",
                category="accessible-luxury"
            ),
            "kate spade": BrandMapping(
                brand_name="Kate Spade",
                url="https://www.therealreal.com/designers/kate-spade",
                gender="unisex",
                category="accessible-luxury"
            ),
            "tory burch": BrandMapping(
                brand_name="Tory Burch",
                url="https://www.therealreal.com/designers/tory-burch",
                gender="unisex",
                category="accessible-luxury"
            ),
            "furla": BrandMapping(
                brand_name="Furla",
                url="https://www.therealreal.com/designers/furla",
                gender="unisex",
                category="accessible-luxury"
            ),
            
            # Jewelry Brands
            "cartier": BrandMapping(
                brand_name="Cartier",
                url="https://www.therealreal.com/designers/cartier",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://www.therealreal.com/designers/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany & co": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://www.therealreal.com/designers/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "van cleef arpels": BrandMapping(
                brand_name="Van Cleef & Arpels",
                url="https://www.therealreal.com/designers/van-cleef-arpels",
                gender="unisex",
                category="jewelry"
            ),
            "bulgari": BrandMapping(
                brand_name="Bulgari",
                url="https://www.therealreal.com/designers/bulgari",
                gender="unisex",
                category="jewelry"
            ),
            
            # Watch Brands
            "rolex": BrandMapping(
                brand_name="Rolex",
                url="https://www.therealreal.com/designers/rolex",
                gender="unisex",
                category="watches"
            ),
            "omega": BrandMapping(
                brand_name="Omega",
                url="https://www.therealreal.com/designers/omega",
                gender="unisex",
                category="watches"
            ),
            "patek philippe": BrandMapping(
                brand_name="Patek Philippe",
                url="https://www.therealreal.com/designers/patek-philippe",
                gender="unisex",
                category="watches"
            ),
            "audemars piguet": BrandMapping(
                brand_name="Audemars Piguet",
                url="https://www.therealreal.com/designers/audemars-piguet",
                gender="unisex",
                category="watches"
            ),
            
            # Designer Fashion
            "off-white": BrandMapping(
                brand_name="Off-White",
                url="https://www.therealreal.com/designers/off-white",
                gender="unisex",
                category="streetwear"
            ),
            "rick owens": BrandMapping(
                brand_name="Rick Owens",
                url="https://www.therealreal.com/designers/rick-owens",
                gender="unisex",
                category="designer"
            ),
            "comme des garcons": BrandMapping(
                brand_name="Comme des Garçons",
                url="https://www.therealreal.com/designers/comme-des-garcons",
                gender="unisex",
                category="designer"
            ),
            "acne studios": BrandMapping(
                brand_name="Acne Studios",
                url="https://www.therealreal.com/designers/acne-studios",
                gender="unisex",
                category="designer"
            ),
            "thom browne": BrandMapping(
                brand_name="Thom Browne",
                url="https://www.therealreal.com/designers/thom-browne",
                gender="unisex",
                category="designer"
            ),
            "maison margiela": BrandMapping(
                brand_name="Maison Margiela",
                url="https://www.therealreal.com/designers/maison-margiela",
                gender="unisex",
                category="designer"
            ),
            "golden goose": BrandMapping(
                brand_name="Golden Goose",
                url="https://www.therealreal.com/designers/golden-goose",
                gender="unisex",
                category="designer"
            ),
            
            # Emerging Contemporary Brands
            "ganni": BrandMapping(
                brand_name="Ganni",
                url="https://www.therealreal.com/designers/ganni",
                gender="unisex",
                category="contemporary"
            ),
            "staud": BrandMapping(
                brand_name="Staud",
                url="https://www.therealreal.com/designers/staud",
                gender="unisex",
                category="contemporary"
            ),
            "cult gaia": BrandMapping(
                brand_name="Cult Gaia",
                url="https://www.therealreal.com/designers/cult-gaia",
                gender="unisex",
                category="contemporary"
            ),
            "by far": BrandMapping(
                brand_name="By Far",
                url="https://www.therealreal.com/designers/by-far",
                gender="unisex",
                category="contemporary"
            ),
            "jw anderson": BrandMapping(
                brand_name="JW Anderson",
                url="https://www.therealreal.com/designers/jw-anderson",
                gender="unisex",
                category="contemporary"
            ),
            "wandler": BrandMapping(
                brand_name="Wandler",
                url="https://www.therealreal.com/designers/wandler",
                gender="unisex",
                category="contemporary"
            ),
            
            # Athletic/Streetwear
            "nike": BrandMapping(
                brand_name="Nike",
                url="https://www.therealreal.com/designers/nike",
                gender="unisex",
                category="athletic"
            ),
            "adidas": BrandMapping(
                brand_name="Adidas",
                url="https://www.therealreal.com/designers/adidas",
                gender="unisex",
                category="athletic"
            ),
            "stone island": BrandMapping(
                brand_name="Stone Island",
                url="https://www.therealreal.com/designers/stone-island",
                gender="unisex",
                category="streetwear"
            ),
    }
    
    def _get_vestiaire_mappings(self) -> Dict[str, BrandMapping]:
        """Vestiaire Collective brand URL mappings - global pre-owned luxury marketplace."""
        return {
            # LVMH Group Brands
            "louis vuitton": BrandMapping(
                brand_name="Louis Vuitton",
                url="https://www.vestiairecollective.com/louis-vuitton",
                gender="unisex",
                category="luxury-fashion"
            ),
            "christian dior": BrandMapping(
                brand_name="Christian Dior",
                url="https://www.vestiairecollective.com/christian-dior",
                gender="unisex",
                category="luxury-fashion"
            ),
            "dior": BrandMapping(
                brand_name="Christian Dior",
                url="https://www.vestiairecollective.com/christian-dior",
                gender="unisex",
                category="luxury-fashion"
            ),
            "fendi": BrandMapping(
                brand_name="Fendi",
                url="https://www.vestiairecollective.com/fendi",
                gender="unisex",
                category="luxury-fashion"
            ),
            "celine": BrandMapping(
                brand_name="Celine",
                url="https://www.vestiairecollective.com/celine",
                gender="unisex",
                category="luxury-fashion"
            ),
            "loewe": BrandMapping(
                brand_name="Loewe",
                url="https://www.vestiairecollective.com/loewe",
                gender="unisex",
                category="luxury-fashion"
            ),
            "givenchy": BrandMapping(
                brand_name="Givenchy",
                url="https://www.vestiairecollective.com/givenchy",
                gender="unisex",
                category="luxury-fashion"
            ),
            "bulgari": BrandMapping(
                brand_name="Bulgari",
                url="https://www.vestiairecollective.com/bulgari",
                gender="unisex",
                category="jewelry"
            ),
            "berluti": BrandMapping(
                brand_name="Berluti",
                url="https://www.vestiairecollective.com/berluti",
                gender="unisex",
                category="luxury-fashion"
            ),
            
            # Kering Group Brands
            "gucci": BrandMapping(
                brand_name="Gucci",
                url="https://www.vestiairecollective.com/gucci",
                gender="unisex",
                category="luxury-fashion"
            ),
            "saint laurent": BrandMapping(
                brand_name="Saint Laurent",
                url="https://www.vestiairecollective.com/saint-laurent",
                gender="unisex",
                category="luxury-fashion"
            ),
            "yves saint laurent": BrandMapping(
                brand_name="Yves Saint Laurent",
                url="https://www.vestiairecollective.com/saint-laurent",
                gender="unisex",
                category="luxury-fashion"
            ),
            "bottega veneta": BrandMapping(
                brand_name="Bottega Veneta",
                url="https://www.vestiairecollective.com/bottega-veneta",
                gender="unisex",
                category="luxury-fashion"
            ),
            "balenciaga": BrandMapping(
                brand_name="Balenciaga",
                url="https://www.vestiairecollective.com/balenciaga",
                gender="unisex",
                category="luxury-fashion"
            ),
            "alexander mcqueen": BrandMapping(
                brand_name="Alexander McQueen",
                url="https://www.vestiairecollective.com/alexander-mcqueen",
                gender="unisex",
                category="luxury-fashion"
            ),
            "brioni": BrandMapping(
                brand_name="Brioni",
                url="https://www.vestiairecollective.com/brioni",
                gender="unisex",
                category="luxury-fashion"
            ),
            
            # Independent Luxury Brands
            "chanel": BrandMapping(
                brand_name="Chanel",
                url="https://www.vestiairecollective.com/chanel",
                gender="unisex",
                category="luxury-fashion"
            ),
            "hermes": BrandMapping(
                brand_name="Hermès",
                url="https://www.vestiairecollective.com/hermes",
                gender="unisex",
                category="luxury-fashion"
            ),
            "hermès": BrandMapping(
                brand_name="Hermès",
                url="https://www.vestiairecollective.com/hermes",
                gender="unisex",
                category="luxury-fashion"
            ),
            "prada": BrandMapping(
                brand_name="Prada",
                url="https://www.vestiairecollective.com/prada",
                gender="unisex",
                category="luxury-fashion"
            ),
            "miu miu": BrandMapping(
                brand_name="Miu Miu",
                url="https://www.vestiairecollective.com/miu-miu",
                gender="unisex",
                category="luxury-fashion"
            ),
            "valentino": BrandMapping(
                brand_name="Valentino",
                url="https://www.vestiairecollective.com/valentino-garavani",
                gender="unisex",
                category="luxury-fashion"
            ),
            "burberry": BrandMapping(
                brand_name="Burberry",
                url="https://www.vestiairecollective.com/burberry",
                gender="unisex",
                category="luxury-fashion"
            ),
            "versace": BrandMapping(
                brand_name="Versace",
                url="https://www.vestiairecollective.com/versace",
                gender="unisex",
                category="luxury-fashion"
            ),
            "dolce gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://www.vestiairecollective.com/dolce-gabbana",
                gender="unisex",
                category="luxury-fashion"
            ),
            "dolce & gabbana": BrandMapping(
                brand_name="Dolce & Gabbana",
                url="https://www.vestiairecollective.com/dolce-gabbana",
                gender="unisex",
                category="luxury-fashion"
            ),
            "armani": BrandMapping(
                brand_name="Armani",
                url="https://www.vestiairecollective.com/armani",
                gender="unisex",
                category="luxury-fashion"
            ),
            "giorgio armani": BrandMapping(
                brand_name="Giorgio Armani",
                url="https://www.vestiairecollective.com/giorgio-armani",
                gender="unisex",
                category="luxury-fashion"
            ),
            "emporio armani": BrandMapping(
                brand_name="Emporio Armani",
                url="https://www.vestiairecollective.com/emporio-armani",
                gender="unisex",
                category="luxury-fashion"
            ),
            
            # Contemporary Luxury
            "chloe": BrandMapping(
                brand_name="Chloé",
                url="https://www.vestiairecollective.com/chloe",
                gender="unisex",
                category="luxury-fashion"
            ),
            "chloé": BrandMapping(
                brand_name="Chloé",
                url="https://www.vestiairecollective.com/chloe",
                gender="unisex",
                category="luxury-fashion"
            ),
            "marc jacobs": BrandMapping(
                brand_name="Marc Jacobs",
                url="https://www.vestiairecollective.com/marc-jacobs",
                gender="unisex",
                category="luxury-fashion"
            ),
            "tom ford": BrandMapping(
                brand_name="Tom Ford",
                url="https://www.vestiairecollective.com/tom-ford",
                gender="unisex",
                category="luxury-fashion"
            ),
            "stella mccartney": BrandMapping(
                brand_name="Stella McCartney",
                url="https://www.vestiairecollective.com/stella-mccartney",
                gender="unisex",
                category="luxury-fashion"
            ),
            "isabel marant": BrandMapping(
                brand_name="Isabel Marant",
                url="https://www.vestiairecollective.com/isabel-marant",
                gender="unisex",
                category="luxury-fashion"
            ),
            "jacquemus": BrandMapping(
                brand_name="Jacquemus",
                url="https://www.vestiairecollective.com/jacquemus",
                gender="unisex",
                category="luxury-fashion"
            ),
            "jil sander": BrandMapping(
                brand_name="Jil Sander",
                url="https://www.vestiairecollective.com/jil-sander",
                gender="unisex",
                category="luxury-fashion"
            ),
            "zimmermann": BrandMapping(
                brand_name="Zimmermann",
                url="https://www.vestiairecollective.com/zimmermann",
                gender="unisex",
                category="contemporary"
            ),
            
            # Accessible Luxury
            "coach": BrandMapping(
                brand_name="Coach",
                url="https://www.vestiairecollective.com/coach",
                gender="unisex",
                category="accessible-luxury"
            ),
            "michael kors": BrandMapping(
                brand_name="Michael Kors",
                url="https://www.vestiairecollective.com/michael-kors",
                gender="unisex",
                category="accessible-luxury"
            ),
            "kate spade": BrandMapping(
                brand_name="Kate Spade",
                url="https://www.vestiairecollective.com/kate-spade",
                gender="unisex",
                category="accessible-luxury"
            ),
            "tory burch": BrandMapping(
                brand_name="Tory Burch",
                url="https://www.vestiairecollective.com/tory-burch",
                gender="unisex",
                category="accessible-luxury"
            ),
            "furla": BrandMapping(
                brand_name="Furla",
                url="https://www.vestiairecollective.com/furla",
                gender="unisex",
                category="accessible-luxury"
            ),
            "longchamp": BrandMapping(
                brand_name="Longchamp",
                url="https://www.vestiairecollective.com/longchamp",
                gender="unisex",
                category="accessible-luxury"
            ),
            "mcm": BrandMapping(
                brand_name="MCM",
                url="https://www.vestiairecollective.com/mcm",
                gender="unisex",
                category="accessible-luxury"
            ),
            
            # Jewelry Brands
            "cartier": BrandMapping(
                brand_name="Cartier",
                url="https://www.vestiairecollective.com/cartier",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://www.vestiairecollective.com/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "tiffany & co": BrandMapping(
                brand_name="Tiffany & Co.",
                url="https://www.vestiairecollective.com/tiffany-co",
                gender="unisex",
                category="jewelry"
            ),
            "van cleef arpels": BrandMapping(
                brand_name="Van Cleef & Arpels",
                url="https://www.vestiairecollective.com/van-cleef-arpels",
                gender="unisex",
                category="jewelry"
            ),
            "boucheron": BrandMapping(
                brand_name="Boucheron",
                url="https://www.vestiairecollective.com/boucheron",
                gender="unisex",
                category="jewelry"
            ),
            "chopard": BrandMapping(
                brand_name="Chopard",
                url="https://www.vestiairecollective.com/chopard",
                gender="unisex",
                category="jewelry"
            ),
            
            # Watch Brands
            "rolex": BrandMapping(
                brand_name="Rolex",
                url="https://www.vestiairecollective.com/rolex",
                gender="unisex",
                category="watches"
            ),
            "omega": BrandMapping(
                brand_name="Omega",
                url="https://www.vestiairecollective.com/omega",
                gender="unisex",
                category="watches"
            ),
            "patek philippe": BrandMapping(
                brand_name="Patek Philippe",
                url="https://www.vestiairecollective.com/patek-philippe",
                gender="unisex",
                category="watches"
            ),
            "audemars piguet": BrandMapping(
                brand_name="Audemars Piguet",
                url="https://www.vestiairecollective.com/audemars-piguet",
                gender="unisex",
                category="watches"
            ),
            "richard mille": BrandMapping(
                brand_name="Richard Mille",
                url="https://www.vestiairecollective.com/richard-mille",
                gender="unisex",
                category="watches"
            ),
            "hublot": BrandMapping(
                brand_name="Hublot",
                url="https://www.vestiairecollective.com/hublot",
                gender="unisex",
                category="watches"
            ),
            
            # Designer Fashion
            "off-white": BrandMapping(
                brand_name="Off-White",
                url="https://www.vestiairecollective.com/off-white",
                gender="unisex",
                category="streetwear"
            ),
            "rick owens": BrandMapping(
                brand_name="Rick Owens",
                url="https://www.vestiairecollective.com/rick-owens",
                gender="unisex",
                category="designer"
            ),
            "comme des garcons": BrandMapping(
                brand_name="Comme des Garçons",
                url="https://www.vestiairecollective.com/comme-des-garcons",
                gender="unisex",
                category="designer"
            ),
            "acne studios": BrandMapping(
                brand_name="Acne Studios",
                url="https://www.vestiairecollective.com/acne-studios",
                gender="unisex",
                category="designer"
            ),
            "thom browne": BrandMapping(
                brand_name="Thom Browne",
                url="https://www.vestiairecollective.com/thom-browne",
                gender="unisex",
                category="designer"
            ),
            "maison margiela": BrandMapping(
                brand_name="Maison Margiela",
                url="https://www.vestiairecollective.com/maison-margiela",
                gender="unisex",
                category="designer"
            ),
            "golden goose": BrandMapping(
                brand_name="Golden Goose",
                url="https://www.vestiairecollective.com/golden-goose",
                gender="unisex",
                category="designer"
            ),
            "issey miyake": BrandMapping(
                brand_name="Issey Miyake",
                url="https://www.vestiairecollective.com/issey-miyake",
                gender="unisex",
                category="designer"
            ),
            "yohji yamamoto": BrandMapping(
                brand_name="Yohji Yamamoto",
                url="https://www.vestiairecollective.com/yohji-yamamoto",
                gender="unisex",
                category="designer"
            ),
            
            # Contemporary Brands
            "ganni": BrandMapping(
                brand_name="Ganni",
                url="https://www.vestiairecollective.com/ganni",
                gender="unisex",
                category="contemporary"
            ),
            "staud": BrandMapping(
                brand_name="Staud",
                url="https://www.vestiairecollective.com/staud",
                gender="unisex",
                category="contemporary"
            ),
            "cult gaia": BrandMapping(
                brand_name="Cult Gaia",
                url="https://www.vestiairecollective.com/cult-gaia",
                gender="unisex",
                category="contemporary"
            ),
            "by far": BrandMapping(
                brand_name="By Far",
                url="https://www.vestiairecollective.com/by-far",
                gender="unisex",
                category="contemporary"
            ),
            "jw anderson": BrandMapping(
                brand_name="JW Anderson",
                url="https://www.vestiairecollective.com/jw-anderson",
                gender="unisex",
                category="contemporary"
            ),
            "wandler": BrandMapping(
                brand_name="Wandler",
                url="https://www.vestiairecollective.com/wandler",
                gender="unisex",
                category="contemporary"
            ),
            "mansur gavriel": BrandMapping(
                brand_name="Mansur Gavriel",
                url="https://www.vestiairecollective.com/mansur-gavriel",
                gender="unisex",
                category="contemporary"
            ),
            "polene": BrandMapping(
                brand_name="Polene",
                url="https://www.vestiairecollective.com/polene",
                gender="unisex",
                category="contemporary"
            ),
            "rejina pyo": BrandMapping(
                brand_name="Rejina Pyo",
                url="https://www.vestiairecollective.com/rejina-pyo",
                gender="unisex",
                category="contemporary"
            ),
            
            # Athletic/Streetwear
            "nike": BrandMapping(
                brand_name="Nike",
                url="https://www.vestiairecollective.com/nike",
                gender="unisex",
                category="athletic"
            ),
            "adidas": BrandMapping(
                brand_name="Adidas",
                url="https://www.vestiairecollective.com/adidas",
                gender="unisex",
                category="athletic"
            ),
            "jordan": BrandMapping(
                brand_name="Jordan",
                url="https://www.vestiairecollective.com/jordan",
                gender="unisex",
                category="athletic"
            ),
            "asics": BrandMapping(
                brand_name="ASICS",
                url="https://www.vestiairecollective.com/asics",
                gender="unisex",
                category="athletic"
            ),
            "stone island": BrandMapping(
                brand_name="Stone Island",
                url="https://www.vestiairecollective.com/stone-island",
                gender="unisex",
                category="streetwear"
            ),
            "supreme": BrandMapping(
                brand_name="Supreme",
                url="https://www.vestiairecollective.com/supreme",
                gender="unisex",
                category="streetwear"
            ),
            "palace": BrandMapping(
                brand_name="Palace",
                url="https://www.vestiairecollective.com/palace",
                gender="unisex",
                category="streetwear"
            ),
            "stussy": BrandMapping(
                brand_name="Stüssy",
                url="https://www.vestiairecollective.com/stussy",
                gender="unisex",
                category="streetwear"
            ),
            "fear of god": BrandMapping(
                brand_name="Fear of God",
                url="https://www.vestiairecollective.com/fear-of-god",
                gender="unisex",
                category="streetwear"
            ),
            "essentials": BrandMapping(
                brand_name="Fear of God Essentials",
                url="https://www.vestiairecollective.com/essentials",
                gender="unisex",
                category="streetwear"
            ),
            
            # Eyewear
            "ray ban": BrandMapping(
                brand_name="Ray-Ban",
                url="https://www.vestiairecollective.com/ray-ban",
                gender="unisex",
                category="eyewear"
            ),
            "oliver peoples": BrandMapping(
                brand_name="Oliver Peoples",
                url="https://www.vestiairecollective.com/oliver-peoples",
                gender="unisex",
                category="eyewear"
            ),
            "celine eyewear": BrandMapping(
                brand_name="Celine Eyewear",
                url="https://www.vestiairecollective.com/celine-eyewear",
                gender="unisex",
                category="eyewear"
            ),
            
            # Footwear Specialists
            "christian louboutin": BrandMapping(
                brand_name="Christian Louboutin",
                url="https://www.vestiairecollective.com/christian-louboutin",
                gender="unisex",
                category="footwear"
            ),
            "jimmy choo": BrandMapping(
                brand_name="Jimmy Choo",
                url="https://www.vestiairecollective.com/jimmy-choo",
                gender="unisex",
                category="footwear"
            ),
            "manolo blahnik": BrandMapping(
                brand_name="Manolo Blahnik",
                url="https://www.vestiairecollective.com/manolo-blahnik",
                gender="unisex",
                category="footwear"
            ),
            "common projects": BrandMapping(
                brand_name="Common Projects",
                url="https://www.vestiairecollective.com/common-projects",
                gender="unisex",
                category="footwear"
            ),
            "dr martens": BrandMapping(
                brand_name="Dr. Martens",
                url="https://www.vestiairecollective.com/dr-martens",
                gender="unisex",
                category="footwear"
            ),
        }
    
    def get_brand_url(self, site: str, brand: str) -> Optional[BrandMapping]:
        """Get the URL mapping for a brand on a specific site."""
        site_mappings = self.mappings.get(site.lower(), {})
        return site_mappings.get(brand.lower())
    
    def get_supported_brands(self, site: str) -> List[str]:
        """Get list of brands supported by a site."""
        site_mappings = self.mappings.get(site.lower(), {})
        return [mapping.brand_name for mapping in site_mappings.values() if mapping.active]
    
    def get_sites_for_brand(self, brand: str) -> List[str]:
        """Get list of sites that support a brand."""
        sites = []
        brand_lower = brand.lower()
        
        for site, mappings in self.mappings.items():
            if brand_lower in mappings and mappings[brand_lower].active:
                sites.append(site)
        
        return sites
    
    def add_brand_mapping(self, site: str, brand: str, url: Union[str, List[str]], 
                         gender: str = "women", category: Optional[str] = None):
        """Add a new brand mapping."""
        if site not in self.mappings:
            self.mappings[site] = {}
        
        self.mappings[site][brand.lower()] = BrandMapping(
            brand_name=brand,
            url=url,
            gender=gender,
            category=category,
            active=True
        )
    
    def deactivate_brand_mapping(self, site: str, brand: str):
        """Deactivate a brand mapping (mark as not working)."""
        if site in self.mappings and brand.lower() in self.mappings[site]:
            self.mappings[site][brand.lower()].active = False
    
    def get_test_brands(self, site: str, limit: int = 5) -> List[BrandMapping]:
        """Get a subset of brands for testing a site."""
        site_mappings = self.mappings.get(site.lower(), {})
        active_mappings = [m for m in site_mappings.values() if m.active]
        return active_mappings[:limit]

# Global instance
brand_mappings = BrandURLMappings()