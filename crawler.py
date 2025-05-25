import asyncio
import sys
import aiohttp
import requests
from typing import List, Callable, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# Track crawled URLs to avoid duplicates
crawled_urls_tracker = set()

def get_crawled_urls():
    """Returns the set of URLs that have been successfully crawled."""
    return crawled_urls_tracker

def find_sitemap(base_url: str) -> Optional[str]:
    """Check for sitemap.xml at common locations."""
    common_paths = [
        '/sitemap.xml',
        '/sitemap_index.xml',
        '/sitemap/sitemap.xml'
    ]
    
    for path in common_paths:
        sitemap_url = urljoin(base_url, path)
        try:
            response = requests.get(sitemap_url, timeout=10)
            if response.status_code == 200:
                return sitemap_url
        except:
            continue
    return None

def parse_sitemap(sitemap_url: str) -> List[str]:
    """Parse sitemap.xml and return list of URLs."""
    try:
        response = requests.get(sitemap_url)
        if response.status_code != 200:
            return []
            
        root = ET.fromstring(response.content)
        urls = []
        
        # Handle sitemap index
        if 'sitemapindex' in root.tag.lower():
            for sitemap in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
                loc = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                if loc is not None and loc.text:
                    urls.extend(parse_sitemap(loc.text))
        # Handle URL set
        elif 'urlset' in root.tag.lower():
            for url_entry in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
                loc = url_entry.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                if loc is not None and loc.text:
                    urls.append(loc.text)
                    
        return list(set(urls))  # Remove duplicates
    except Exception as e:
        print(f"Error parsing sitemap {sitemap_url}: {str(e)}")
        return []

async def discover_urls(start_url: str, max_pages: int = 50) -> List[str]:
    """Main URL discovery function that uses the appropriate method."""
    # First try to use sitemap
    sitemap_url = find_sitemap(start_url)
    if sitemap_url:
        print(f"Found sitemap at {sitemap_url}")
        return parse_sitemap(sitemap_url)
    
    # Fall back to requests-based discovery
    print("Using requests-based discovery")
    return await discover_with_requests(start_url, max_pages)

async def discover_with_requests(start_url: str, max_pages: int = 50) -> List[str]:
    """URL discovery using requests and BeautifulSoup."""
    print("Using requests-based URL discovery...")
    
    try:
        # Start with the base URL
        visited = set()
        to_visit = {start_url}
        urls = set()
        
        while to_visit and len(urls) < max_pages:
            url = to_visit.pop()
            if url in visited:
                continue
                
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    urls.add(url)
                    
                    # Find all links on the page
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        full_url = urljoin(url, href)
                        
                        # Only follow links from the same domain
                        if urlparse(full_url).netloc == urlparse(start_url).netloc:
                            if full_url not in visited and full_url not in to_visit:
                                to_visit.add(full_url)
                                
            except Exception as e:
                print(f"Error processing {url}: {str(e)}")
                
            visited.add(url)
            
        return list(urls)[:max_pages]
        
    except Exception as e:
        print(f"Error in discover_with_requests: {str(e)}")
        return []

async def crawl_and_process(urls: List[str], callback: Callable, max_concurrent: int = 5):
    """Crawl and process URLs with error handling and rate limiting."""
    semaphore = asyncio.Semaphore(max_concurrent)
    processed_urls = set()
    
    # Configure connection pool settings
    connector = aiohttp.TCPConnector(
        ssl=False,
        limit_per_host=5,
        force_close=False,
        enable_cleanup_closed=True,
        ttl_dns_cache=300
    )
    
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=10)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    
    async def fetch_with_retry(session: aiohttp.ClientSession, url: str, max_retries: int = 3):
        nonlocal processed_urls
        
        if url in processed_urls:
            return None
            
        processed_urls.add(url)
        
        for attempt in range(max_retries):
            try:
                async with semaphore:
                    async with session.get(url, allow_redirects=True, timeout=timeout) as response:
                        if response.status == 200:
                            return await response.text()
                        elif 400 <= response.status < 500:
                            print(f"Client error {response.status} for {url}")
                            return None
                        else:
                            print(f"Server error {response.status} for {url}, attempt {attempt + 1}/{max_retries}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"Error fetching {url}: {str(e)}, attempt {attempt + 1}/{max_retries}")
                if attempt == max_retries - 1:  # Last attempt
                    return None
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
        return None
    
    async def process_url(session: aiohttp.ClientSession, url: str):
        if not url.startswith(('http://', 'https://')):
            print(f"Skipping invalid URL: {url}")
            return
            
        print(f"Processing: {url}")
        
        try:
            content = await fetch_with_retry(session, url)
            if not content:
                return
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract the main content
            main_content = (soup.find('main') or 
                          soup.find('article') or 
                          soup.find('div', class_=lambda x: x and 'content' in x.lower()) or 
                          soup.body)
            
            if main_content:
                # Clean up the content
                for element in main_content(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                    element.decompose()
                
                # Get clean text with proper spacing
                text = '\n'.join(line.strip() for line in main_content.get_text().splitlines() if line.strip())
                
                if text:
                    # Call the callback with URL and content as separate arguments
                    title = (soup.title.string if soup.title else 'No Title').strip()
                    await callback(url, text)  # Pass URL and content as separate arguments
                    print(f"Processed: {url} - {title}")
                else:
                    print(f"No content found for {url}")
            else:
                print(f"No main content found for {url}")
                
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Filter out already crawled URLs
    new_urls = [url for url in urls if url not in crawled_urls_tracker]
    
    if not new_urls:
        print("No new URLs to process")
        return
    
    print(f"Processing {len(new_urls)} URLs with {max_concurrent} concurrent requests...")
    
    # Process all URLs with a single session
    async with aiohttp.ClientSession(
        headers=headers,
        connector=connector,
        timeout=timeout,
        raise_for_status=False
    ) as session:
        # Process URLs in chunks with retries and backoff
        total_urls = len(new_urls)
        chunk_size = max(1, max_concurrent // 2)  # Use smaller chunks to be more gentle
        
        for i in range(0, total_urls, chunk_size):
            chunk = new_urls[i:i + chunk_size]
            tasks = [process_url(session, url) for url in chunk]
            
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                # Add a small delay between chunks
                if i + chunk_size < total_urls:
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"Error in chunk {i//chunk_size + 1}: {str(e)}")
                # Continue with next chunk even if one fails
                continue

# For backward compatibility
discover_with_crawl4ai = discover_urls