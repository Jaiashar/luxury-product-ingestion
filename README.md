# Luxury Product Ingestion

**A Python pipeline that turns listings from multiple luxury resale sites into a structured product catalog.**

I built this as part of Auricore's pricing and product-data infrastructure. Comparing luxury goods across marketplaces requires collecting inconsistent listings, extracting useful attributes, handling product images, and saving a consistent record for downstream matching and valuation.

## What happens to a listing

1. A site-specific adapter retrieves and extracts the listing.
2. Categorization and parsing turn the source fields into a structured product record.
3. Image utilities handle the associated product imagery.
4. Storage code persists catalog records in DynamoDB and image objects in S3.
5. Progress and failure tracking help inspect an incomplete or interrupted run.

Collecting a listing and proving that it is the same product as another listing are separate tasks. This repository handles ingestion; the linked canonicalization project handles downstream matching and enrichment.

## Pipeline

```mermaid
flowchart LR
    A[Marketplace adapters] --> B[Listing extraction]
    B --> C[AI categorization]
    C --> D[Validated product records]
    D --> E[DynamoDB]
    B --> F[Image processing]
    F --> G[S3]
```

The historical source includes adapters for The RealReal, Vestiaire Collective, Fashionphile, Farfetch, Rebag and StockX. Live site compatibility has not been revalidated. The implementation includes asynchronous scraping, rate limits, retries, progress tracking, Claude-based categorization, image handling and AWS storage.

| Area | Source |
| --- | --- |
| Multi-site CLI | [main.py](main.py) |
| Marketplace-specific extraction | [scraper/sites](scraper/sites) |
| Categorization | [ai_categorizer.py](scraper/utils/ai_categorizer.py) |
| Product and progress models | [data_models.py](scraper/utils/data_models.py) |
| Image handling | [optimized_image_handler.py](scraper/utils/optimized_image_handler.py) |
| Catalog and image storage | [optimized_aws_storage.py](optimized_aws_storage.py) |

## Try the data model offline

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install 'pydantic>=2,<3'
python examples/offline_product.py
```

The example uses a synthetic product and exercises the actual validation and serialization models. It makes no network requests and requires no credentials.

## Configure the full pipeline

```sh
pip install -r requirements.txt
cp .env.example .env
# Supply your own API keys, supported model ID and isolated AWS resources.
python main.py
```

The full pipeline calls paid APIs and can create/write DynamoDB tables and S3 objects. Configure a dedicated development AWS profile and explicitly set `DYNAMODB_TABLE_NAME`, `FAILURES_TABLE_NAME` and `S3_BUCKET_NAME`. The public snapshot does not carry original credentials or fall back to the original storage resources.

This is historical source. Provider APIs, available model IDs and marketplace markup may have changed. The dependency file is not a reproducible lockfile; end-to-end ingestion has not been revalidated.

## Related work

[Product Canonicalization](https://github.com/Jaiashar/product-canonicalization) resolves and enriches product records downstream. [Auricore Web](https://github.com/Jaiashar/auricore-web) presents item identification and market-price research to users.

## Authorship and validation

See [PROVENANCE.md](PROVENANCE.md) for the original revision and publication changes. Source syntax and the synthetic offline example are checked; live scraping, AI calls and AWS writes are not part of this validation.
