import os
from embedder import Embedder
from storage import load_chromadb_vectorstore

def test_chromadb_retrieval_on_crawled_content():
    # This should match the persist_directory used in main.py
    persist_dir = './chroma/'
    assert os.path.exists(persist_dir), f"ChromaDB directory '{persist_dir}' does not exist. Run the main crawl first."

    # Load the vectorstore
    vectorstore = load_chromadb_vectorstore(persist_directory=persist_dir)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    # Query for a relevant term
    query = "examplecode"
    results = retriever.invoke(query)

    # Check that at least one chunk is returned and contains expected content
    assert results, "No results returned from ChromaDB."
    found = any("pydantic" in doc.page_content.lower() for doc in results)
    assert found, "Relevant chunk about 'pydantic' not found in retrieved results."
    print(f"Test passed: Retrieved {len(results)} relevant chunks from ChromaDB.\n")
    for i, doc in enumerate(results, 1):
        print(f"--- Chunk {i} ---")
        print(f"Source: {doc.metadata.get('source')}")
        print(f"Chunk ID: {doc.metadata.get('chunk_id')}")
        print(f"Content:\n{doc.page_content[:500]}\n{'-'*40}")

if __name__ == "__main__":
    test_chromadb_retrieval_on_crawled_content() 