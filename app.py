import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# Langchain specific imports for chat handling
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Import your existing modules (assuming these are correctly implemented elsewhere)
from embedder import Embedder
from storage import store_in_chromadb, load_chromadb_vectorstore, delete_from_chromadb
from crawler import crawl_and_process, find_sitemap, parse_sitemap, discover_with_crawl4ai

app = FastAPI(
    title="Documentation RAG System",
    version="1.0.0",
    description="A RAG (Retrieval-Augmented Generation) system for documentation"
)

# Create static directory if it doesn't exist
Path("static").mkdir(exist_ok=True, parents=True)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates (if you plan to use Jinja2 for server-side rendering, otherwise can be removed)
templates = Jinja2Templates(directory="templates")

# Global variables
embedder: Optional[Embedder] = None
vectorstore: Any = None # Type hint as Any as the exact type from chromadb might be complex
scraped_sites: Dict[str, Dict[str, Any]] = {}
crawl_status: Dict[str, Dict[str, Any]] = {}

SITES_METADATA_FILE = "sites_metadata.json"

def load_sites_metadata():
    global scraped_sites, crawl_status
    if os.path.exists(SITES_METADATA_FILE):
        try:
            with open(SITES_METADATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                scraped_sites = data.get("scraped_sites", {})
                crawl_status = data.get("crawl_status", {})
        except Exception as e:
            print(f"Failed to load sites metadata: {e}")
            scraped_sites = {}
            crawl_status = {}
    else:
        scraped_sites = {}
        crawl_status = {}

def save_sites_metadata():
    try:
        with open(SITES_METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "scraped_sites": scraped_sites,
                "crawl_status": crawl_status
            }, f, default=str, indent=2)
    except Exception as e:
        print(f"Failed to save sites metadata: {e}")

# Models
class ChatMessage(BaseModel):
    message: str

class URLInput(BaseModel):
    url: str
    name: Optional[str] = None

class SiteResponse(BaseModel):
    id: str
    url: str
    name: str
    status: str
    progress: Optional[float] = 0.0
    created_at: datetime
    updated_at: datetime

class ChatResponse(BaseModel):
    response: str
    sources: Optional[List[Dict[str, Any]]] = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"WebSocket disconnected: {websocket.client}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcasts a dictionary message as JSON to all active connections."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error broadcasting message to {connection.client}: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

# Event handlers
@app.on_event("startup")
async def startup_event():
    global embedder, vectorstore
    load_sites_metadata()
    try:
        embedder = Embedder()
        vectorstore = load_chromadb_vectorstore()
        print("Embedder and vectorstore initialized successfully")
    except Exception as e:
        print(f"Error initializing services: {e}")
        # Re-raise to prevent the app from starting if essential services fail
        raise

# Routes
@app.get("/", response_class=FileResponse)
async def get_index():
    """Serves the main HTML page for the application."""
    return FileResponse("static/index.html")

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles WebSocket connections for real-time communication."""
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "chat_message":
                    await handle_chat_message(websocket, message.get("content", ""))
                else:
                    print(f"Unknown message type received: {message.get('type')}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {message.get('type')}"
                    })
                    
            except json.JSONDecodeError:
                print("Received invalid JSON format over WebSocket.")
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })
            except WebSocketDisconnect:
                print("Client disconnected during message reception.")
                break # Exit the loop when client disconnects
            except Exception as e:
                print(f"Error processing WebSocket message: {str(e)}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Server error processing message: {str(e)}"
                })
                
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket.")
    except Exception as e:
        print(f"Unexpected WebSocket error: {str(e)}")
    finally:
        manager.disconnect(websocket)
        try:
            await websocket.close()
        except RuntimeError as e:
            # Handle case where websocket might already be closed
            print(f"Error closing websocket (might already be closed): {e}")

async def handle_chat_message(websocket: WebSocket, message: str):
    """Handles incoming chat messages via WebSocket, performs RAG, and streams response."""
    global vectorstore, embedder
    
    message_id = f"msg-{uuid.uuid4().hex}"
    
    try:
        if not vectorstore:
            await websocket.send_json({
                "type": "chat_response",
                "response": "Error: Vector store not initialized. Please load some data first.",
                "sources": [],
                "message_id": message_id,
                "is_complete": True
            })
            return
            
        if not message or not message.strip():
            await websocket.send_json({
                "type": "chat_response",
                "response": "Please enter a valid message.",
                "sources": [],
                "message_id": message_id,
                "is_complete": True
            })
            return
        
        # Send typing indicator
        await websocket.send_json({
            "type": "typing",
            "is_typing": True,
            "message_id": message_id
        })
        
        # Perform hybrid search
        results = embedder.hybrid_search(vectorstore, message, k=5)
        print(f"Found {len(results)} relevant chunks for query: {message}")
        
        # Prepare sources
        sources = []
        if results:
            for i, doc in enumerate(results):
                try:
                    sources.append({
                        "id": str(i + 1),
                        "title": doc.metadata.get('title', 'Untitled'),
                        "url": doc.metadata.get('source', '#'),
                        "chunk_number": doc.metadata.get('chunk_number', 'N/A'),
                        "preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
                    })
                except Exception as e:
                    print(f"Error processing document metadata {i}: {str(e)}")
                    continue
            
            # Send sources first
            if sources:
                await websocket.send_json({
                    "type": "sources",
                    "sources": sources,
                    "message_id": message_id
                })
            
            # Prepare the context for the LLM
            context = "\n\n".join([f"Source {i+1}:\n{doc.page_content}" for i, doc in enumerate(results)])
            
            # --- System Prompt (Externalized for DRY and clarity) ---
            SYSTEM_PROMPT = """
You are a highly experienced and approachable Developer Advocate, specializing in making complex technical concepts easy to understand for "noob" or beginner developers. Your primary goal is to empower them to confidently use documentation and write code.

Here are your core responsibilities and characteristics:

1.  **Audience First (Noob Developers):**
    * Assume the user has minimal prior knowledge. Avoid jargon where possible, and if jargon is necessary, always explain it clearly and concisely.
    * Break down complex topics into small, digestible steps.
    * Be patient, encouraging, and supportive. Never make the user feel foolish for asking "basic" questions.
    * Anticipate common pitfalls and offer solutions or warnings.

2.  **Documentation Expert:**
    * Refer to and explain concepts directly from the provided documentation.
    * Highlight key sections or examples within the documentation.
    * Show them *how* to read and interpret documentation effectively, not just *what* it says.
    * If a concept isn't directly in the provided context, gracefully explain that, and if appropriate, suggest where else they might look (e.g., "While this specific detail isn't in the current documentation, generally you'd look for X in Y documentation").

3.  **Coding Assistant & Best Practices Coach:**
    * When providing code, make it runnable, clear, and well-commented.
    * Explain *why* a particular code snippet works, focusing on the underlying concepts.
    * Offer practical, real-world examples that resonate with a beginner's learning journey.
    * Suggest best practices for writing clean, efficient, and maintainable code.
    * If there are multiple ways to achieve something, briefly explain the pros and cons for a beginner.

4.  **Communication Style:**
    * **Tone:** Friendly, enthusiastic, encouraging, and highly professional.
    * **Clarity:** Use simple, direct language. Avoid overly academic or theoretical explanations unless specifically requested and then simplify them.
    * **Formatting:** Utilize Markdown extensively for readability:
        * Headings (`#`, `##`, `###`) for structure.
        * Bullet points or numbered lists for steps or concepts.
        * Code blocks (```python`, ```javascript`, etc.) for all code examples.
        * Bold (`**text**`) for emphasis on keywords or important points.
        * Inline code (`` `code` ``) for variable names, function calls, etc.
    * **Interactive:** Encourage follow-up questions and provide clear calls to action.

5.  **Constraints:**
    * Only use information from the provided documentation/context. If the answer isn't in the provided context, state that clearly and offer general guidance if appropriate, but do not hallucinate specific details from other sources.
    * Do not engage in casual conversation outside of the dev advocacy role. Stay focused on technical assistance.
    * Do not give personal opinions or speculate beyond the scope of the documentation.

**Always strive to make learning enjoyable and accessible for every new developer!**
"""
            prompt_template = SYSTEM_PROMPT + """

Context:
{context}

Question: {question}
"""
            prompt = ChatPromptTemplate.from_template(prompt_template)
            
            # Create a chain using embedder.llm (assuming embedder has an llm attribute)
            chain = (
                {"context": lambda x: context, "question": lambda x: x["question"]}
                | prompt
                | embedder.llm # Use embedder.llm here
                | StrOutputParser()
            )
            
            response_chunks = []
            try:
                async for chunk in chain.astream({"question": message}):
                    response_chunks.append(chunk)
                    await websocket.send_json({
                        "type": "chat_response",
                        "response": chunk,
                        "message_id": message_id,
                        "is_complete": False # Indicate that more chunks are coming
                    })
                
                full_response = "".join(response_chunks)
                # Send final completion message with full response and sources
                await websocket.send_json({
                    "type": "chat_response",
                    "response": full_response,
                    "sources": sources,
                    "message_id": message_id,
                    "is_complete": True # Indicate that the response is complete
                })
            except Exception as e:
                print(f"Error streaming LLM response: {str(e)}")
                await websocket.send_json({
                    "type": "chat_response",
                    "response": "Sorry, I encountered an error while generating a response. Please try again later.",
                    "sources": [],
                    "message_id": message_id,
                    "is_complete": True
                })
        else:
            # No relevant results found
            await websocket.send_json({
                "type": "chat_response",
                "response": "I couldn't find any relevant information to answer your question.",
                "sources": [],
                "message_id": message_id,
                "is_complete": True
            })
    except Exception as e:
        print(f"Unhandled error in handle_chat_message: {str(e)}")
        await websocket.send_json({
            "type": "chat_response",
            "response": "An unexpected error occurred while processing your message. Please try again.",
            "sources": [],
            "message_id": message_id,
            "is_complete": True
        })
    finally:
        # Ensure typing indicator is hidden regardless of success or failure
        try:
            await websocket.send_json({
                "type": "typing",
                "is_typing": False,
                "message_id": message_id
            })
        except Exception as e:
            print(f"Error sending typing indicator off: {e}")


# Keep the original HTTP endpoint for compatibility, but direct to WebSocket
@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """HTTP endpoint for chat (recommends WebSocket for interactive use)."""
    global vectorstore, embedder
    
    try:
        if not vectorstore:
            raise HTTPException(status_code=503, detail="Vector store not initialized. Please load some data first.")
            
        if not message.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty.")
        
        # For HTTP, we'll just return a simple response
        return ChatResponse(
            response="Please use the WebSocket endpoint (/ws) for interactive chat. See /docs for WebSocket endpoint details.",
            sources=[]
        )
    except HTTPException as e:
        raise e # Re-raise FastAPI HTTPExceptions
    except Exception as e:
        print(f"Error in HTTP chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

SITES_METADATA_FILE = "sites_metadata.json"

def load_sites_metadata():
    global scraped_sites, crawl_status
    try:
        with open(SITES_METADATA_FILE, "r") as f:
            data = json.load(f)
            scraped_sites = data.get("scraped_sites", {})
            crawl_status = data.get("crawl_status", {})
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as e:
        print(f"Error loading sites metadata: {e}")

def save_sites_metadata():
    global scraped_sites, crawl_status
    data = {
        "scraped_sites": scraped_sites,
        "crawl_status": crawl_status
    }
    with open(SITES_METADATA_FILE, "w") as f:
        json.dump(data, f)

@app.post("/api/add-site")
async def add_site(url_input: URLInput):
    """Initiates crawling and processing for a new site."""
    try:
        if not vectorstore:
            raise HTTPException(status_code=503, detail="Vector store not initialized. Please load some data first.")
            
        site_id = str(uuid.uuid4())
        site_name = url_input.name or url_input.url
        
        # Initialize crawl status
        crawl_status[site_id] = {
            "status": "starting",
            "progress": 0.0,
            "total_urls": 0,
            "processed_urls": 0,
            "current_url": "",
            "chunks_added": 0
        }
        
        scraped_sites[site_id] = {
            "id": site_id,
            "name": site_name,
            "url": url_input.url,
            "added_at": datetime.now().isoformat(),
            "status": "crawling",
            "total_chunks": 0
        }
        
        save_sites_metadata()
        
        # Start crawling in background
        asyncio.create_task(crawl_site_background(site_id, url_input.url))
        
        # Broadcast site added event (manager.broadcast expects dict)
        await manager.broadcast({
            "type": "site_added",
            "site": scraped_sites[site_id]
        })
        
        return {"site_id": site_id, "message": "Crawling started"}
    except Exception as e:
        print(f"Error adding site: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add site: {str(e)}")

async def crawl_site_background(site_id: str, start_url: str):
    """Background task to crawl a site, process content, and store in vectorstore."""
    global vectorstore, embedder
    try:
        # Update status to finding URLs
        crawl_status[site_id]["status"] = "finding_urls"
        save_sites_metadata()
        await manager.broadcast({
            "type": "crawl_status",
            "site_id": site_id,
            "status": crawl_status[site_id].copy()
        })
        
        urls = []
        try:
            # Find URLs via sitemap or crawl4ai
            sitemap_url = find_sitemap(start_url)
            if sitemap_url:
                print(f"Found sitemap at {sitemap_url}")
                urls = parse_sitemap(sitemap_url)
            else:
                print("No sitemap found, discovering URLs with crawl4ai...")
                urls = await discover_with_crawl4ai(start_url)
            
            if not urls:
                raise ValueError("No URLs found to crawl for the given site.")
                
            print(f"Found {len(urls)} URLs to process for site {site_id}")
            
            crawl_status[site_id]["total_urls"] = len(urls)
            crawl_status[site_id]["status"] = "crawling"
            save_sites_metadata()
            
            # Callback function for processing each crawled URL
            async def process_callback(url: str, content: str):
                try:
                    if not content or not content.strip():
                        print(f"Skipping empty content for {url}")
                        return
                        
                    docs = embedder.split_and_embed(url, content)
                    if not docs:
                        print(f"No documents generated for {url}")
                        return
                        
                    store_in_chromadb(docs, vectorstore)
                    
                    # Update progress
                    crawl_status[site_id]["processed_urls"] += 1
                    crawl_status[site_id]["chunks_added"] += len(docs)
                    crawl_status[site_id]["current_url"] = url
                    
                    total = max(1, crawl_status[site_id]["total_urls"])
                    processed = crawl_status[site_id]["processed_urls"]
                    crawl_status[site_id]["progress"] = min(100.0, (processed / total) * 100.0)
                    
                    scraped_sites[site_id]["total_chunks"] = crawl_status[site_id]["chunks_added"]
                    save_sites_metadata()
                    
                    # Only broadcast updates periodically to avoid excessive WebSocket traffic
                    if processed % max(1, total // 20) == 0 or processed == total:
                        await manager.broadcast({
                            "type": "crawl_progress",
                            "site_id": site_id,
                            "status": crawl_status[site_id].copy()
                        })
                        
                except Exception as e:
                    print(f"Error processing content for URL {url}: {str(e)}")
                    # Increment processed_urls even on error to ensure progress continues
                    crawl_status[site_id]["processed_urls"] += 1
                    total = max(1, crawl_status[site_id]["total_urls"])
                    processed = crawl_status[site_id]["processed_urls"]
                    crawl_status[site_id]["progress"] = min(100.0, (processed / total) * 100.0)
                    save_sites_metadata()
                    await manager.broadcast({ # Broadcast error for specific URL
                        "type": "crawl_url_error",
                        "site_id": site_id,
                        "url": url,
                        "error": str(e)
                    })
            
            # Process all URLs
            await crawl_and_process(urls, process_callback)
            
            # Mark as completed
            crawl_status[site_id]["status"] = "completed"
            scraped_sites[site_id]["status"] = "completed"
            save_sites_metadata()
            
            await manager.broadcast({
                "type": "crawl_completed",
                "site_id": site_id,
                "total_chunks": crawl_status[site_id]["chunks_added"]
            })
            
        except Exception as e:
            print(f"Error during URL discovery or main crawl loop for site {site_id}: {str(e)}")
            crawl_status[site_id]["status"] = "error"
            crawl_status[site_id]["error"] = str(e)
            scraped_sites[site_id]["status"] = "error"
            save_sites_metadata()
            
            await manager.broadcast({
                "type": "crawl_error",
                "site_id": site_id,
                "error": str(e)
            })
    except Exception as e:
        print(f"Critical error in crawl_site_background for site {site_id}: {str(e)}")
        # Ensure status is updated even for unexpected errors outside the main try block
        if site_id in crawl_status:
            crawl_status[site_id]["status"] = "error"
            crawl_status[site_id]["error"] = str(e)
        if site_id in scraped_sites:
            scraped_sites[site_id]["status"] = "error"
        save_sites_metadata()
        await manager.broadcast({
            "type": "crawl_error",
            "site_id": site_id,
            "error": f"Unexpected critical error during crawl: {str(e)}"
        })

@app.get("/api/sites")
async def get_sites():
    """Returns a list of all currently tracked scraped sites."""
    load_sites_metadata()  # Always load latest from disk
    return {"sites": list(scraped_sites.values())}

@app.get("/api/crawl-status/{site_id}")
async def get_crawl_status(site_id: str):
    """Returns crawl status for a given site."""
    load_sites_metadata()
    status = crawl_status.get(site_id)
    if not status:
        return {"error": "No crawl status found for site_id"}
    return {
        "progress": status.get("progress", 0.0),
        "total_urls": status.get("total_urls", 0),
        "processed_urls": status.get("processed_urls", 0),
        "chunks_added": status.get("chunks_added", 0),
        "current_url": status.get("current_url", ""),
        "error": status.get("error", None),
        "status": status.get("status", "")
    }

@app.delete("/api/sites/{site_id}")
async def delete_site(site_id: str):
    """Deletes a site's data from the vectorstore and memory."""
    try:
        if site_id not in scraped_sites:
            raise HTTPException(status_code=404, detail="Site not found.")
        
        site = scraped_sites[site_id]
        
        # Delete from ChromaDB based on the source URL
        delete_from_chromadb(vectorstore, {"source": site["url"]})
        print(f"Deleted data for site {site_id} (URL: {site['url']}) from ChromaDB.")
        
        # Remove from memory
        del scraped_sites[site_id]
        if site_id in crawl_status:
            del crawl_status[site_id]
        save_sites_metadata()
        
        await manager.broadcast({
            "type": "site_deleted",
            "site_id": site_id
        })
        
        return {"message": "Site deleted successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error deleting site {site_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete site: {str(e)}")

@app.delete("/api/database")
async def clear_database():
    """Clears all data from the vectorstore and resets tracked sites."""
    global vectorstore
    try:
        # Clear ChromaDB collection
        if vectorstore:
            vectorstore.delete_collection()
            print("ChromaDB collection deleted.")
        
        # Clear in-memory data
        scraped_sites.clear()
        crawl_status.clear()
        save_sites_metadata()
        print("In-memory site data cleared.")
        
        # Delete metadata file
        try:
            if os.path.exists(SITES_METADATA_FILE):
                os.remove(SITES_METADATA_FILE)
        except Exception as e:
            print(f"Failed to delete sites metadata file: {e}")
        
        # Reinitialize vectorstore to ensure it's ready for new data
        vectorstore = load_chromadb_vectorstore()
        print("Vectorstore reinitialized.")
        
        await manager.broadcast({
            "type": "database_cleared"
        })
        
        return {"message": "Database cleared successfully."}
    except Exception as e:
        print(f"Error clearing database: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Ensure the static directory exists before running uvicorn
    Path("static").mkdir(exist_ok=True, parents=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)
