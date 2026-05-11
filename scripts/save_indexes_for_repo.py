#!/usr/bin/env python3
"""
Save BM25/PageRank indexes for a repository already in the database.

This script is for repos that were uploaded before the Storage-based saving
was implemented (e.g., Kubernetes repo_id=13).

Usage:
    python scripts/save_indexes_for_repo.py --repo-id 13

Time estimate:
    - Small repos (<10K chunks): 10-30 seconds
    - Medium repos (10K-50K chunks): 30-90 seconds
    - Mega repos (>50K chunks): 1-3 minutes

What it does:
    1. Loads chunks from Supabase (uses cache if available)
    2. Builds chunk dependency graph
    3. Builds BM25 index (tokenizes all chunks)
    4. Computes PageRank scores
    5. Saves BM25/PageRank to Supabase Storage (gzipped)
    6. Updates preindexed_repos table

Date: December 2025
"""




import os
import sys
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


def save_indexes_for_repo(repo_id: int, force: bool = False) -> bool:
    """
    Compute and save BM25/PageRank indexes for an existing repository.

    Args:
        repo_id: Repository ID in Supabase
        force: If True, rebuild even if indexes already exist

    Returns:
        True if successful, False otherwise
    """
    from backend.api.data_storage import retrieve_chunks
    from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph

    start_time = time.time()

    logging.info(f"{'='*60}")
    logging.info(f"SAVING INDEXES FOR REPO_ID={repo_id}")
    logging.info(f"{'='*60}")

    # Check if indexes already exist
    if not force and HybridRetriever.indexes_exist_in_storage(repo_id):
        logging.info(f"✅ Indexes already exist in Storage for repo_id={repo_id}")
        logging.info(f"   Use --force to rebuild anyway")
        return True

    # Step 1: Load chunks
    logging.info("📥 Step 1/4: Loading chunks from Supabase...")
    step_start = time.time()
    chunks = retrieve_chunks(repo_id)

    if not chunks:
        logging.error("❌ No chunks found for this repo_id!")
        return False

    logging.info(f"   ✅ Loaded {len(chunks):,} chunks in {time.time() - step_start:.1f}s")

    # Step 2: Build chunk graph
    logging.info("🔗 Step 2/4: Building chunk dependency graph...")
    step_start = time.time()
    chunk_graph = build_chunk_graph(chunks)
    logging.info(f"   ✅ Built graph: {len(chunk_graph.nodes()):,} nodes, {len(chunk_graph.edges()):,} edges in {time.time() - step_start:.1f}s")

    # Step 3: Build BM25 and PageRank
    logging.info("📊 Step 3/4: Building BM25 + computing PageRank...")
    logging.info("   (This takes 1-3 minutes for mega-repos with 100K+ chunks)")

    step_start = time.time()
    hybrid_retriever = HybridRetriever(
        chunks=chunks,
        vector_store=None,  # Not needed for saving BM25/PageRank
        chunk_graph=chunk_graph,
        repo_id=repo_id,
        use_cached_indexes=False  # Force rebuild
    )
    build_time = time.time() - step_start

    logging.info(f"   ✅ BM25: {len(hybrid_retriever.chunk_ids):,} documents")
    logging.info(f"   ✅ PageRank: {len(hybrid_retriever.pagerank_scores):,} nodes")
    logging.info(f"   ✅ Build time: {build_time:.1f}s")

    # Step 4: Save to Supabase Storage
    logging.info("💾 Step 4/4: Saving to Supabase Storage...")
    step_start = time.time()
    success = hybrid_retriever.save_indexes(repo_id)
    save_time = time.time() - step_start

    if success:
        total_time = time.time() - start_time
        logging.info(f"{'='*60}")
        logging.info(f"✅ SUCCESS: Saved indexes for repo_id={repo_id}")
        logging.info(f"   Total time: {total_time:.1f}s")
        logging.info(f"   - Chunks: {len(chunks):,}")
        logging.info(f"   - Graph nodes: {len(chunk_graph.nodes()):,}")
        logging.info(f"   - BM25 docs: {len(hybrid_retriever.chunk_ids):,}")
        logging.info(f"   - PageRank nodes: {len(hybrid_retriever.pagerank_scores):,}")
        logging.info(f"{'='*60}")

        # Update preindexed_repos table if it exists
        try:
            from backend.api.supabase_client import get_supabase_client
            supabase = get_supabase_client()
            supabase.table('preindexed_repos').update({
                'has_bm25_index': True,
                'has_pagerank': True
            }).eq('repo_id', repo_id).execute()
            logging.info("   ✅ Updated preindexed_repos table")
        except Exception as e:
            logging.debug(f"   (preindexed_repos update skipped: {e})")

        return True
    else:
        logging.error("❌ FAILED to save indexes")
        return False


def list_repos_needing_indexes():
    """List all preindexed repos that don't have BM25/PageRank in Storage."""
    from backend.api.supabase_client import get_supabase_client
    from backend.api.hybrid_retrieval import HybridRetriever

    logging.info("📋 Checking preindexed repos for missing indexes...")
    logging.info("=" * 60)

    try:
        supabase = get_supabase_client()

        # Get all preindexed repos
        result = supabase.table('preindexed_repos')\
            .select('repo_id, repo_name, chunk_count, has_bm25_index, has_pagerank')\
            .execute()

        if not result.data:
            logging.info("   No preindexed repos found")
            return []

        missing = []
        for repo in result.data:
            repo_id = repo['repo_id']
            has_indexes = HybridRetriever.indexes_exist_in_storage(repo_id)

            if not has_indexes:
                missing.append(repo)
                logging.info(f"   ❌ repo_id={repo_id}: {repo['repo_name']} ({repo['chunk_count']:,} chunks)")
            else:
                logging.info(f"   ✅ repo_id={repo_id}: {repo['repo_name']} - indexes exist")

        logging.info("=" * 60)
        if missing:
            logging.info(f"Total: {len(missing)} repos need indexes")
        else:
            logging.info("All preindexed repos have indexes in Storage!")

        return missing

    except Exception as e:
        logging.error(f"❌ Error listing repos: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(
        description='Save BM25/PageRank indexes for an existing repository',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Save indexes for Kubernetes (repo_id=13)
    python scripts/save_indexes_for_repo.py --repo-id 13

    # Force rebuild even if indexes exist
    python scripts/save_indexes_for_repo.py --repo-id 13 --force

    # List repos that need indexes
    python scripts/save_indexes_for_repo.py --list

    # Save indexes for all repos that need them
    python scripts/save_indexes_for_repo.py --all
        """
    )
    parser.add_argument(
        '--repo-id',
        type=int,
        help='Repository ID (e.g., 13 for Kubernetes)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Rebuild indexes even if they already exist'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List repos that need indexes'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Save indexes for all repos that need them'
    )
    args = parser.parse_args()

    if args.list:
        list_repos_needing_indexes()
        return

    if args.all:
        missing = list_repos_needing_indexes()
        if not missing:
            logging.info("Nothing to do!")
            return

        results = {}
        for repo in missing:
            success = save_indexes_for_repo(repo['repo_id'])
            results[repo['repo_name']] = success

        # Summary
        logging.info("\n" + "=" * 60)
        logging.info("SUMMARY")
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
        return

    if args.repo_id:
        success = save_indexes_for_repo(args.repo_id, force=args.force)
        sys.exit(0 if success else 1)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == '__main__':
    main()
