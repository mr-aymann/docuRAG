from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict
from datetime import datetime, timezone
from urllib.parse import urlparse
import os
from dotenv import load_dotenv
import re

load_dotenv()

class Embedder:
    def __init__(self, embeddings_model="models/embedding-001", llm_model="gemini-1.5-flash"):
        # Get API key from environment
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set. Please add it to your .env file.")
            
        # Initialize embeddings and LLM with the API key
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=embeddings_model,
            google_api_key=self.api_key
        )
        self.llm = ChatGoogleGenerativeAI(
            model=llm_model,
            google_api_key=self.api_key,
            temperature=0.8
        )
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)

    def get_vectorstore(self, persist_directory="./chroma/"):
        return Chroma(
            collection_name="website_content",
            embedding_function=self.embeddings,
            persist_directory=persist_directory
        )

    def extract_headers(self, text: str) -> List[Dict]:
        """Extract headers and their positions from markdown text."""
        headers = []
        for match in re.finditer(r'^(#{1,6})\s+(.*)', text, re.MULTILINE):
            headers.append({
                'level': len(match.group(1)),
                'title': match.group(2).strip(),
                'start': match.start()
            })
        return headers

    def assign_nearest_header(self, chunk_start: int, headers: List[Dict]) -> str:
        """Find the nearest preceding header for a chunk."""
        nearest = None
        for header in headers:
            if header['start'] <= chunk_start:
                if nearest is None or header['start'] > nearest['start']:
                    nearest = header
        return nearest['title'] if nearest else "Untitled"

    def chunk_and_annotate(self, text: str, url: str) -> List[Document]:
        """Split text into chunks and assign nearest header as title."""
        headers = self.extract_headers(text)
        splits = self.splitter.split_text(text)
        docs = []
        last_idx = 0
        for i, chunk in enumerate(splits):
            # Find the start index of this chunk in the original text
            idx = text.find(chunk, last_idx)
            last_idx = idx + len(chunk)
            title = self.assign_nearest_header(idx, headers)
            metadata = {
                "source": url,
                "chunk_number": i,
                "title": title,
                "chunk_size": len(chunk),
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "url_path": urlparse(url).path
            }
            docs.append(Document(page_content=chunk, metadata=metadata))
        return docs

    def split_and_embed(self, url: str, content: str) -> List[Document]:
        """Split document into chunks, assign headers, and return Document objects."""
        return self.chunk_and_annotate(content, url)

    def hybrid_search(self, vectorstore, query: str, k: int = 5) -> List[Document]:
        """Perform hybrid search: keyword + vector search, return unique results."""
        # Keyword search (simple filter)
        keyword_results = vectorstore.similarity_search(query, k=k*2)  # get more for dedup
        # Vector search
        vector_results = vectorstore.similarity_search_by_vector(
            self.embeddings.embed_query(query), k=k*2)
        # Combine and deduplicate
        seen = set()
        results = []
        for doc in keyword_results + vector_results:
            key = (doc.metadata.get("source"), doc.metadata.get("chunk_number"))
            if key not in seen:
                results.append(doc)
                seen.add(key)
            if len(results) >= k:
                break
        return results
