from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

def store_in_chromadb(docs, persist_directory="./chroma/"):
    """
    Store documents in Chroma vector store with persistence.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    vectorstore = Chroma(
        collection_name="website_content",
        embedding_function=embeddings,
        persist_directory=persist_directory
    )
    vectorstore.add_documents(docs)

def load_chromadb_vectorstore(persist_directory="./chroma/"):
    """
    Load the persisted Chroma vector store from the specified directory.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    vectorstore = Chroma(
        collection_name="website_content",
        embedding_function=embeddings,
        persist_directory=persist_directory
    )
    return vectorstore

def save_to_file(content, url, chunk_id, output_file="./crawled_data.txt"):
    """
    Append a chunk of content to a single file, including the URL and chunk ID for traceability.
    """
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"URL: {url}\nChunk ID: {chunk_id}\n\n{content}\n{'='*80}\n")
