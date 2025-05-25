import asyncio
from embedder import Embedder
from storage import load_chromadb_vectorstore
from utils import log_chunk_info
from langchain_core.output_parsers import MarkdownListOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate

async def chat():
    # Initialize Embedder and VectorStore
    embedder = Embedder()
    vectorstore = load_chromadb_vectorstore()

    print("💬 Chat session started. Type 'exit' to end.\n")

    # Define the output parser
    # We'll use StrOutputParser for general markdown formatting
    # If you want to strictly parse into a list, MarkdownListOutputParser can be used
    output_parser = StrOutputParser()

    while True:
        query = input("🧾 Your question: ").strip()
        if query.lower() in {"exit", "quit"}:
            print("👋 Exiting chat.")
            break

        # Use hybrid search for best retrieval
        results = embedder.hybrid_search(vectorstore, query, k=10)
        print("\n📚 Top Retrieved Chunks:")
        for i, doc in enumerate(results, 1):
            print(f"\n--- Chunk {i} ---")
            print(f"Title/Header: {doc.metadata.get('title', 'Untitled')}")
            print(f"Source: {doc.metadata.get('source', 'Unknown')}")
            print(f"Chunk Number: {doc.metadata.get('chunk_number', 'N/A')}")
            print(f"Content:\n{doc.page_content[:500]}\n...")

        # Synthesize answer using LLM
        context = "\n\n".join([doc.page_content for doc in results])
        
        # Craft a prompt that encourages the LLM to use Markdown for formatting
        prompt_template = PromptTemplate(
            template="""Context:
{context}

Question: {query}

Please answer as a helpful documentation assistant. Format your answer neatly using Markdown, including headers, code blocks (if applicable), and lists to improve readability.
""",
            input_variables=["context", "query"],
        )
        
        # Combine prompt, LLM, and parser into a chain
        chain = prompt_template | embedder.llm | output_parser
        
        # Invoke the chain to get the formatted answer
        answer = await chain.ainvoke({"context": context, "query": query})
        
        print(f"\n🧠 Answer:\n{answer}\n")

if __name__ == "__main__":
    asyncio.run(chat())