# backend/main.py
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.api.github_api import fetch_repo_content, fetch_repo_content_via_git, fetch_repo_metadata
from backend.api.langchain_integration import get_jamba_response
from backend.api.ast_parser import parse_code_to_ast
from backend.api.data_storage import initialize_database, store_repository_metadata, store_ast_data, store_chunks_batch, retrieve_chunks
from backend.api.chunk_processor import process_repository_to_chunks, get_chunk_stats
from backend.api.chatbot import router as chatbot_router
from backend.api.graph_generator import create_dependency_graph, create_chunk_level_graph, save_graph_as_json, load_graph_from_json
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
    exclude_docs: Optional[bool] = None  # None = auto-detect, True = exclude, False = include
    exclude_examples: Optional[bool] = None  # None = auto-detect, True = exclude, False = include

class QueryRequest(BaseModel):
    query: str
    context: dict  # Adjust to accept dictionary context

def store_repo_data(repo_metadata):
    # Log the storage action for debugging
    print(f"Storing repository metadata: {repo_metadata}")

def store_parsed_data(parsed_data):
    # Log the storage action for debugging
    print(f"Storing parsed AST data: {parsed_data}")

def filter_repository_content(repo_content, exclude_docs=None, exclude_examples=None):
    """
    Smart directory filtering with auto-detection for large repositories.

    Args:
        repo_content: List of {path, content} dicts
        exclude_docs: None (auto), True (force exclude), False (force include)
        exclude_examples: None (auto), True (force exclude), False (force include)

    Returns:
        Filtered repo_content, excluded_dirs list
    """
    total_files = len(repo_content)

    # Detect if docs/, docs_src/, or examples/ exist
    # Note: docs_src/ is common in Python projects (FastAPI, Pydantic, etc.) for tutorial code
    has_docs = any(
        'docs/' in f['path'] or f['path'].startswith('docs/') or
        'docs_src/' in f['path'] or f['path'].startswith('docs_src/')
        for f in repo_content
    )
    has_examples = any('examples/' in f['path'] or f['path'].startswith('examples/') for f in repo_content)

    # Auto-detection logic: Exclude if repo is large (>500 files) AND directory exists
    if exclude_docs is None:
        exclude_docs = has_docs and total_files > 500
    if exclude_examples is None:
        exclude_examples = has_examples and total_files > 500

    excluded_dirs = []

    # Apply filters
    if exclude_docs and has_docs:
        repo_content = [f for f in repo_content if not (
            'docs/' in f['path'] or f['path'].startswith('docs/') or
            'docs_src/' in f['path'] or f['path'].startswith('docs_src/')
        )]
        excluded_dirs.append('docs/')
        logging.info(f"📁 Excluded docs/ and docs_src/ directories (large repo optimization)")

    if exclude_examples and has_examples:
        repo_content = [f for f in repo_content if not ('examples/' in f['path'] or f['path'].startswith('examples/'))]
        excluded_dirs.append('examples/')
        logging.info(f"📁 Excluded examples/ directory (large repo optimization)")

    if excluded_dirs:
        logging.info(f"✂️  Filtered: {total_files} → {len(repo_content)} files (excluded: {', '.join(excluded_dirs)})")

    return repo_content, excluded_dirs

@app.post("/api/upload_repo")
async def upload_repo(link: RepoLink):
    try:
        repo_url = link.repo_url
        sub_directory = link.sub_directory
        exclude_docs = link.exclude_docs
        exclude_examples = link.exclude_examples
        auth_token = os.getenv("GITHUB_AUTH_TOKEN")

        # Fetch repository content using git clone (faster, no rate limits)
        # Fallback to API if git not available
        logging.debug(f"Fetching content for repo: {repo_url}")

        try:
            # Try git clone first (industry standard, no rate limits)
            repo_content = fetch_repo_content_via_git(repo_url, sub_directory)
            logging.info(f"✅ Fetched {len(repo_content)} files via git clone (0 API calls)")
        except Exception as git_error:
            # Fallback to GitHub API if git fails
            logging.warning(f"Git clone failed: {git_error}, falling back to GitHub API")
            repo_content = fetch_repo_content(repo_url, auth_token, sub_directory)
            logging.info(f"✅ Fetched {len(repo_content)} files via GitHub API")

        # Apply smart directory filtering (enterprise-grade optimization)
        repo_content, excluded_dirs = filter_repository_content(repo_content, exclude_docs, exclude_examples)

        logging.debug(f"Fetched repo content: {len(repo_content)} files")
        
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

        # Enhanced logging for method-level chunking
        logging.info(f"📊 CHUNKING STATS: Generated {chunk_stats['total']} chunks from {chunk_stats.get('files_processed', 0)} files")
        logging.info(f"   By type: {chunk_stats.get('by_type', {})}")
        logging.info(f"   Token stats: avg={chunk_stats.get('avg_tokens', 0):.0f}, max={chunk_stats.get('max_tokens', 0)}, >800tok={chunk_stats.get('chunks_over_800_tokens', 0)}")
        logging.info(f"   Truncated: {chunk_stats.get('chunks_truncated', 0)} chunks")

        # Store chunks in database
        store_chunks_batch(repo_id, chunks)
        logging.debug("Chunks stored in database")

        # Save parsed data as context (keep for backward compatibility)
        with open("context.json", "w") as context_file:
            json.dump(parsed_data, context_file)

        # Create and save the dependency graph
        # Auto-detect: Use chunk-level graph if chunks have method-level data
        logging.info(f"🔍 GRAPH CREATION: Analyzing {len(chunks)} chunks for graph type detection...")

        # Check if ANY chunk is a method (not just first 10 - test files come first!)
        has_method_level_chunks = any(
            chunk.get('type') == 'method'
            for chunk in chunks
        )

        logging.info(f"   Detection result: has_method_level_chunks = {has_method_level_chunks}")
        if has_method_level_chunks:
            method_count = sum(1 for c in chunks if c.get('type') == 'method')
            logging.info(f"   Found {method_count} method chunks")

        if has_method_level_chunks:
            logging.info("📊 Creating CHUNK-LEVEL graph (method-level chunks detected)...")
            logging.info(f"   Sample chunk types: {[c.get('type') for c in chunks[:5]]}")
            graph = create_chunk_level_graph(chunks)
            logging.info(f"✅ Chunk-level graph created with {len(graph.nodes())} nodes, {len(graph.edges())} edges")
        else:
            logging.info("📊 Creating FILE-LEVEL graph (legacy chunks detected)...")
            graph = create_dependency_graph(parsed_data)
            logging.info(f"✅ File-level graph created with {len(graph.nodes())} nodes, {len(graph.edges())} edges")

        save_graph_as_json(graph, "dependency_graph.json")
        logging.info("💾 Graph saved to dependency_graph.json")

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
            "files_processed": chunk_stats.get('files_processed', 0),
            "excluded_dirs": excluded_dirs  # Tell frontend what was excluded
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

@app.get("/api/debug/chunks/{repo_id}")
async def debug_chunks(repo_id: int, search: Optional[str] = None):
    """
    DEBUG ENDPOINT: Inspect chunks and search results

    Usage:
    - /api/debug/chunks/1 - List all chunks for repo
    - /api/debug/chunks/1?search=route - Search chunks by name/file
    """
    try:
        chunks = retrieve_chunks(repo_id)

        if search:
            # Filter chunks matching search term
            matching = [c for c in chunks if search.lower() in c['name'].lower() or search.lower() in c['file_path'].lower()]
            return {
                "total_chunks": len(chunks),
                "search_term": search,
                "matching_chunks": len(matching),
                "results": [
                    {
                        "chunk_id": c['chunk_id'],
                        "name": c['name'],
                        "type": c['type'],
                        "file": c['file_path'],
                        "lines": f"{c['start_line']}-{c['end_line']}",
                        "code_preview": c['code'][:200] + "..." if len(c['code']) > 200 else c['code']
                    }
                    for c in matching[:20]
                ]
            }
        else:
            # Return summary stats
            by_type = {}
            by_file = {}
            for c in chunks:
                by_type[c['type']] = by_type.get(c['type'], 0) + 1
                by_file[c['file_path']] = by_file.get(c['file_path'], 0) + 1

            return {
                "total_chunks": len(chunks),
                "by_type": by_type,
                "files_with_chunks": len(by_file),
                "sample_chunk_ids": [c['chunk_id'] for c in chunks[:10]]
            }
    except Exception as e:
        logging.error(f"Error in debug_chunks: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/api/debug/graph")
async def debug_graph():
    """
    DEBUG ENDPOINT: Inspect current dependency graph structure

    Returns info about nodes and their IDs
    """
    try:
        graph = load_graph_from_json("dependency_graph.json")
        data = json_graph.node_link_data(graph)

        nodes_by_type = {}
        for node in data["nodes"]:
            node_type = node.get('type', 'unknown')
            nodes_by_type[node_type] = nodes_by_type.get(node_type, 0) + 1

        return {
            "total_nodes": len(data["nodes"]),
            "total_edges": len(data["links"]),
            "nodes_by_type": nodes_by_type,
            "sample_node_ids": [n['id'] for n in data["nodes"][:10]],
            "sample_nodes": [
                {"id": n['id'], "type": n.get('type', '?'), "label": n.get('label', '?')}
                for n in data["nodes"][:10]
            ]
        }
    except Exception as e:
        logging.error(f"Error in debug_graph: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# Include the chatbot router
app.include_router(chatbot_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
