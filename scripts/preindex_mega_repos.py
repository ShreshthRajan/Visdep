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

# Top 8 mega-repos to pre-index (Option A: Prioritized list)
# These are the largest, most popular open-source codebases
MEGA_REPOS = [
    # Major frameworks
    "tensorflow/tensorflow",
    "pytorch/pytorch",
    "facebook/react",
    "microsoft/vscode",
    
    # Web frameworks
    "django/django",
    "fastapi/fastapi",
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
        logging.info("📥 Step 1/8: Fetching repository content...")
        repo_url = f"https://github.com/{repo_name}"
        repo_content = fetch_repo_content_via_git(repo_url, subdirectory)
        logging.info(f"   Fetched {len(repo_content)} files")
        
        # 2. Parse to AST
        logging.info("🔍 Step 2/8: Parsing code to AST...")
        parsed_data = parse_code_to_ast(repo_content)
        logging.info(f"   Parsed {len(parsed_data)} files")
        
        # 3. Process into chunks
        logging.info("📦 Step 3/8: Processing into chunks...")
        chunks = process_repository_to_chunks(parsed_data)
        logging.info(f"   Generated {len(chunks)} chunks")
        
        # 4. Store in Supabase
        logging.info("💾 Step 4/8: Storing in Supabase...")
        repo_id = store_repository_metadata(repo_name, {
            'full_name': repo_name,
            'preindexed': True,
            'chunk_count': len(chunks)
        })
        store_chunks_batch(repo_id, chunks)
        logging.info(f"   Stored with repo_id={repo_id}")
        
        # 5. Build and save indexes
        logging.info("📊 Step 5/8: Building search indexes...")
        logging.info(f"   Processing {len(chunks):,} chunks (this may take 1-3 hours for mega-repos)")
        
        # Build chunk graph
        logging.info("   Building chunk dependency graph...")
        chunk_graph = build_chunk_graph(chunks)
        logging.info(f"   ✅ Graph built: {len(chunk_graph.nodes())} nodes, {len(chunk_graph.edges())} edges")
        
        # Initialize vector store (FAISS)
        from langchain_openai import OpenAIEmbeddings
        from langchain_community.vectorstores import FAISS
        from langchain_core.documents import Document
        
        logging.info("   Initializing OpenAI embeddings...")
        embeddings = OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-3-small"
        )
        
        # Create documents (can be slow for large repos)
        logging.info("   Creating document objects...")
        documents = []
        for i, chunk in enumerate(chunks):
            content = f"File: {chunk['file_path']}\nType: {chunk['type']}\nName: {chunk['name']}\n\n{chunk['code']}"
            metadata = {
                "chunk_id": chunk['chunk_id'],
                "source": chunk['file_path'],
                "type": chunk['type'],
                "name": chunk['name']
            }
            documents.append(Document(page_content=content, metadata=metadata))
            
            # Log progress every 10K chunks
            if (i + 1) % 10000 == 0:
                logging.info(f"   Documents: {i + 1:,}/{len(chunks):,} created")
        
        logging.info(f"   ✅ Created {len(documents):,} documents")
        
        # Build FAISS in batches
        logging.info("   Building FAISS vector index (this is the slowest step)...")
        BATCH_SIZE = 500
        vector_store = None
        total_batches = (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(documents), BATCH_SIZE):
            batch = documents[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            
            if vector_store is None:
                logging.info(f"   FAISS batch {batch_num}/{total_batches}: Creating initial index...")
                vector_store = await FAISS.afrom_documents(batch, embeddings)
            else:
                logging.info(f"   FAISS batch {batch_num}/{total_batches}: Merging...")
                batch_store = await FAISS.afrom_documents(batch, embeddings)
                vector_store.merge_from(batch_store)
            
            # Log progress every 10 batches or at completion
            if batch_num % 10 == 0 or batch_num == total_batches:
                logging.info(f"   FAISS progress: {min(i + BATCH_SIZE, len(documents)):,}/{len(documents):,} documents ({batch_num}/{total_batches} batches)")
        
        logging.info(f"   ✅ FAISS index built with {len(documents):,} vectors")
        
        # Save FAISS
        logging.info("   Saving FAISS index to disk...")
        os.makedirs(FAISS_DIR, exist_ok=True)
        faiss_path = f"{FAISS_DIR}/{repo_id}"
        vector_store.save_local(faiss_path)
        logging.info(f"   ✅ Saved FAISS index to {faiss_path}")
        
        # Initialize hybrid retriever and save indexes
        logging.info("   Building BM25 index...")
        hybrid_retriever = HybridRetriever(
            chunks=chunks,
            vector_store=vector_store,
            chunk_graph=chunk_graph,
            repo_id=repo_id,
            use_cached_indexes=False  # Force build
        )
        
        logging.info("   Computing PageRank scores (this may take 10-30 min for mega-repos)...")
        hybrid_retriever.save_indexes(repo_id, vector_store=vector_store)
        logging.info("   ✅ Saved BM25, PageRank, and FAISS indexes")
        
        # 6. Create graph structure
        logging.info("🎨 Step 6/8: Creating graph structure...")
        graph = create_chunk_level_graph(chunks)
        save_graph_as_json(graph, repo_id=repo_id)
        
        logging.info(f"   Graph created with {len(graph.nodes())} nodes")
        
        # 7. Generate hierarchical summaries
        logging.info("📝 Step 7/8: Generating hierarchical summaries...")
        anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        summaries = await generate_hierarchical_summaries(
            chunks=chunks,
            repo_id=repo_id,
            repo_name=repo_name,
            anthropic_client=anthropic_client
        )
        store_summaries(repo_id, summaries)
        logging.info(f"   Generated {summaries['stats']['total_files']} file summaries, {summaries['stats']['total_packages']} package summaries")
        
        # 8. Compute graph positions server-side (replaces flaky headless browser)
        logging.info("📍 Step 8/8: Computing graph positions server-side...")
        from backend.api.graph_generator import store_graph_positions
        import networkx as nx

        node_count = len(graph.nodes())
        positions_success = False

        try:
            MEGA_THRESHOLD = 20000

            if node_count > MEGA_THRESHOLD:
                # Very large: compute for file structure only
                logging.info(f"   MEGA-REPO: {node_count:,} nodes - computing file structure positions...")

                structure_nodes = [
                    n for n, data in graph.nodes(data=True)
                    if data.get('type') in ('directory', 'file')
                ]
                G_structure = graph.subgraph(structure_nodes).copy()
                structure_count = len(G_structure.nodes())
                logging.info(f"   Reduced: {node_count:,} → {structure_count:,} nodes")

                # Adaptive iterations for latency optimization
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
                # Medium: full spring layout
                iterations = 50 if node_count > 15000 else 75 if node_count > 10000 else 100
                logging.info(f"   Computing full layout for {node_count:,} nodes ({iterations} iterations)...")
                positions = nx.spring_layout(
                    graph,
                    k=2.0 / (node_count ** 0.5),
                    iterations=iterations,
                    scale=10000,
                    seed=42
                )

            # Save positions
            positions_dict = {
                str(node_id): {'x': float(pos[0]), 'y': float(pos[1])}
                for node_id, pos in positions.items()
            }
            store_graph_positions(repo_id, positions_dict)
            logging.info(f"   ✅ Saved {len(positions_dict):,} positions")
            positions_success = True

        except Exception as pos_error:
            logging.warning(f"   ⚠️ Position computation failed: {pos_error}")

        # Register as pre-indexed
        supabase = get_supabase_client()
        supabase.table('preindexed_repos').upsert({
            'repo_name': repo_name,
            'repo_id': repo_id,
            'chunk_count': len(chunks),
            'node_count': len(graph.nodes()),
            'has_summaries': True,
            'has_positions': positions_success,
            'has_bm25_index': True,
            'has_pagerank': True,
            'has_faiss_index': True,
            'processing_time_seconds': int(time.time() - start_time)
        }, on_conflict='repo_name').execute()

        if positions_success:
            logging.info("✅ Graph positions computed and saved")
        else:
            logging.warning("⚠️ Positions not saved - graph will use LOD fallback")
        
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

