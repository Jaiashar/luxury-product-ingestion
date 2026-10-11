"""Validate a synthetic catalog record without credentials or network requests."""
from pathlib import Path
import sys
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper.utils.data_models import Product, ProductImage

product = Product(
    product_id="demo-bag-001",
    brand="Example Atelier",
    model="Everyday Bag",
    product_name="Example Atelier Everyday Bag",
    category="handbags",
    sku=["DEMO-001"],
    source_url=["https://example.com/products/demo-bag"],
    images=[ProductImage(image_id="demo-image-001", url="https://example.com/demo.jpg")],
)
record = product.to_dict()
assert record["brand"] == "Example Atelier"
assert record["images"][0]["image_id"] == "demo-image-001"
assert json.loads(product.to_db_dict()["sku"]) == ["DEMO-001"]
print(json.dumps(record, indent=2))
print("Offline validation and serialization: PASS")
