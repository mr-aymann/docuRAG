# Documentation RAG System
A modern web application that allows you to crawl documentation websites, index their content, and chat with the documentation using Retrieval-Augmented Generation (RAG) powered by LangChain and ChromaDB.

https://github.com/user-attachments/assets/0fac891d-712b-44ba-ae7b-c02fdd63881e

## Features

- 🕷️ Crawl and index documentation websites
- 💬 Chat with your documentation using natural language
- 🔍 Hybrid search combining semantic and keyword search
- 📊 Real-time progress tracking for crawling and indexing
- 🎨 Modern, responsive UI with a clean interface
- 🔄 WebSocket support for real-time updates
- 📱 Mobile-friendly design

## Prerequisites

- Python 3.8+
- Node.js 14+ (for frontend assets)
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd crawl-rag
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Install the frontend dependencies (if you need to modify frontend assets):
   ```bash
   cd static
   npm install
   cd ..
   ```

## Configuration

Create a `.env` file in the project root with the following variables:

```
# API Keys (if needed)
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key

# App settings
DEBUG=True
HOST=0.0.0.0
PORT=8000
```

## Running the Application

1. Start the FastAPI server:
   ```bash
   uvicorn app:app --reload
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:8000
   ```

## Project Structure

```
crawl-rag/
├── app.py                 # FastAPI application
├── requirements.txt       # Python dependencies
├── static/                # Frontend assets (JS, CSS, images)
│   ├── css/
│   ├── js/
│   └── index.html
├── chroma/                # ChromaDB storage
├── crawler.py             # Web crawling functionality
├── embedder.py            # Text embedding and LLM integration
├── storage.py             # Vector store operations
└── utils.py               # Utility functions
```

## API Endpoints

- `GET /` - Serve the frontend application
- `POST /api/chat` - Process chat messages
- `GET /api/sites` - List all indexed sites
- `POST /api/sites` - Add a new site to crawl
- `DELETE /api/sites/{site_id}` - Remove a site
- `DELETE /api/database` - Clear the entire database
- `WS /ws` - WebSocket endpoint for real-time updates

## WebSocket Events

- `site_added` - A new site has been added for crawling
- `crawl_status` - Update on crawling progress
- `crawl_completed` - Crawling has finished
- `crawl_error` - An error occurred during crawling
- `site_deleted` - A site has been removed
- `database_cleared` - The database has been cleared

## Development

### Frontend Development

The frontend is built with vanilla JavaScript and Tailwind CSS. To make changes:

1. Navigate to the `static` directory
2. Edit the HTML, CSS, or JavaScript files
3. The changes will be automatically picked up by the FastAPI server in development mode

### Backend Development

1. The backend uses FastAPI with WebSocket support
2. All API endpoints are documented with OpenAPI (available at `/docs`)
3. Use the `--reload` flag during development for automatic reloading

## Deployment

### Docker

A `Dockerfile` is provided for containerized deployment:

```bash
docker build -t doc-rag .
docker run -p 8000:8000 doc-rag
```

### Production

For production deployment, consider using:

- Gunicorn with Uvicorn workers
- Nginx as a reverse proxy
- Environment variables for configuration
- Proper logging and monitoring

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [LangChain](https://python.langchain.com/) for the RAG framework
- [ChromaDB](https://www.trychroma.com/) for the vector store
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [Tailwind CSS](https://tailwindcss.com/) for the UI components
