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
    exclude_tests: Optional[bool] = None  # None = auto-detect (>40%), True = exclude, False = include

class QueryRequest(BaseModel):
    query: str
    context: dict  # Adjust to accept dictionary context

def store_repo_data(repo_metadata):
    # Log the storage action for debugging
    print(f"Storing repository metadata: {repo_metadata}")

def store_parsed_data(parsed_data):
    # Log the storage action for debugging
    print(f"Storing parsed AST data: {parsed_data}")

def analyze_directory_contributions(repo_content):
    """
    Analyze which directories contribute most files (for smart filtering).

    Returns:
        Dict of {dir_name: {'count': int, 'percentage': float, 'sample_files': list}}
    """
    from collections import defaultdict

    dir_stats = defaultdict(lambda: {'count': 0, 'files': []})
    total_files = len(repo_content)

    # Directories to analyze (enterprise-grade filtering targets)
    target_dirs = ['tests/', 'migrations/', 'locale/', 'static/', 'templates/', 'docs/', 'docs_src/', 'examples/']

    for file_info in repo_content:
        path = file_info['path']
        for target_dir in target_dirs:
            if target_dir in path or path.startswith(target_dir):
                # Extract root directory name (e.g., 'django/contrib/admin/tests/' → 'tests/')
                dir_stats[target_dir]['count'] += 1
                if len(dir_stats[target_dir]['files']) < 3:  # Keep 3 sample files
                    dir_stats[target_dir]['files'].append(path)
                break

    # Calculate percentages
    result = {}
    for dir_name, stats in dir_stats.items():
        if stats['count'] > 0:
            result[dir_name] = {
                'count': stats['count'],
                'percentage': (stats['count'] / total_files) * 100,
                'sample_files': stats['files']
            }

    return result

def filter_repository_content(repo_content, exclude_docs=None, exclude_examples=None, exclude_tests=None):
    """
    Enterprise-grade tiered directory filtering with smart auto-detection.

    Tier 1: Always exclude (docs, examples) for large repos
    Tier 2: Smart exclude (tests, migrations) if >40% contribution
    Tier 3: Notify user of exclusions with savings calculation

    Args:
        repo_content: List of {path, content} dicts
        exclude_docs: None (auto), True (force exclude), False (force include)
        exclude_examples: None (auto), True (force exclude), False (force include)
        exclude_tests: None (auto), True (force exclude), False (force include)

    Returns:
        Tuple of (filtered_content, metadata_dict)
        metadata_dict contains: excluded_dirs, notifications, savings
    """
    total_files = len(repo_content)
    original_count = total_files

    # Analyze directory contributions
    dir_contributions = analyze_directory_contributions(repo_content)

    logging.info(f"📊 SMART FILTER: Analyzing {total_files} files...")
    for dir_name, stats in sorted(dir_contributions.items(), key=lambda x: x[1]['percentage'], reverse=True):
        logging.info(f"   {dir_name}: {stats['count']} files ({stats['percentage']:.1f}%)")

    excluded_dirs = []
    notifications = []

    # TIER 1: Always exclude docs and examples for large repos (>500 files)
    has_docs = 'docs/' in dir_contributions or 'docs_src/' in dir_contributions
    has_examples = 'examples/' in dir_contributions

    if exclude_docs is None:
        exclude_docs = has_docs and total_files > 500
    if exclude_examples is None:
        exclude_examples = has_examples and total_files > 500

    if exclude_docs and has_docs:
        before = len(repo_content)
        repo_content = [f for f in repo_content if not (
            'docs/' in f['path'] or f['path'].startswith('docs/') or
            'docs_src/' in f['path'] or f['path'].startswith('docs_src/')
        )]
        after = len(repo_content)
        excluded_count = before - after
        excluded_dirs.append('docs/')

        notifications.append({
            'type': 'tier1_auto',
            'directory': 'docs/',
            'files_excluded': excluded_count,
            'reason': 'Documentation files are not needed for understanding code implementation',
            'savings_pct': int((excluded_count / original_count) * 100)
        })
        logging.info(f"📁 Tier 1: Excluded docs/ ({excluded_count} files)")

    if exclude_examples and has_examples:
        before = len(repo_content)
        repo_content = [f for f in repo_content if not ('examples/' in f['path'] or f['path'].startswith('examples/'))]
        after = len(repo_content)
        excluded_count = before - after
        excluded_dirs.append('examples/')

        notifications.append({
            'type': 'tier1_auto',
            'directory': 'examples/',
            'files_excluded': excluded_count,
            'reason': 'Example code is redundant with actual implementation',
            'savings_pct': int((excluded_count / original_count) * 100)
        })
        logging.info(f"📁 Tier 1: Excluded examples/ ({excluded_count} files)")

    # TIER 2: Smart exclude tests if >40% contribution AND repo is large (>1000 files)
    if total_files > 1000:
        tests_stats = dir_contributions.get('tests/', {})
        migrations_stats = dir_contributions.get('migrations/', {})
        locale_stats = dir_contributions.get('locale/', {})
        static_stats = dir_contributions.get('static/', {})
        templates_stats = dir_contributions.get('templates/', {})

        # Auto-exclude tests if >40% of repo (enterprise heuristic)
        if exclude_tests is None and tests_stats.get('percentage', 0) > 40:
            exclude_tests = True
            logging.info(f"🧠 SMART DETECTION: tests/ is {tests_stats['percentage']:.1f}% of repo (>40% threshold) → Auto-excluding")

        if exclude_tests and tests_stats:
            before = len(repo_content)
            repo_content = [f for f in repo_content if not ('tests/' in f['path'] or f['path'].startswith('tests/') or '/test_' in f['path'])]
            after = len(repo_content)
            excluded_count = before - after
            excluded_dirs.append('tests/')

            notifications.append({
                'type': 'tier2_smart',
                'directory': 'tests/',
                'files_excluded': excluded_count,
                'reason': 'Test files are not core implementation (configure in Advanced Options to include)',
                'savings_pct': int((excluded_count / original_count) * 100),
                'contribution_pct': tests_stats['percentage'],
                'can_override': True
            })
            logging.info(f"📁 Tier 2: Smart-excluded tests/ ({excluded_count} files, {tests_stats['percentage']:.1f}% of repo)")

        # Auto-exclude migrations if >20% AND >500 migration files
        if migrations_stats.get('count', 0) > 500 and migrations_stats.get('percentage', 0) > 20:
            before = len(repo_content)
            repo_content = [f for f in repo_content if not ('migrations/' in f['path'] or f['path'].startswith('migrations/'))]
            after = len(repo_content)
            excluded_count = before - after
            excluded_dirs.append('migrations/')

            notifications.append({
                'type': 'tier2_smart',
                'directory': 'migrations/',
                'files_excluded': excluded_count,
                'reason': 'Database migrations are generated code, not core implementation',
                'savings_pct': int((excluded_count / original_count) * 100)
            })
            logging.info(f"📁 Tier 2: Smart-excluded migrations/ ({excluded_count} files)")

        # Auto-exclude locale if >200 files (translation files)
        if locale_stats.get('count', 0) > 200:
            before = len(repo_content)
            repo_content = [f for f in repo_content if not ('locale/' in f['path'] or f['path'].startswith('locale/'))]
            after = len(repo_content)
            excluded_count = before - after
            excluded_dirs.append('locale/')

            notifications.append({
                'type': 'tier2_smart',
                'directory': 'locale/',
                'files_excluded': excluded_count,
                'reason': 'Translation files are not code logic',
                'savings_pct': int((excluded_count / original_count) * 100)
            })
            logging.info(f"📁 Tier 2: Smart-excluded locale/ ({excluded_count} files)")

    # Calculate total savings
    final_count = len(repo_content)
    total_excluded = original_count - final_count
    total_savings_pct = int((total_excluded / original_count) * 100) if total_excluded > 0 else 0

    if excluded_dirs:
        logging.info(f"✂️  FINAL FILTER: {original_count} → {final_count} files ({total_savings_pct}% reduction)")
        logging.info(f"   Excluded directories: {', '.join(excluded_dirs)}")

    metadata = {
        'excluded_dirs': excluded_dirs,
        'notifications': notifications,
        'original_file_count': original_count,
        'filtered_file_count': final_count,
        'total_savings_pct': total_savings_pct,
        'dir_contributions': dir_contributions
    }

    return repo_content, metadata

@app.post("/api/upload_repo")
async def upload_repo(link: RepoLink):
    try:
        repo_url = link.repo_url
        sub_directory = link.sub_directory
        exclude_docs = link.exclude_docs
        exclude_examples = link.exclude_examples
        exclude_tests = link.exclude_tests
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

        # Apply enterprise-grade tiered filtering with smart auto-detection
        repo_content, filter_metadata = filter_repository_content(repo_content, exclude_docs, exclude_examples, exclude_tests)

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

        # Enterprise-grade mega-repo detection
        # Warn users about extremely large repos (PyTorch, TensorFlow, Linux kernel scale)
        # Threshold: 20K chunks (Django=11.7K works, PyTorch=92K is too large)
        mega_repo_warning = None
        if chunk_stats['total'] > 20000:
            mega_repo_warning = {
                'type': 'mega_repo',
                'chunk_count': chunk_stats['total'],
                'message': f"⚠️ This repository is extremely large ({chunk_stats['total']:,} chunks).",
                'recommendation': "For faster analysis and better performance, we recommend using the 'subdirectory' field to focus on a specific module.",
                'examples': {
                    'pytorch': "Try subdirectory: 'torch' or 'torch/nn'",
                    'tensorflow': "Try subdirectory: 'tensorflow/python'",
                    'chromium': "Try subdirectory: 'chrome/browser'"
                },
                'impact': {
                    'upload_time': 'May take 2-5 minutes',
                    'graph_size': f'~{chunk_stats["total"] * 1.1:,.0f} nodes (very large)',
                    'query_time': 'Queries may be slower (~15-20 seconds)'
                }
            }
            logging.warning(f"⚠️ MEGA-REPO DETECTED: {chunk_stats['total']:,} chunks")
            logging.warning(f"   Upload will continue but may take 2-5 minutes")
            logging.warning(f"   Recommend using subdirectory field for better performance")

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
            "filter_metadata": filter_metadata,  # Enterprise-grade filtering info with notifications
            "mega_repo_warning": mega_repo_warning  # Warning for extremely large repos
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
