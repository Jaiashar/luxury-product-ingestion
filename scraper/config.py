# scraper/config.py
"""Configuration management for the brand scraper."""

import os
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class ScrapFlyConfig:
    api_key: str
    concurrency_limit: int = 5  # REDUCED from 20 to 5
    rate_limit: float = 3.0  # INCREASED from 1.0 to 3.0 seconds
    
@dataclass
class ClaudeConfig:
    api_key: str
    model: str = "claude-3-5-sonnet-20241022"  # Updated to current model
    
@dataclass
class ScraperConfig:
    scrapfly: ScrapFlyConfig
    claude: ClaudeConfig
    image_dir: str = "./Auricore/images"
    progress_file: str = "./Auricore/progress.json"
    max_retries: int = 3
    retry_delay: float = 2.0
    min_images_per_product: int = 3
    supported_sites: List[str] = None
    
    def __post_init__(self):
        if self.supported_sites is None:
            self.supported_sites = ["therealreal", "vestiaire", "fashionphile"]
        
        # Create directories if they don't exist
        os.makedirs(self.image_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)

def load_config() -> ScraperConfig:
    """Load configuration from environment variables."""
    # Try to load from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, skip
    
    # Get API key from environment - NO HARDCODED DEFAULT
    scrapfly_api_key = os.getenv("SCRAPFLY_API_KEY")
    if not scrapfly_api_key:
        raise ValueError("SCRAPFLY_API_KEY environment variable is required!")
    
    scrapfly_config = ScrapFlyConfig(
        api_key=scrapfly_api_key,  # Use environment variable only
        concurrency_limit=int(os.getenv("SCRAPFLY_CONCURRENCY", "5")),  # Default to 5
        rate_limit=float(os.getenv("SCRAPFLY_RATE_LIMIT", "3.0"))  # Default to 3.0
    )
    
    claude_config = ClaudeConfig(
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")  # Updated default
    )
    
    return ScraperConfig(
        scrapfly=scrapfly_config,
        claude=claude_config
    )

