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
from backend.api.data_storage import initialize_database, store_repository_metadata, store_chunks_batch, retrieve_chunks
from backend.api.chunk_processor import process_repository_to_chunks, get_chunk_stats
from backend.api.chatbot import router as chatbot_router
from backend.api.graph_generator import (
    create_dependency_graph, 
    create_chunk_level_graph, 
    save_graph_as_json, 
    load_graph_from_json,
    load_graph_positions,
    precompute_graph_with_positions
)
from networkx.readwrite import json_graph
from dotenv import load_dotenv
from typing import Optional, List
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
    user_id: Optional[str] = None  # Phase 2: User who owns this repo
    github_token: Optional[str] = None  # Phase 2: User's OAuth token for private repos

class QueryRequest(BaseModel):
    query: str
    repo_id: Optional[int] = None  # Multi-tenant: Explicit repo_id for user isolation
    context: Optional[dict] = None  # Optional: backend loads from DB server-side
    node_context: Optional[dict] = None  # DEPRECATED: For single per-node queries (backwards compat)
    node_contexts: Optional[List[dict]] = None  # NEW: For multi-node queries [{'chunk_id', 'name', 'type'}, ...]

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
    global latest_repo_id  # Declare global at function top
    
    try:
        repo_url = link.repo_url
        sub_directory = link.sub_directory
        exclude_docs = link.exclude_docs
        exclude_examples = link.exclude_examples
        exclude_tests = link.exclude_tests
        auth_token = os.getenv("GITHUB_AUTH_TOKEN")
        
        # =====================================================================
        # MEGA-REPO OPTIMIZATION: Check for pre-indexed repository
        # =====================================================================
        # Pre-indexed repos (kubernetes, tensorflow, etc.) have all indexes
        # pre-computed. Skip processing and return instantly.
        # =====================================================================
        try:
            from backend.api.supabase_client import get_supabase_client
            supabase = get_supabase_client()
            
            # Extract repo name from URL (e.g., 'kubernetes/kubernetes' from URL)
            repo_name = '/'.join(repo_url.rstrip('/').split('/')[-2:])
            
            # Check if this repo is pre-indexed
            preindexed = supabase.table('preindexed_repos')\
                .select('*')\
                .eq('repo_name', repo_name)\
                .limit(1)\
                .execute()
            
            if preindexed.data and len(preindexed.data) > 0:
                pre = preindexed.data[0]
                logging.info(f"🚀 PRE-INDEXED REPO DETECTED: {repo_name}")
                logging.info(f"   Chunks: {pre['chunk_count']}, Nodes: {pre['node_count']}")
                logging.info(f"   Has: summaries={pre['has_summaries']}, positions={pre['has_positions']}, BM25={pre['has_bm25_index']}")
                
                # Set global repo_id for latest upload
                latest_repo_id = pre['repo_id']
                
                # =====================================================================
                # CRITICAL FIX: Link pre-indexed repo to user in user_repos table
                # Without this, frontend can't find the repo and loads wrong one!
                # =====================================================================
                if link.user_id:
                    try:
                        logging.info(f"🔗 Linking pre-indexed repo to user: user_id={link.user_id}, repo_id={pre['repo_id']}")
                        
                        # Check if this repo already exists for this user
                        existing = supabase.table('user_repos')\
                            .select('*')\
                            .eq('user_id', link.user_id)\
                            .eq('repo_name', repo_name)\
                            .execute()
                        
                        if existing.data and len(existing.data) > 0:
                            # Update last_accessed and ensure local_repo_id is correct
                            logging.info(f"📝 Updating existing repo record (id={existing.data[0]['id']})")
                            supabase.table('user_repos').update({
                                'last_accessed': 'now()',
                                'local_repo_id': pre['repo_id']
                            }).eq('id', existing.data[0]['id']).execute()
                            logging.info(f"✅ Updated pre-indexed repo access for user {link.user_id}")
                        else:
                            # Create new user_repo link
                            logging.info(f"➕ Creating new user_repos record for pre-indexed repo")
                            result = supabase.table('user_repos').insert({
                                'user_id': link.user_id,
                                'repo_name': repo_name,
                                'repo_url': repo_url,
                                'is_private': False,  # Pre-indexed repos are always public
                                'local_repo_id': pre['repo_id']
                            }).execute()
                            logging.info(f"✅ Linked pre-indexed repo {repo_name} to user {link.user_id}, supabase_id={result.data[0]['id'] if result.data else 'unknown'}")
                    except Exception as link_error:
                        # Don't fail the request if linking fails
                        logging.warning(f"⚠️ Failed to link pre-indexed repo to user: {link_error}")
                
                return {
                    "message": f"Pre-indexed repository loaded instantly.",
                    "repo_id": pre['repo_id'],
                    "chunks": pre['chunk_count'],
                    "files_processed": pre['node_count'],
                    "preindexed": True,
                    "filter_metadata": {
                        "excluded_dirs": [],
                        "notifications": [{
                            'type': 'preindexed',
                            'message': f"Repository is pre-indexed with {pre['chunk_count']:,} chunks. All indexes loaded instantly."
                        }],
                        "original_file_count": pre['node_count'],
                        "filtered_file_count": pre['node_count'],
                        "total_savings_pct": 0
                    }
                }
        except Exception as preindex_error:
            # Pre-index check failed, continue with normal upload
            logging.debug(f"Pre-index check: {preindex_error} (continuing normal upload)")

        # Fetch repository content using git clone (faster, no rate limits)
        # Fallback to API if git not available
        try:
            # Try git clone first (industry standard, no rate limits)
            # Phase 2: Pass user's OAuth token for private repo access
            user_oauth_token = link.github_token or None
            repo_content = fetch_repo_content_via_git(repo_url, sub_directory, oauth_token=user_oauth_token)
            logging.info(f"✅ Fetched {len(repo_content)} files via git clone (0 API calls)")
        except Exception as git_error:
            # Fallback to GitHub API if git fails
            logging.warning(f"Git clone failed: {git_error}, falling back to GitHub API")
            # Use user's token if available, otherwise fallback to PAT
            api_token = link.github_token or auth_token
            repo_content = fetch_repo_content(repo_url, api_token, sub_directory)
            logging.info(f"✅ Fetched {len(repo_content)} files via GitHub API")

        # Apply enterprise-grade tiered filtering with smart auto-detection
        repo_content, filter_metadata = filter_repository_content(repo_content, exclude_docs, exclude_examples, exclude_tests)

        repo_metadata = fetch_repo_metadata(repo_url, auth_token)

        # Parse the repository content to AST
        parsed_data = parse_code_to_ast(repo_content)

        # Store repository metadata (returns unique repo_id from Supabase)
        repo_id = store_repository_metadata(repo_metadata['full_name'], repo_metadata)
        logging.info(f"🆔 Supabase assigned repo_id={repo_id} for {repo_metadata['full_name']}")
        # Note: ast_data storage removed - it was never read after upload (unused table)

        # Process repository into chunks
        chunks = process_repository_to_chunks(parsed_data)
        chunk_stats = get_chunk_stats(chunks)

        # Enhanced logging for method-level chunking
        logging.info(f"📊 CHUNKING STATS: Generated {chunk_stats['total']} chunks from {chunk_stats.get('files_processed', 0)} files")
        logging.info(f"   By type: {chunk_stats.get('by_type', {})}")
        logging.info(f"   Token stats: avg={chunk_stats.get('avg_tokens', 0):.0f}, max={chunk_stats.get('max_tokens', 0)}, >800tok={chunk_stats.get('chunks_over_800_tokens', 0)}")
        logging.info(f"   Truncated: {chunk_stats.get('chunks_truncated', 0)} chunks")

        # Store chunks in database
        store_chunks_batch(repo_id, chunks)

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

        save_graph_as_json(graph, repo_id=repo_id)
        logging.info(f"💾 Graph saved to dependency_graph_{repo_id}.json")

        # =======================================================================
        # MEGA-REPO AUTO-POSITIONS: Pre-compute positions for large repos
        # =======================================================================
        # For repos >10K nodes, compute positions server-side during upload.
        # This ensures full beautiful graph on first load (no LOD fallback).
        #
        # Strategy with latency optimization:
        # - 10K-20K nodes: Full spring layout with adaptive iterations
        # - >20K nodes: File structure only (directories + files)
        #
        # Iteration scaling (O(n²) per iteration):
        # - <5K nodes: 100 iterations (~30s)
        # - 5K-10K nodes: 50 iterations (~1 min)
        # - >10K nodes: 30 iterations (~2 min)
        # =======================================================================
        POSITION_THRESHOLD = 10000
        MEGA_THRESHOLD = 20000
        node_count = len(graph.nodes())

        if node_count > POSITION_THRESHOLD:
            try:
                import networkx as nx
                from backend.api.graph_generator import store_graph_positions

                if node_count > MEGA_THRESHOLD:
                    # Very large: compute for file structure only
                    logging.info(f"📍 MEGA-REPO: {node_count:,} nodes - computing positions for file structure only...")

                    structure_nodes = [
                        n for n, data in graph.nodes(data=True)
                        if data.get('type') in ('directory', 'file')
                    ]
                    G_structure = graph.subgraph(structure_nodes).copy()
                    structure_count = len(G_structure.nodes())
                    logging.info(f"   Reduced: {node_count:,} → {structure_count:,} nodes")

                    # Adaptive iterations based on structure size
                    iterations = 30 if structure_count > 10000 else 50 if structure_count > 5000 else 100
                    logging.info(f"   Computing spring layout ({iterations} iterations)...")

                    positions = nx.spring_layout(
                        G_structure,
                        k=2.0 / (structure_count ** 0.5),
                        iterations=iterations,
                        scale=15000,
                        seed=42
                    )
                else:
                    # Medium-large: full spring layout with adaptive iterations
                    iterations = 50 if node_count > 15000 else 75
                    logging.info(f"📍 Computing positions for {node_count:,} nodes ({iterations} iterations)...")
                    positions = nx.spring_layout(
                        graph,
                        k=2.0 / (node_count ** 0.5),
                        iterations=iterations,
                        scale=10000,
                        seed=42
                    )

                # Convert to storage format
                positions_dict = {
                    str(node_id): {'x': float(pos[0]), 'y': float(pos[1])}
                    for node_id, pos in positions.items()
                }

                store_graph_positions(repo_id, positions_dict)
                logging.info(f"✅ Saved {len(positions_dict):,} positions")

            except Exception as pos_error:
                # Don't fail upload if position computation fails
                logging.warning(f"⚠️ Position computation failed (graph will use LOD fallback): {pos_error}")

        # Task 2.1: Invalidate cached queries for this repo (fresh upload = fresh answers)
        from backend.api.data_storage import invalidate_cache_for_repo
        invalidate_cache_for_repo(repo_id)

        # Store repo_id globally for latest upload (simple solution for single-user prototype)
        # Note: global declaration already at top of function (line 325)
        latest_repo_id = repo_id

        # Phase 2: Link repo to user in Supabase (if user_id provided)
        if link.user_id:
            try:
                from backend.api.supabase_client import get_supabase_client
                supabase = get_supabase_client()

                logging.info(f"🔗 Linking repo to Supabase: user_id={link.user_id}, repo_id={repo_id}, repo_name={repo_metadata['full_name']}")

                # Check if this repo already exists for this user
                existing = supabase.table('user_repos').select('*').eq('user_id', link.user_id).eq('repo_name', repo_metadata['full_name']).execute()

                if existing.data and len(existing.data) > 0:
                    # Update last_accessed
                    logging.info(f"📝 Updating existing repo record (id={existing.data[0]['id']}) with local_repo_id={repo_id}")
                    supabase.table('user_repos').update({
                        'last_accessed': 'now()',
                        'local_repo_id': repo_id
                    }).eq('id', existing.data[0]['id']).execute()
                    logging.info(f"✅ Updated repo access time for user {link.user_id}, local_repo_id={repo_id}")
                else:
                    # Create new user_repo link
                    logging.info(f"➕ Creating new user_repos record with local_repo_id={repo_id}")
                    result = supabase.table('user_repos').insert({
                        'user_id': link.user_id,
                        'repo_name': repo_metadata['full_name'],
                        'repo_url': repo_url,
                        'is_private': bool(link.github_token),  # Has token = private
                        'local_repo_id': repo_id
                    }).execute()
                    logging.info(f"✅ Linked repo {repo_metadata['full_name']} to user {link.user_id}, local_repo_id={repo_id}, supabase_id={result.data[0]['id'] if result.data else 'unknown'}")
            except Exception as e:
                # Don't fail upload if Supabase linking fails
                logging.warning(f"⚠️ Failed to link repo to user in Supabase: {e}")

        return {
            "message": "Repository data successfully uploaded, parsed, and graph generated.",
            "repo_id": repo_id,
            "chunks": chunk_stats['total'],
            "files_processed": chunk_stats.get('files_processed', 0),
            "filter_metadata": filter_metadata  # Enterprise-grade filtering info with notifications
        }
    
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logging.error(f"Error in upload_repo: {e}")
        logging.error(f"Full traceback:\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@app.post("/api/upload_repo_stream")
async def upload_repo_stream(link: RepoLink):
    """
    Upload repository with real-time SSE progress streaming.

    Streams progress events at each stage:
    - init: Starting upload
    - preindexed: Found pre-indexed repo (instant complete)
    - clone: Cloning repository
    - clone_done: Clone complete with file count
    - filter: Filtering files
    - parse: Parsing AST
    - chunks: Processing chunks
    - graph: Creating dependency graph
    - positions: Computing positions (for large repos)
    - done: Upload complete
    - error: Error occurred
    """
    def sse_event(event_type: str, data: dict) -> str:
        """Format SSE event with type and JSON data."""
        payload = {"type": event_type, **data}
        return f"data: {json.dumps(payload)}\n\n"

    async def event_generator():
        global latest_repo_id

        try:
            repo_url = link.repo_url
            sub_directory = link.sub_directory
            exclude_docs = link.exclude_docs
            exclude_examples = link.exclude_examples
            exclude_tests = link.exclude_tests
            auth_token = os.getenv("GITHUB_AUTH_TOKEN")

            # Extract repo name for display
            repo_name = '/'.join(repo_url.rstrip('/').split('/')[-2:])

            yield sse_event("init", {
                "message": f"Initializing upload for {repo_name}...",
                "progress": 5,
                "repo_name": repo_name
            })
            await asyncio.sleep(0)  # Allow event to be sent

            # Check for pre-indexed repository
            try:
                from backend.api.supabase_client import get_supabase_client
                supabase = get_supabase_client()

                preindexed = supabase.table('preindexed_repos')\
                    .select('*')\
                    .eq('repo_name', repo_name)\
                    .limit(1)\
                    .execute()

                if preindexed.data and len(preindexed.data) > 0:
                    pre = preindexed.data[0]
                    latest_repo_id = pre['repo_id']

                    # Link to user if provided
                    if link.user_id:
                        try:
                            existing = supabase.table('user_repos')\
                                .select('*')\
                                .eq('user_id', link.user_id)\
                                .eq('repo_name', repo_name)\
                                .execute()

                            if existing.data and len(existing.data) > 0:
                                supabase.table('user_repos').update({
                                    'last_accessed': 'now()',
                                    'local_repo_id': pre['repo_id']
                                }).eq('id', existing.data[0]['id']).execute()
                            else:
                                supabase.table('user_repos').insert({
                                    'user_id': link.user_id,
                                    'repo_name': repo_name,
                                    'repo_url': repo_url,
                                    'is_private': False,
                                    'local_repo_id': pre['repo_id']
                                }).execute()
                        except Exception:
                            pass

                    yield sse_event("preindexed", {
                        "message": f"Pre-indexed repository loaded instantly!",
                        "progress": 100,
                        "repo_id": pre['repo_id'],
                        "chunks": pre['chunk_count'],
                        "nodes": pre['node_count']
                    })
                    yield sse_event("done", {
                        "message": "Repository ready",
                        "repo_id": pre['repo_id'],
                        "chunks": pre['chunk_count'],
                        "files_processed": pre['node_count'],
                        "preindexed": True
                    })
                    return
            except Exception:
                pass  # Continue with normal upload

            # Step 1: Clone repository
            yield sse_event("clone", {
                "message": "Cloning repository...",
                "progress": 10
            })
            await asyncio.sleep(0)

            user_oauth_token = link.github_token or None
            try:
                repo_content = fetch_repo_content_via_git(repo_url, sub_directory, oauth_token=user_oauth_token)
            except Exception as git_error:
                api_token = link.github_token or auth_token
                repo_content = fetch_repo_content(repo_url, api_token, sub_directory)

            yield sse_event("clone_done", {
                "message": f"Found {len(repo_content)} files",
                "progress": 20,
                "file_count": len(repo_content),
                "sample_files": [f['path'] for f in repo_content[:5]]
            })
            await asyncio.sleep(0)

            # Step 2: Filter content
            yield sse_event("filter", {
                "message": "Filtering dependency directories...",
                "progress": 25
            })
            await asyncio.sleep(0)

            repo_content, filter_metadata = filter_repository_content(
                repo_content, exclude_docs, exclude_examples, exclude_tests
            )

            filtered_count = len(repo_content)
            excluded_dirs = filter_metadata.get('excluded_dirs', [])

            yield sse_event("filter_done", {
                "message": f"Filtered to {filtered_count} files" + (f" (excluded: {', '.join(excluded_dirs)})" if excluded_dirs else ""),
                "progress": 30,
                "filtered_count": filtered_count,
                "excluded_dirs": excluded_dirs
            })
            await asyncio.sleep(0)

            # Step 3: Parse AST
            yield sse_event("parse", {
                "message": "Parsing code structure...",
                "progress": 35
            })
            await asyncio.sleep(0)

            repo_metadata = fetch_repo_metadata(repo_url, auth_token)
            parsed_data = parse_code_to_ast(repo_content)

            yield sse_event("parse_done", {
                "message": f"Parsed {len(parsed_data)} files",
                "progress": 45,
                "parsed_count": len(parsed_data)
            })
            await asyncio.sleep(0)

            # Step 4: Store metadata
            yield sse_event("store", {
                "message": "Storing repository metadata...",
                "progress": 50
            })
            await asyncio.sleep(0)

            repo_id = store_repository_metadata(repo_metadata['full_name'], repo_metadata)
            latest_repo_id = repo_id

            # Step 5: Process chunks
            yield sse_event("chunks", {
                "message": "Processing code chunks...",
                "progress": 55
            })
            await asyncio.sleep(0)

            chunks = process_repository_to_chunks(parsed_data)
            chunk_stats = get_chunk_stats(chunks)

            yield sse_event("chunks_done", {
                "message": f"Generated {chunk_stats['total']} chunks",
                "progress": 65,
                "chunk_count": chunk_stats['total'],
                "by_type": chunk_stats.get('by_type', {})
            })
            await asyncio.sleep(0)

            # Step 6: Store chunks
            yield sse_event("store_chunks", {
                "message": "Storing chunks in database...",
                "progress": 70
            })
            await asyncio.sleep(0)

            store_chunks_batch(repo_id, chunks)

            # Step 7: Create graph
            yield sse_event("graph", {
                "message": "Building dependency graph...",
                "progress": 75
            })
            await asyncio.sleep(0)

            has_method_level_chunks = any(chunk.get('type') == 'method' for chunk in chunks)

            if has_method_level_chunks:
                graph = create_chunk_level_graph(chunks)
            else:
                graph = create_dependency_graph(parsed_data)

            node_count = len(graph.nodes())
            edge_count = len(graph.edges())

            # Get sample nodes for visualization
            sample_nodes = []
            for node_id, node_data in list(graph.nodes(data=True))[:10]:
                sample_nodes.append({
                    "id": str(node_id),
                    "label": node_data.get('label', str(node_id)),
                    "type": node_data.get('type', 'unknown')
                })

            yield sse_event("graph_done", {
                "message": f"Created graph with {node_count} nodes",
                "progress": 80,
                "node_count": node_count,
                "edge_count": edge_count,
                "sample_nodes": sample_nodes
            })
            await asyncio.sleep(0)

            save_graph_as_json(graph, repo_id=repo_id)

            # Step 8: Compute positions for large repos
            POSITION_THRESHOLD = 10000
            MEGA_THRESHOLD = 20000

            if node_count > POSITION_THRESHOLD:
                yield sse_event("positions", {
                    "message": f"Computing layout for {node_count} nodes (this may take 1-2 minutes)...",
                    "progress": 85,
                    "node_count": node_count
                })
                await asyncio.sleep(0)

                try:
                    import networkx as nx
                    from backend.api.graph_generator import store_graph_positions

                    if node_count > MEGA_THRESHOLD:
                        structure_nodes = [
                            n for n, data in graph.nodes(data=True)
                            if data.get('type') in ('directory', 'file')
                        ]
                        G_structure = graph.subgraph(structure_nodes).copy()
                        structure_count = len(G_structure.nodes())

                        iterations = 30 if structure_count > 10000 else 50 if structure_count > 5000 else 100

                        yield sse_event("positions_progress", {
                            "message": f"Computing positions for {structure_count} file nodes...",
                            "progress": 88,
                            "structure_count": structure_count
                        })
                        await asyncio.sleep(0)

                        positions = nx.spring_layout(
                            G_structure,
                            k=2.0 / (structure_count ** 0.5),
                            iterations=iterations,
                            scale=15000,
                            seed=42
                        )
                    else:
                        iterations = 50 if node_count > 15000 else 75
                        positions = nx.spring_layout(
                            graph,
                            k=2.0 / (node_count ** 0.5),
                            iterations=iterations,
                            scale=10000,
                            seed=42
                        )

                    positions_dict = {
                        str(node_id): {'x': float(pos[0]), 'y': float(pos[1])}
                        for node_id, pos in positions.items()
                    }
                    store_graph_positions(repo_id, positions_dict)

                    yield sse_event("positions_done", {
                        "message": f"Saved {len(positions_dict)} positions",
                        "progress": 92,
                        "positions_count": len(positions_dict)
                    })
                    await asyncio.sleep(0)

                except Exception as pos_error:
                    yield sse_event("positions_skipped", {
                        "message": "Position computation skipped (will compute on first load)",
                        "progress": 92
                    })
                    await asyncio.sleep(0)

            # Step 9: Link to user
            if link.user_id:
                yield sse_event("link", {
                    "message": "Linking repository to account...",
                    "progress": 95
                })
                await asyncio.sleep(0)

                try:
                    from backend.api.supabase_client import get_supabase_client
                    supabase = get_supabase_client()

                    existing = supabase.table('user_repos').select('*').eq('user_id', link.user_id).eq('repo_name', repo_metadata['full_name']).execute()

                    if existing.data and len(existing.data) > 0:
                        supabase.table('user_repos').update({
                            'last_accessed': 'now()',
                            'local_repo_id': repo_id
                        }).eq('id', existing.data[0]['id']).execute()
                    else:
                        supabase.table('user_repos').insert({
                            'user_id': link.user_id,
                            'repo_name': repo_metadata['full_name'],
                            'repo_url': repo_url,
                            'is_private': bool(link.github_token),
                            'local_repo_id': repo_id
                        }).execute()
                except Exception:
                    pass

            # Invalidate cache
            from backend.api.data_storage import invalidate_cache_for_repo
            invalidate_cache_for_repo(repo_id)

            # Final done event
            yield sse_event("done", {
                "message": "Repository ready!",
                "progress": 100,
                "repo_id": repo_id,
                "chunks": chunk_stats['total'],
                "files_processed": chunk_stats.get('files_processed', 0),
                "node_count": node_count,
                "edge_count": edge_count
            })

        except Exception as e:
            import traceback
            logging.error(f"Error in upload_repo_stream: {e}")
            logging.error(traceback.format_exc())
            yield sse_event("error", {
                "message": str(e),
                "progress": 0
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/dependency_graph")
async def get_dependency_graph(repo_id: Optional[int] = None):
    """
    Get dependency graph

    Multi-tenant: Requires explicit repo_id parameter for user isolation.

    Args:
        repo_id: Repository ID (required for multi-tenant production)
    """
    try:
        # Multi-tenant: Require explicit repo_id (no global fallback for production safety)
        if not repo_id:
            raise HTTPException(
                status_code=400,
                detail="repo_id parameter is required. Please select a repository first."
            )

        target_repo_id = repo_id

        logging.info(f"📊 Loading graph for repo_id={target_repo_id}")

        # Multi-tenant: Handle missing graph files gracefully (old/corrupted repos)
        try:
            graph = load_graph_from_json(repo_id=target_repo_id)
        except FileNotFoundError:
            logging.warning(f"⚠️ Graph file not found for repo_id={target_repo_id} (may need re-upload)")
            return {
                "nodes": [],
                "edges": [],
                "error": "Graph not available. Please re-upload this repository."
            }

        data = json_graph.node_link_data(graph)
        
        # =====================================================================
        # MEGA-REPO OPTIMIZATION: Load pre-computed positions if available
        # =====================================================================
        # For mega-repos (>10K nodes), positions are pre-computed server-side
        # using ForceAtlas2 with high iterations. This enables instant render.
        # =====================================================================
        precomputed_positions = None
        if target_repo_id:
            positions = load_graph_positions(target_repo_id)
            if positions:
                precomputed_positions = positions
                logging.info(f"📍 Loaded pre-computed positions for {len(positions)} nodes")
                
                # Merge positions into node data
                for node in data["nodes"]:
                    node_id = node["id"]
                    if node_id in positions:
                        node["x"] = positions[node_id]["x"]
                        node["y"] = positions[node_id]["y"]

        # Check for mega-repo using node count from already-loaded graph (no database query)
        # OPTIMIZATION: Use len(data["nodes"]) instead of retrieve_chunks() to avoid
        # expensive paginated queries (153 queries for 152K chunks = timeout).
        # Node count is always >= chunk count, so this is a safe threshold check.
        mega_repo_warning = None
        if target_repo_id:
            node_count = len(data["nodes"])
            
            # Mega-repo threshold: 20,000 nodes (affects <1% of repos)
            # Django: 11.7K works fine
            # PyTorch: 92K is too large
            # Kubernetes: 172K nodes
            if node_count > 20000:
                # Try to get exact chunk_count from preindexed_repos (single fast query)
                chunk_count = node_count  # Default fallback
                try:
                    from backend.api.supabase_client import get_supabase_client
                    supabase = get_supabase_client()
                    result = supabase.table('preindexed_repos')\
                        .select('chunk_count')\
                        .eq('repo_id', target_repo_id)\
                        .limit(1)\
                        .execute()
                    if result.data and len(result.data) > 0:
                        chunk_count = result.data[0]['chunk_count']
                except Exception as e:
                    # If query fails, use node_count (close enough for warning)
                    logging.debug(f"Could not fetch chunk_count from preindexed_repos: {e}")
                
                mega_repo_warning = {
                    'chunk_count': chunk_count,
                    'node_count': node_count,
                    'message': f"This repository is extremely large ({chunk_count:,} chunks, {node_count:,} nodes).",
                    'recommendation': "For better performance, try using the 'subdirectory' field to focus on a specific module.",
                    'example': "For PyTorch: subdirectory='torch' or 'torch/nn'",
                    'has_precomputed_positions': precomputed_positions is not None
                }
                logging.info(f"⚠️ Mega-repo warning for graph page: {chunk_count:,} chunks, {node_count:,} nodes, precomputed={precomputed_positions is not None}")

        return {
            "nodes": data["nodes"],
            "edges": data["links"],
            "mega_repo_warning": mega_repo_warning,
            "has_precomputed_positions": precomputed_positions is not None
        }
    except Exception as e:
        logging.error(f"Error in get_dependency_graph: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/api/query")
async def query_jamba(request: QueryRequest):
    try:
        query = request.query

        # ENTERPRISE FIX: Load chunks from database server-side (eliminates race condition)
        # This approach is:
        # 1. More robust - no dependency on frontend timing
        # 2. Faster - avoids transferring 3MB+ JSON over network
        # 3. More secure - backend controls data source

        # Multi-tenant: Require explicit repo_id (no global fallback for production safety)
        if not request.repo_id:
            raise HTTPException(
                status_code=400,
                detail="repo_id is required. Please select a repository first."
            )

        target_repo_id = request.repo_id

        # Load chunks from database (same pattern as query_stream endpoint)
        chunks = retrieve_chunks(target_repo_id)

        if not chunks:
            raise HTTPException(status_code=400, detail=f"No chunks found for repository. Please re-upload the repository.")

        # Convert to context format expected by langchain_integration
        context = {chunk['chunk_id']: chunk for chunk in chunks}

        logging.info(f"Loaded {len(chunks)} chunks from database for query (server-side)")

        # Get response from Jamba model with caching (Task 2.1)
        # OPTION C: Pass node_context(s) for per-node queries
        # Backwards compat: convert single node_context to array
        node_contexts_array = None
        if request.node_contexts:
            node_contexts_array = request.node_contexts
        elif request.node_context:
            node_contexts_array = [request.node_context]  # Convert single to array

        response = await get_jamba_response(
            query,
            context,
            repo_id=target_repo_id,
            node_contexts=node_contexts_array
        )

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

@app.get("/api/node_code/{chunk_id:path}")
async def get_node_code(chunk_id: str, repo_id: Optional[int] = None):
    """
    Get code for a specific node/chunk
    Returns the actual code content for display in Inspector

    Multi-tenant: Accepts repo_id parameter for user isolation
    """
    try:
        # Multi-tenant: Require explicit repo_id (no global fallback for production safety)
        if not repo_id:
            raise HTTPException(
                status_code=400,
                detail="repo_id parameter is required. Please select a repository first."
            )

        target_repo_id = repo_id
        chunks = retrieve_chunks(target_repo_id)

        # Try exact match first
        chunk = next((c for c in chunks if c['chunk_id'] == chunk_id), None)

        # If no exact match and it's a file/directory, get first chunk from that file
        if not chunk:
            file_chunks = [c for c in chunks if c.get('file_path') == chunk_id or c.get('chunk_id', '').startswith(chunk_id + '::')]
            if file_chunks:
                # Return first class or function from file
                chunk = next((c for c in file_chunks if c.get('type') in ['class_definition', 'function']), file_chunks[0])

        if chunk and chunk.get('code'):
            return {"code": chunk['code']}  # Full code, no limit
        else:
            return {"code": None}

    except Exception as e:
        logging.error(f"Error fetching node code: {e}")
        return {"code": None}

@app.post("/api/explain_node")
async def explain_node(request: dict):
    """
    Fast explanation endpoint using Claude Haiku for <2s latency

    Returns a concise 2-3 sentence explanation of a code chunk.
    Optimized for speed over comprehensiveness.

    Multi-tenant: Accepts repo_id in request for user isolation
    """
    try:
        chunk_id = request.get('chunk_id')
        name = request.get('name', 'this code')
        chunk_type = request.get('type', 'code')
        repo_id = request.get('repo_id')

        # Multi-tenant: Require explicit repo_id (no global fallback for production safety)
        if not repo_id:
            raise HTTPException(
                status_code=400,
                detail="repo_id is required. Please select a repository first."
            )

        target_repo_id = repo_id

        # Get chunk from database
        chunks = retrieve_chunks(target_repo_id)
        chunk = next((c for c in chunks if c['chunk_id'] == chunk_id), None)

        if not chunk:
            # Fallback: use name for generic explanation
            code_snippet = f"Code entity: {name} ({chunk_type})"
        else:
            # Truncate code for faster processing
            code_snippet = chunk['code'][:800]  # Max 800 chars for speed

        # Use Haiku for fast response
        from anthropic import Anthropic
        anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        prompt = f"""Explain what this {chunk_type} does in 2-3 concise sentences:

{code_snippet}

Be technical but clear. Focus on purpose and key functionality."""

        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",  # Fast model
            max_tokens=150,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )

        explanation = response.content[0].text

        logging.info(f"✅ Quick explain for {name}: {len(explanation)} chars")

        return {"explanation": explanation}

    except Exception as e:
        logging.error(f"Explain error: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

@app.get("/api/query_stream")
async def query_stream(query: str, repo_id: Optional[int] = None):
    """
    Task 2.3: Streaming endpoint for real-time Claude responses

    Uses Server-Sent Events (SSE) to stream tokens as they're generated.
    Perceived latency: ~1s to first token (vs 19s for batch).

    Args:
        query: User query (URL parameter)
        repo_id: Repository ID for multi-tenant isolation

    Returns:
        StreamingResponse with SSE events
    """
    try:
        from backend.api.langchain_integration import get_jamba_response_stream

        # Multi-tenant: Require explicit repo_id (no global fallback for production safety)
        if not repo_id:
            raise HTTPException(
                status_code=400,
                detail="repo_id parameter is required. Please select a repository first."
            )

        target_repo_id = repo_id

        # Get chunks from database
        chunks = retrieve_chunks(target_repo_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="No chunks found for repository.")

        # Convert to context format
        context = {chunk['chunk_id']: chunk for chunk in chunks}

        # Stream response
        async def event_generator():
            try:
                async for token in get_jamba_response_stream(query, context, repo_id=target_repo_id):
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

@app.post("/api/save_graph_positions")
async def save_graph_positions_endpoint(request: dict):
    """
    Save pre-computed graph positions from frontend
    
    After vis-network completes ForceAtlas2 stabilization, the frontend
    saves the beautiful positions here. Future loads use these positions
    for instant rendering with identical aesthetics.
    
    Args:
        request: {repo_id: int, positions: {node_id: {x, y}, ...}}
    """
    try:
        repo_id = request.get('repo_id')
        positions = request.get('positions')
        
        if not repo_id or not positions:
            raise HTTPException(status_code=400, detail="repo_id and positions required")
        
        logging.info(f"💾 Saving {len(positions)} graph positions for repo_id={repo_id}")
        
        # Import and save
        from backend.api.graph_generator import store_graph_positions
        success = store_graph_positions(repo_id, positions)
        
        if success:
            logging.info(f"✅ Graph positions saved for repo_id={repo_id}")
            
            # Also update preindexed_repos if this is a pre-indexed repo
            try:
                from backend.api.supabase_client import get_supabase_client
                supabase = get_supabase_client()
                supabase.table('preindexed_repos')\
                    .update({'has_positions': True})\
                    .eq('repo_id', repo_id)\
                    .execute()
                logging.info(f"   Updated preindexed_repos.has_positions=True")
            except Exception as e:
                logging.debug(f"   Not a preindexed repo or update failed: {e}")
            
            return {"success": True, "positions_saved": len(positions)}
        else:
            raise HTTPException(status_code=500, detail="Failed to save positions")
            
    except Exception as e:
        logging.error(f"Error saving graph positions: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {e}")


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

# Include the auth router
from backend.api.auth import router as auth_router
app.include_router(auth_router, prefix="/api")

# Include the repos router
from backend.api.repos import router as repos_router
app.include_router(repos_router, prefix="/api")

# Include the sessions router
from backend.api.sessions import router as sessions_router
app.include_router(sessions_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
