# storage.py
import os
import re
from urllib.parse import urlparse
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from typing import List

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Configure Google API key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set. Please add it to your .env file.")

# It's good practice to define constants once
EMBEDDING_MODEL_NAME = "models/embedding-001"
COLLECTION_NAME = "website_content"

def store_in_chromadb(docs: List[Document], vectorstore: Chroma):
    """
    Store documents in the provided Chroma vector store.
    This function assumes the vectorstore is already initialized with the correct
    embedding function and persist directory.
    """
    if not isinstance(vectorstore, Chroma):
        raise TypeError("Expected 'vectorstore' to be an instance of Chroma.")

    vectorstore.add_documents(docs)
    print(f"Added {len(docs)} documents to ChromaDB.")

def load_chromadb_vectorstore(persist_directory: str = "./chroma/") -> Chroma:
    """
    Load or create the Chroma vector store from the specified directory.
    This function initializes the embeddings function internally.
    """
    # Create the directory if it doesn't exist
    os.makedirs(persist_directory, exist_ok=True)
    
    # Initialize embeddings with the API key
    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        google_api_key=GOOGLE_API_KEY
    )
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=persist_directory
    )
    return vectorstore

def delete_from_chromadb(vectorstore: Chroma, where_clause: dict):
    """
    Deletes documents from the Chroma vector store based on a metadata filter.
    Example where_clause: {"source": "https://www.example.com/"}
    """
    if not isinstance(vectorstore, Chroma):
        raise TypeError("Expected 'vectorstore' to be an instance of Chroma.")
    
    try:
        # ChromaDB's delete method can take a 'where' clause for filtering by metadata
        vectorstore.delete(where=where_clause)
        print(f"Deleted documents from ChromaDB with filter: {where_clause}")
    except Exception as e:
        print(f"Error deleting from ChromaDB: {e}")
        raise # Re-raise to be handled by the caller (app.py)

def save_to_file(content: str, url: str, chunk_id: int, output_file: str = "./crawled_data.txt"):
    """
    Append a chunk of content to a single file, including the URL and chunk ID for traceability.
    """
    # Ensure the directory exists
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"URL: {url}\nChunk ID: {chunk_id}\n\n{content}\n{'='*80}\n")