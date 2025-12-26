#!/usr/bin/env python3
"""
Pre-Index Mega-Repos Script

This script pre-indexes the top 20 largest open-source repositories
for instant loading when users upload them.

Pre-computed artifacts:
1. Code chunks (stored in Supabase)
2. FAISS vector index (stored on disk)
3. BM25 index (stored on disk)
4. PageRank scores (stored on disk)
5. ForceAtlas2 graph positions (stored in Supabase)
6. Hierarchical summaries (stored in Supabase)

Usage:
    python scripts/preindex_mega_repos.py [--repo REPO_NAME]

Examples:
    # Pre-index all mega-repos
    python scripts/preindex_mega_repos.py

    # Pre-index a specific repo
    python scripts/preindex_mega_repos.py --repo kubernetes/kubernetes

Date: December 2025
Status: Production-ready
"""

import os
import sys
import asyncio
import argparse
import logging
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Top 20 mega-repos to pre-index
# These are the largest, most popular open-source codebases
MEGA_REPOS = [
    # Major frameworks
    "kubernetes/kubernetes",
    "tensorflow/tensorflow",
    "pytorch/pytorch",
    "microsoft/vscode",
    "facebook/react",
    
    # Languages and runtimes
    "golang/go",
    "rust-lang/rust",
    "nodejs/node",
    "python/cpython",
    
    # Infrastructure
    "apache/spark",
    "elastic/elasticsearch",
    "grafana/grafana",
    "prometheus/prometheus",
    "moby/moby",
    "hashicorp/terraform",
    
    # Web frameworks
    "django/django",
    "pallets/flask",
    "fastapi/fastapi",
    "rails/rails",
    
    # Tools
    "ansible/ansible",
]


async def preindex_repo(repo_name: str, subdirectory: str = None):
    """
    Pre-index a single repository with all artifacts.
    
    Args:
        repo_name: GitHub repo name (e.g., 'kubernetes/kubernetes')
        subdirectory: Optional subdirectory to focus on (e.g., 'pkg' for kubernetes)
    """
    from backend.api.github_api import fetch_repo_content_via_git
    from backend.api.ast_parser import parse_code_to_ast
    from backend.api.chunk_processor import process_repository_to_chunks
    from backend.api.data_storage import store_repository_metadata, store_chunks_batch, FAISS_DIR
    from backend.api.graph_generator import (
        create_chunk_level_graph, 
        save_graph_as_json
    )
    from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph
    from backend.api.summarization import generate_hierarchical_summaries, store_summaries
    from backend.api.supabase_client import get_supabase_client
    from anthropic import Anthropic
    
    start_time = time.time()
    
    logging.info(f"🚀 PRE-INDEXING: {repo_name}")
    logging.info("=" * 60)
    
    try:
        # 1. Fetch repository content
        logging.info("📥 Step 1/7: Fetching repository content...")
        repo_url = f"https://github.com/{repo_name}"
        repo_content = fetch_repo_content_via_git(repo_url, subdirectory)
        logging.info(f"   Fetched {len(repo_content)} files")
        
        # 2. Parse to AST
        logging.info("🔍 Step 2/7: Parsing code to AST...")
        parsed_data = parse_code_to_ast(repo_content)
        logging.info(f"   Parsed {len(parsed_data)} files")
        
        # 3. Process into chunks
        logging.info("📦 Step 3/7: Processing into chunks...")
        chunks = process_repository_to_chunks(parsed_data)
        logging.info(f"   Generated {len(chunks)} chunks")
        
        # 4. Store in Supabase
        logging.info("💾 Step 4/7: Storing in Supabase...")
        repo_id = store_repository_metadata(repo_name, {
            'full_name': repo_name,
            'preindexed': True,
            'chunk_count': len(chunks)
        })
        store_chunks_batch(repo_id, chunks)
        logging.info(f"   Stored with repo_id={repo_id}")
        
        # 5. Build and save indexes
        logging.info("📊 Step 5/7: Building search indexes...")
        
        # Build chunk graph
        chunk_graph = build_chunk_graph(chunks)
        
        # Initialize vector store (FAISS)
        from langchain_openai import OpenAIEmbeddings
        from langchain_community.vectorstores import FAISS
        from langchain_core.documents import Document
        
        embeddings = OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-3-small"
        )
        
        documents = []
        for chunk in chunks:
            content = f"File: {chunk['file_path']}\nType: {chunk['type']}\nName: {chunk['name']}\n\n{chunk['code']}"
            metadata = {
                "chunk_id": chunk['chunk_id'],
                "source": chunk['file_path'],
                "type": chunk['type'],
                "name": chunk['name']
            }
            documents.append(Document(page_content=content, metadata=metadata))
        
        # Build FAISS in batches
        BATCH_SIZE = 500
        vector_store = None
        for i in range(0, len(documents), BATCH_SIZE):
            batch = documents[i:i + BATCH_SIZE]
            if vector_store is None:
                vector_store = await FAISS.afrom_documents(batch, embeddings)
            else:
                batch_store = await FAISS.afrom_documents(batch, embeddings)
                vector_store.merge_from(batch_store)
            logging.info(f"   FAISS: {min(i + BATCH_SIZE, len(documents))}/{len(documents)} documents")
        
        # Save FAISS
        os.makedirs(FAISS_DIR, exist_ok=True)
        faiss_path = f"{FAISS_DIR}/{repo_id}"
        vector_store.save_local(faiss_path)
        logging.info(f"   Saved FAISS index to {faiss_path}")
        
        # Initialize hybrid retriever and save indexes
        hybrid_retriever = HybridRetriever(
            chunks=chunks,
            vector_store=vector_store,
            chunk_graph=chunk_graph,
            repo_id=repo_id,
            use_cached_indexes=False  # Force build
        )
        hybrid_retriever.save_indexes(repo_id)
        logging.info(f"   Saved BM25 and PageRank indexes")
        
        # 6. Create graph (positions saved by frontend after you load it)
        logging.info("🎨 Step 6/7: Creating graph structure...")
        graph = create_chunk_level_graph(chunks)
        save_graph_as_json(graph, repo_id=repo_id)
        
        logging.info(f"   Graph created with {len(graph.nodes())} nodes")
        logging.info(f"   ⚠️ IMPORTANT: Load this repo in frontend to save ForceAtlas2 positions!")
        logging.info(f"   After vis-network stabilizes, positions will be auto-saved.")
        
        # 7. Generate hierarchical summaries
        logging.info("📝 Step 7/7: Generating hierarchical summaries...")
        anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        summaries = await generate_hierarchical_summaries(
            chunks=chunks,
            repo_id=repo_id,
            repo_name=repo_name,
            anthropic_client=anthropic_client
        )
        store_summaries(repo_id, summaries)
        logging.info(f"   Generated {summaries['stats']['total_files']} file summaries, {summaries['stats']['total_packages']} package summaries")
        
        # Register as pre-indexed
        # Note: has_positions=False until you load in frontend
        supabase = get_supabase_client()
        supabase.table('preindexed_repos').upsert({
            'repo_name': repo_name,
            'repo_id': repo_id,
            'chunk_count': len(chunks),
            'node_count': len(graph.nodes()),
            'has_summaries': True,
            'has_positions': False,  # Set to True after frontend saves positions
            'has_bm25_index': True,
            'has_pagerank': True,
            'has_faiss_index': True,
            'processing_time_seconds': int(time.time() - start_time)
        }, on_conflict='repo_name').execute()
        
        elapsed = time.time() - start_time
        logging.info(f"✅ PRE-INDEXING COMPLETE: {repo_name}")
        logging.info(f"   Chunks: {len(chunks)}")
        logging.info(f"   Nodes: {len(graph.nodes())}")
        logging.info(f"   Time: {elapsed:.1f}s")
        logging.info("=" * 60)
        
        return True
        
    except Exception as e:
        logging.error(f"❌ PRE-INDEXING FAILED: {repo_name}")
        logging.error(f"   Error: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False


async def main():
    parser = argparse.ArgumentParser(description='Pre-index mega-repos for instant loading')
    parser.add_argument('--repo', type=str, help='Specific repo to index (e.g., kubernetes/kubernetes)')
    parser.add_argument('--all', action='store_true', help='Index all mega-repos')
    args = parser.parse_args()
    
    if args.repo:
        # Index specific repo
        success = await preindex_repo(args.repo)
        sys.exit(0 if success else 1)
    elif args.all:
        # Index all mega-repos
        results = {}
        for repo in MEGA_REPOS:
            success = await preindex_repo(repo)
            results[repo] = success
        
        # Summary
        logging.info("\n" + "=" * 60)
        logging.info("PRE-INDEXING SUMMARY")
        logging.info("=" * 60)
        
        succeeded = [r for r, s in results.items() if s]
        failed = [r for r, s in results.items() if not s]
        
        logging.info(f"✅ Succeeded: {len(succeeded)}/{len(results)}")
        for repo in succeeded:
            logging.info(f"   - {repo}")
        
        if failed:
            logging.info(f"❌ Failed: {len(failed)}/{len(results)}")
            for repo in failed:
                logging.info(f"   - {repo}")
        
        sys.exit(0 if not failed else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())

