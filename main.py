import asyncio
from crawler import crawl_and_process, find_sitemap, parse_sitemap, discover_with_crawl4ai, get_crawled_urls
from embedder import Embedder
from storage import store_in_chromadb, save_to_file
from utils import log_chunk_info
from langchain.chains import RetrievalQA

# File to store sitemap URLs and their crawl status
SITEMAP_STATUS_FILE = "sitemap_crawl_status.txt"

async def handle_processed_result(url, content):
    # Use heuristic chunking and header assignment
    docs = embedder.split_and_embed(url, content)
    for doc in docs:
        log_chunk_info(doc.metadata["source"], doc.metadata["chunk_number"], len(doc.page_content))
        save_to_file(doc.page_content, doc.metadata["source"], doc.metadata["chunk_number"])
    store_in_chromadb(docs)

def print_sitemap_crawl_status(sitemap_urls):
    """
    Prints the crawl status of URLs found in the sitemap.
    Marks URLs as "Crawled" if they are in the crawled_urls_tracker.
    """
    crawled_urls = get_crawled_urls()
    print("\n=== Sitemap Crawl Status ===")
    with open(SITEMAP_STATUS_FILE, "w") as f:
        for url in sitemap_urls:
            status = "[Crawled]" if url in crawled_urls else "[Pending]"
            print(f"{status} {url}")
            f.write(f"{status} {url}\n")
    print(f"\nSitemap crawl status saved to {SITEMAP_STATUS_FILE}")


async def main():
    start_url = "https://ai.pydantic.dev//"
    if not start_url.startswith('http'):
        start_url = 'https://' + start_url

    # Step 1: Find URLs
    sitemap_url = find_sitemap(start_url)
    if sitemap_url:
        urls_from_sitemap = parse_sitemap(sitemap_url)
        urls = urls_from_sitemap
        print(f"Found {len(urls_from_sitemap)} URLs in sitemap.")
    else:
        urls_from_sitemap = [] # Initialize empty if no sitemap
        urls = await discover_with_crawl4ai(start_url)

    # Step 2: Initialize Embedder and VectorStore
    global embedder, vectorstore
    embedder = Embedder()
    vectorstore = embedder.get_vectorstore()

    # Step 3: Start crawling and processing
    async def async_callback(url, content):
        await handle_processed_result(url, content)
    await crawl_and_process(urls, async_callback)

    print("✅ Crawling, embedding, and storing complete.")

    # Step 4: Print and save sitemap crawl status
    if sitemap_url: # Only show sitemap status if a sitemap was found
        print_sitemap_crawl_status(urls_from_sitemap)


    # Step 5: RAG Retrieval with Hybrid Search
    query = "What is pydantic AI? Why do we use it?"
    # Use hybrid search for best performance
    results = embedder.hybrid_search(vectorstore, query, k=5)
    print("\n📚 Top Retrieved Chunks:")
    for i, doc in enumerate(results, 1):
        print(f"\n--- Chunk {i} ---")
        print(f"Title/Header: {doc.metadata.get('title', 'Untitled')}")
        print(f"Source: {doc.metadata.get('source', 'Unknown')}")
        print(f"Chunk Number: {doc.metadata.get('chunk_number', 'N/A')}")
        print(f"Content:\n{doc.page_content[:500]}\n...")

    # Optionally, pass the concatenated context to the LLM for answer synthesis
    context = "\n\n".join([doc.page_content for doc in results])
    prompt = f"Context:\n{context}\n\nQuestion: {query}\nAnswer as a helpful documentation assistant."
    answer = embedder.llm.invoke(prompt)
    print(f"\n🧠 Synthesized Answer:\n{answer}\n")

if __name__ == "__main__":
    asyncio.run(main())