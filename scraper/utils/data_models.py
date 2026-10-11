# scraper/utils/data_models.py
"""Pydantic models for data validation with AI categorization support."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import hashlib
import json
import asyncio

class ProductImage(BaseModel):
    image_id: str
    url: str
    local_path: Optional[str] = None
    file_size: Optional[int] = None

    # ADD THESE NEW LINES:
    s3_key: Optional[str] = None
    s3_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'image_id': self.image_id,
            'url': self.url,
            'local_path': self.local_path,
            'file_size': self.file_size
        }

class Product(BaseModel):
    product_id: str = Field(description="Generated unique product ID")
    brand: str = Field(description="Brand name from the website")
    model: str = Field(description="Product model/name")
    sku: List[str] = Field(default_factory=list, description="SKUs from different sites")
    category: Optional[str] = None
    product_name: Optional[str] = None
    source_url: List[str] = Field(default_factory=list, description="URLs from different sites")
    images: List[ProductImage] = Field(default_factory=list, description="Max 2 images per product")
    # Removed gender field (now included in product_name)
    # Removed raw_data field
    
    @field_validator('product_name', mode='before')
    @classmethod
    def generate_product_name(cls, v, info):
        """Always ensure product_name is set to avoid None values."""
        if v:
            return v
        
        # Generate from brand and model if available
        data = info.data if hasattr(info, 'data') else {}
        brand = data.get('brand', '')
        model = data.get('model', '')
        
        if brand and model:
            return f"{brand} {model}"
        elif model:
            return model
        elif brand:
            return f"{brand} Product"
        else:
            return "Unknown Product"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Product to dictionary format for JSON export."""
        return {
            'product_id': self.product_id,
            'brand': self.brand,
            'model': self.model,
            'sku': self.sku,
            'category': self.category,
            'product_name': self.product_name,
            'source_url': self.source_url,
            'images': [img.to_dict() for img in self.images]
            # Removed gender and raw_data
        }
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to database-ready dictionary."""
        return {
            'product_id': self.product_id,
            'brand': self.brand,
            'model': self.model,
            'sku': json.dumps(self.sku) if self.sku else None,
            'category': self.category,
            'product_name': self.product_name,
            'source_url': json.dumps(self.source_url) if self.source_url else None,
            'image_ids': [img.image_id for img in self.images]
        }

class ScrapingProgress(BaseModel):
    brand: str
    sites_completed: List[str] = Field(default_factory=list)
    products_found: int = 0
    products_processed: int = 0
    products_stored: int = 0
    failed_urls: List[str] = Field(default_factory=list)
    last_updated: str = Field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())