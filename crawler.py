# crawler.py

import asyncio
import requests
from urllib.parse import urljoin
from xml.etree import ElementTree
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher

# Global set to store successfully crawled URLs
crawled_urls_tracker = set()

def find_sitemap(base_url):
    candidates = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
        urljoin(base_url, "/sitemap1.xml"),
        urljoin(base_url, "/sitemap/sitemap.xml"),
    ]
    for url in candidates:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and ("<urlset" in r.text or "<sitemapindex" in r.text):
                print(f"Found sitemap: {url}")
                return url
        except Exception:
            continue
    print("No sitemap found at standard locations.")
    return None


def parse_sitemap(sitemap_url):
    urls = []
    try:
        r = requests.get(sitemap_url, timeout=10)
        root = ElementTree.fromstring(r.content)
        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        # Handle both <url> and <sitemap> tags for nested sitemaps
        for loc in root.findall(".//ns:loc", namespace):
            urls.append(loc.text)
        # If it's a sitemap index, parse nested sitemaps recursively
        for sitemap_loc in root.findall(".//ns:sitemap/ns:loc", namespace):
            urls.extend(parse_sitemap(sitemap_loc.text))
    except Exception as e:
        print(f"Error parsing sitemap: {e}")
    return urls


async def discover_with_crawl4ai(start_url, max_pages=50):
    print("Discovering URLs with Crawl4AI...")
    browser_config = BrowserConfig(headless=True)
    async with AsyncWebCrawler(config=browser_config) as crawler:
        discovered = await crawler.arun_discover(start_url, max_pages=max_pages)
        urls = list(discovered.urls)
        print(f"Discovered {len(urls)} URLs.")
        return urls


async def crawl_and_process(urls, callback, max_concurrent=10):
    print("\n=== Crawling and Embedding Content in Parallel ( No Streaming Mode) ===")
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
    )
    crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,
        check_interval=1.0,
        max_session_permit=max_concurrent,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun_many(urls=urls, config=crawl_config, dispatcher=dispatcher)
        for result in results:
            if result.success and result.markdown:
                print(f"[SUCCESS] {result.url}")
                await callback(result.url, result.markdown)
                crawled_urls_tracker.add(result.url) # Add to tracker
            else:
                print(f"[FAIL] {result.url}: {result.error_message}")

def get_crawled_urls():
    """Returns the set of URLs that have been successfully crawled."""
    return crawled_urls_tracker