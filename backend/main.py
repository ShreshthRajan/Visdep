# backend/main.py
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata
from backend.api.langchain_integration import get_jamba_response
from backend.api.ast_parser import parse_code_to_ast
from backend.api.data_storage import initialize_database, store_repository_metadata, store_ast_data, store_chunks_batch, retrieve_chunks
from backend.api.chunk_processor import process_repository_to_chunks, get_chunk_stats
from backend.api.chatbot import router as chatbot_router
from backend.api.graph_generator import create_dependency_graph, save_graph_as_json, load_graph_from_json
from networkx.readwrite import json_graph
from dotenv import load_dotenv
from typing import Optional
import logging
import asyncio

# Load environment variables from .env file
load_dotenv()

# Initialize database on startup
initialize_database()

# Global variable to store latest repo_id (simple solution for prototype)
latest_repo_id = None

app = FastAPI()

# Add CORS middleware to allow requests from the frontend
# Supports both local development and production
ALLOWED_ORIGINS = os.getenv(
    'ALLOWED_ORIGINS',
    'http://localhost:3000,https://visdep.com,https://*.vercel.app'
).split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure required API keys are set
# AI21 is now optional (we use Claude in Step 3)
if not os.getenv("GITHUB_AUTH_TOKEN"):
    logging.warning("GITHUB_AUTH_TOKEN not set - repository uploads will fail")

# Check for LLM API keys (either Claude or AI21)
if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("AI21_API_KEY"):
    logging.warning("Neither ANTHROPIC_API_KEY nor AI21_API_KEY set - chatbot will not work")

# Check for embeddings API key
if not os.getenv("OPENAI_API_KEY"):
    logging.warning("OPENAI_API_KEY not set - vector store creation will fail")

class RepoLink(BaseModel):
    repo_url: str
    sub_directory: Optional[str] = None

class QueryRequest(BaseModel):
    query: str
    context: dict  # Adjust to accept dictionary context

def store_repo_data(repo_metadata):
    # Log the storage action for debugging
    print(f"Storing repository metadata: {repo_metadata}")

def store_parsed_data(parsed_data):
    # Log the storage action for debugging
    print(f"Storing parsed AST data: {parsed_data}")

@app.post("/api/upload_repo")
async def upload_repo(link: RepoLink):
    try:
        repo_url = link.repo_url
        sub_directory = link.sub_directory
        auth_token = os.getenv("GITHUB_AUTH_TOKEN")
        
        # Fetch repository content and metadata
        logging.debug(f"Fetching content for repo: {repo_url}")
        repo_content = fetch_repo_content(repo_url, auth_token, sub_directory)
        logging.debug(f"Fetched repo content: {repo_content}")
        
        repo_metadata = fetch_repo_metadata(repo_url, auth_token)
        logging.debug(f"Fetched repo metadata: {repo_metadata}")
        
        # Parse the repository content to AST
        parsed_data = parse_code_to_ast(repo_content)
        logging.debug(f"Parsed AST data: {parsed_data}")
        
        # Store repository metadata and parsed AST data
        repo_id = store_repository_metadata(repo_metadata['full_name'], repo_metadata)
        for file_path, ast_info in parsed_data.items():
            store_ast_data(repo_id, file_path, ast_info)

        # Process repository into chunks
        logging.debug("Processing repository into chunks...")
        chunks = process_repository_to_chunks(parsed_data)
        chunk_stats = get_chunk_stats(chunks)
        logging.info(f"Generated {chunk_stats['total']} chunks from {chunk_stats.get('files_processed', 0)} files")
        logging.info(f"Chunk types: {chunk_stats.get('by_type', {})}")

        # Store chunks in database
        store_chunks_batch(repo_id, chunks)
        logging.debug("Chunks stored in database")

        # Save parsed data as context (keep for backward compatibility)
        with open("context.json", "w") as context_file:
            json.dump(parsed_data, context_file)

        # Create and save the dependency graph
        graph = create_dependency_graph(parsed_data)
        save_graph_as_json(graph, "dependency_graph.json")

        # Task 2.1: Invalidate cached queries for this repo (fresh upload = fresh answers)
        from backend.api.data_storage import invalidate_cache_for_repo
        invalidate_cache_for_repo(repo_id)

        # Store repo_id globally for latest upload (simple solution for single-user prototype)
        global latest_repo_id
        latest_repo_id = repo_id

        return {
            "message": "Repository data successfully uploaded, parsed, and graph generated.",
            "repo_id": repo_id,
            "chunks": chunk_stats['total'],
            "files_processed": chunk_stats.get('files_processed', 0)
        }
    
    except Exception as e:
        logging.error(f"Error in upload_repo: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/api/dependency_graph")
async def get_dependency_graph():
    try:
        graph = load_graph_from_json("dependency_graph.json")
        data = json_graph.node_link_data(graph)
        return {"nodes": data["nodes"], "edges": data["links"]}
    except Exception as e:
        logging.error(f"Error in get_dependency_graph: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/api/query")
async def query_jamba(request: QueryRequest):
    try:
        query = request.query
        context = request.context

        # Get response from Jamba model with caching (Task 2.1)
        # Pass latest_repo_id for cache lookup
        global latest_repo_id
        response = await get_jamba_response(query, context, repo_id=latest_repo_id)

        if response:
            # Handle both dict (new format with citations) and string (legacy format)
            if isinstance(response, dict):
                # New format: includes response, citations, highlighted_nodes
                return response
            else:
                # Legacy format: plain string response
                return {"response": response}
        else:
            raise HTTPException(status_code=500, detail="Failed to get a response from the model.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/api/query_stream")
async def query_stream(query: str):
    """
    Task 2.3: Streaming endpoint for real-time Claude responses

    Uses Server-Sent Events (SSE) to stream tokens as they're generated.
    Perceived latency: ~1s to first token (vs 19s for batch).

    Args:
        query: User query (URL parameter)

    Returns:
        StreamingResponse with SSE events
    """
    try:
        from backend.api.langchain_integration import get_jamba_response_stream

        # Load context for latest repo
        global latest_repo_id
        if not latest_repo_id:
            raise HTTPException(status_code=400, detail="No repository loaded. Upload a repository first.")

        # Get chunks from database
        chunks = retrieve_chunks(latest_repo_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="No chunks found for repository.")

        # Convert to context format
        context = {chunk['chunk_id']: chunk for chunk in chunks}

        # Stream response
        async def event_generator():
            try:
                async for token in get_jamba_response_stream(query, context, repo_id=latest_repo_id):
                    # SSE format: data: {token}\n\n
                    yield f"data: {json.dumps({'token': token})}\n\n"
                    await asyncio.sleep(0)  # Allow other tasks

                # Send completion event
                yield f"data: {json.dumps({'done': True})}\n\n"

            except Exception as e:
                logging.error(f"Error in stream generator: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    except Exception as e:
        logging.error(f"Error in query_stream: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/api/context")
async def get_context():
    """
    Get context for LLM

    NEW: Returns chunk-level context from database (Steps 1-3)
    Fallback: Returns file-level context if no chunks available
    """
    global latest_repo_id

    try:
        # NEW: Try to load chunks from database (Steps 1-3 pipeline)
        if latest_repo_id:
            logging.info(f"Loading chunks for repo_id={latest_repo_id}")
            chunks = retrieve_chunks(latest_repo_id)

            if chunks:
                # Convert to dict format {chunk_id: chunk_data}
                chunk_dict = {chunk['chunk_id']: chunk for chunk in chunks}
                logging.info(f"Returning {len(chunks)} chunks (NEW chunk-level format)")
                return chunk_dict

        # Fallback: Load old file-level context
        logging.warning("No chunks available, falling back to file-level context")
        with open("context.json", "r") as context_file:
            context = json.load(context_file)
        return context

    except Exception as e:
        logging.error(f"Error in get_context: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/api/chunks/{repo_id}")
async def get_chunks(repo_id: int):
    """
    NEW ENDPOINT: Get chunks for a repository
    Returns chunk-level context suitable for LLM
    """
    try:
        chunks = retrieve_chunks(repo_id)
        # Convert to dict format for frontend
        chunk_dict = {chunk['chunk_id']: chunk for chunk in chunks}
        return chunk_dict
    except Exception as e:
        logging.error(f"Error in get_chunks: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# Include the chatbot router
app.include_router(chatbot_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
