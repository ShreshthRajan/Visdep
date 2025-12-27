#!/usr/bin/env python3
"""
Resume Pre-Indexing Script

Resumes pre-indexing from Step 5 (building indexes) for a repo that already
has chunks stored in Supabase.

Usage:
    python scripts/resume_preindex.py --repo-id 13
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


async def resume_from_step5(repo_id: int):
    """
    Resume pre-indexing from Step 5 for a repo with existing chunks.
    
    Args:
        repo_id: Repository ID that already has chunks stored
    """
    from backend.api.data_storage import FAISS_DIR, retrieve_chunks
    from backend.api.graph_generator import create_chunk_level_graph, save_graph_as_json
    from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph
    from backend.api.summarization import generate_hierarchical_summaries, store_summaries
    from backend.api.supabase_client import get_supabase_client
    from anthropic import Anthropic
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    
    start_time = time.time()
    
    logging.info(f"🔄 RESUMING PRE-INDEXING: repo_id={repo_id}")
    logging.info("=" * 60)
    
    try:
        # Load chunks from Supabase
        logging.info("📥 Loading chunks from Supabase...")
        chunks = retrieve_chunks(repo_id)
        logging.info(f"   ✅ Loaded {len(chunks):,} chunks")
        
        if len(chunks) == 0:
            logging.error(f"❌ No chunks found for repo_id={repo_id}")
            return False
        
        # Get repo name from Supabase
        supabase = get_supabase_client()
        repo_result = supabase.table('repositories').select('repo_name').eq('id', repo_id).single().execute()
        repo_name = repo_result.data['repo_name'] if repo_result.data else f"repo_{repo_id}"
        
        logging.info(f"   Repo: {repo_name}")
        
        # 5. Build and save indexes
        logging.info("📊 Step 5/7: Building search indexes...")
        logging.info(f"   Processing {len(chunks):,} chunks (this may take 1-3 hours for mega-repos)")
        
        # Build chunk graph
        logging.info("   Building chunk dependency graph...")
        chunk_graph = build_chunk_graph(chunks)
        logging.info(f"   ✅ Graph built: {len(chunk_graph.nodes())} nodes, {len(chunk_graph.edges())} edges")
        
        # Initialize vector store (FAISS)
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
        hybrid_retriever.save_indexes(repo_id)
        logging.info("   ✅ Saved BM25 and PageRank indexes")
        
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
        logging.info(f"✅ RESUME COMPLETE: repo_id={repo_id}")
        logging.info(f"   Chunks: {len(chunks):,}")
        logging.info(f"   Nodes: {len(graph.nodes()):,}")
        logging.info(f"   Time: {elapsed:.1f}s")
        logging.info("=" * 60)
        
        return True
        
    except Exception as e:
        logging.error(f"❌ RESUME FAILED: repo_id={repo_id}")
        logging.error(f"   Error: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False


async def main():
    parser = argparse.ArgumentParser(description='Resume pre-indexing from Step 5')
    parser.add_argument('--repo-id', type=int, required=True, help='Repository ID to resume')
    args = parser.parse_args()
    
    success = await resume_from_step5(args.repo_id)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())

