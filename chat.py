import asyncio
import requests
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher, Url, PageInfo

# This global tracker is not used in this file, but was in the original app.py context.
# It's better managed within app.py's session state.
# crawled_urls_tracker = set()

def find_sitemap(base_url: str) -> str | None:
    """
    Attempts to find a sitemap URL for the given base URL.
    Args:
        base_url: The base URL of the website.
    Returns:
        The sitemap URL if found, otherwise None.
    """
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'https://' + base_url

    # Common sitemap locations
    candidates = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"), # For sitemap indexes
        urljoin(base_url, "/sitemap.xml.gz"),   # Compressed sitemap
        urljoin(base_url, "/sitemap_index.xml.gz"),
        urljoin(base_url, "/robots.txt"), # Check robots.txt for sitemap directive
    ]
    print(f"Searching for sitemap for {base_url} at: {candidates}")

    for url in candidates:
        try:
            r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0 (compatible; SitemapChecker/1.0)'})
            r.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            if "robots.txt" in url:
                for line in r.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_url_from_robots = line.split(":", 1)[1].strip()
                        print(f"Found sitemap directive in robots.txt: {sitemap_url_from_robots}")
                        # Optionally, verify this URL as well
                        try:
                            rs = requests.get(sitemap_url_from_robots, timeout=10)
                            if rs.status_code == 200 and ("<urlset" in rs.text or "<sitemapindex" in rs.text):
                                return sitemap_url_from_robots
                        except Exception:
                            continue # Try next candidate if this one fails
            elif ("<urlset" in r.text or "<sitemapindex" in r.text): # Basic check for XML sitemap content
                print(f"Found sitemap: {url}")
                return url
        except requests.exceptions.RequestException as e:
            print(f"Error checking sitemap candidate {url}: {e}")
            continue
    print(f"No sitemap found at standard locations for {base_url}.")
    return None


def parse_sitemap(sitemap_url: str) -> list[str]:
    """
    Parses a sitemap URL (XML) and extracts all URLs. Handles nested sitemaps.
    Args:
        sitemap_url: The URL of the sitemap (can be a sitemap index).
    Returns:
        A list of URLs extracted from the sitemap.
    """
    urls = []
    try:
        print(f"Parsing sitemap: {sitemap_url}")
        r = requests.get(sitemap_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (compatible; SitemapParser/1.0)'})
        r.raise_for_status()
        
        content = r.content
        # Basic check for gzipped content (though requests usually handles this)
        if sitemap_url.endswith(".gz"):
            import gzip
            try:
                content = gzip.decompress(content)
            except gzip.BadGzipFile:
                print(f"Warning: File {sitemap_url} ends with .gz but might not be gzipped. Trying to parse as is.")
                # content remains r.content

        # The namespace can vary, but this is the most common one.
        # Using local-name() in XPath can bypass namespace issues if they arise.
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as e_parse:
            print(f"XML ParseError for {sitemap_url}: {e_parse}. Content might not be valid XML.")
            return urls


        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        
        # Find <loc> tags within <url> tags (standard sitemap)
        for loc_element in root.findall(".//ns:url/ns:loc", namespace):
            if loc_element.text:
                urls.append(loc_element.text.strip())
        
        # Find <loc> tags within <sitemap> tags (sitemap index file)
        for sitemap_loc_element in root.findall(".//ns:sitemap/ns:loc", namespace):
            if sitemap_loc_element.text:
                nested_sitemap_url = sitemap_loc_element.text.strip()
                print(f"Found nested sitemap: {nested_sitemap_url}. Parsing recursively...")
                urls.extend(parse_sitemap(nested_sitemap_url)) # Recursive call

    except requests.exceptions.RequestException as e_req:
        print(f"Request error parsing sitemap {sitemap_url}: {e_req}")
    except Exception as e:
        print(f"Unexpected error parsing sitemap {sitemap_url}: {e}")
    
    print(f"Found {len(urls)} URLs from {sitemap_url} (including nested if any).")
    return list(set(urls)) # Return unique URLs


async def discover_with_crawl4ai(start_url: str, max_pages: int = 50) -> list[str]:
    """
    Discovers URLs starting from a given URL using Crawl4AI.
    Args:
        start_url: The URL to start discovery from.
        max_pages: The maximum number of pages to discover.
    Returns:
        A list of discovered URLs.
    """
    print(f"Discovering URLs with Crawl4AI from {start_url}, max_pages={max_pages}...")
    browser_config = BrowserConfig(
        headless=True,
        verbose=False # Set to True for more crawl4ai logs
    )
    # Using default dispatcher and run_config for discovery
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            discovered_result = await crawler.arun_discover(start_url, max_pages=max_pages)
            if discovered_result and discovered_result.urls:
                urls = list(discovered_result.urls)
                print(f"Crawl4AI discovered {len(urls)} URLs.")
                return urls
            else:
                print("Crawl4AI discovery yielded no URLs or an empty result.")
                return []
        except Exception as e:
            print(f"Error during Crawl4AI discovery for {start_url}: {e}")
            return []


async def crawl_and_process(urls_to_crawl: list[str], callback, max_concurrent: int = 5):
    """
    Crawls a list of URLs concurrently, extracts content, and calls a callback for each.
    Args:
        urls_to_crawl: A list of URL strings to crawl.
        callback: An async function to call with (url: str, content: str | None).
                  content is None if an error occurs or no text content is found.
        max_concurrent: Max concurrent browser tasks/fetches.
    """
    if not urls_to_crawl:
        print("No URLs provided to crawl_and_process.")
        return

    print(f"\n=== Starting crawl_and_process for {len(urls_to_crawl)} URLs (concurrent arun) ===")
    browser_config = BrowserConfig(
        headless=True,
        verbose=False, # Set to True for detailed crawl4ai logs
        # extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"] # Often default/handled
    )
    # Dispatcher controls browser instance pooling and concurrency for crawl4ai
    dispatcher = MemoryAdaptiveDispatcher(max_concurrent_tasks=max_concurrent)
    crawl_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, # Or CacheMode.USE_CACHE for development
        stream=False, # We want full page content
        page_timeout=30000, # 30 seconds page timeout
        request_timeout=20000 # 20 seconds request timeout
    )
    
    # Semaphore to more explicitly limit the number of concurrent `crawler.arun` calls
    # if dispatcher's max_concurrent_tasks isn't granular enough or for other reasons.
    # Typically, dispatcher's setting should be primary for browser task concurrency.
    # Using a semaphore here adds another layer of control over our task creation.
    semaphore = asyncio.Semaphore(max_concurrent)

    async with AsyncWebCrawler(config=browser_config, run_config=crawl_config, dispatcher=dispatcher) as crawler:
        tasks = []

        async def fetch_url_and_callback(url_str: str):
            async with semaphore: # Limit active fetches managed by this loop
                print(f"Attempting to fetch: {url_str}")
                page_info: PageInfo | None = None
                try:
                    # crawler.arun processes a single URL
                    page_info = await crawler.arun(url=Url(url_str))
                    
                    if page_info and page_info.content_text:
                        # print(f"Content found for {url_str}. Length: {len(page_info.content_text)}. Calling callback.")
                        await callback(url_str, page_info.content_text)
                    elif page_info:
                        print(f"No text content for {url_str}. Status: {page_info.status_code}. Error: {page_info.error_message}")
                        await callback(url_str, None) # No content
                    else:
                        # This case means arun returned None, indicating a more severe failure
                        print(f"Failed to fetch or no PageInfo result for {url_str}.")
                        await callback(url_str, None) # Error/No result
                except Exception as e_fetch:
                    print(f"Exception during fetch for {url_str}: {e_fetch}")
                    await callback(url_str, None) # Error

        for u in urls_to_crawl:
            if u: # Ensure URL is not empty
                tasks.append(fetch_url_and_callback(u))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=False) # Set return_exceptions=True to debug individual task failures
        else:
            print("No valid tasks created for crawling.")

    print(f"=== Finished crawl_and_process for {len(urls_to_crawl)} URLs ===")

