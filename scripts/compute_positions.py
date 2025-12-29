#!/usr/bin/env python3
"""
Compute Graph Positions for Mega-Repos

This script computes ForceAtlas2-style positions for large repositories
that are already in the database but don't have pre-computed positions.

Usage:
    # Compute positions for Kubernetes (repo_id=13)
    python scripts/compute_positions.py --repo-id 13

    # Compute positions for all repos without positions
    python scripts/compute_positions.py --all

    # List repos that need positions
    python scripts/compute_positions.py --list

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


def compute_positions_for_repo(repo_id: int, node_count: int = None) -> bool:
    """
    Compute and save graph positions for a repository.

    Uses networkx spring_layout with Barnes-Hut optimization for O(n log n) performance.
    For very large graphs (>50K nodes), uses chunked computation.

    Args:
        repo_id: Repository ID in Supabase
        node_count: Optional node count for progress estimation

    Returns:
        True if positions were computed and saved successfully
    """
    import networkx as nx
    from backend.api.graph_generator import load_graph_from_json, store_graph_positions

    start_time = time.time()

    logging.info(f"🚀 Computing positions for repo_id={repo_id}")
    logging.info("=" * 60)

    try:
        # Step 1: Load graph from Supabase
        logging.info("📥 Step 1/3: Loading graph from Supabase...")
        G = load_graph_from_json(repo_id=repo_id)

        actual_node_count = len(G.nodes())
        actual_edge_count = len(G.edges())
        logging.info(f"   Loaded: {actual_node_count:,} nodes, {actual_edge_count:,} edges")

        if actual_node_count == 0:
            logging.error("❌ Graph has no nodes!")
            return False

        # Step 2: Compute positions using spring layout
        logging.info("📊 Step 2/3: Computing positions...")

        # Choose algorithm based on size
        if actual_node_count < 5000:
            # Small graph: Use Kamada-Kawai (higher quality, O(n²))
            logging.info("   Using Kamada-Kawai layout (high quality)")
            positions = nx.kamada_kawai_layout(G, scale=5000)
        elif actual_node_count < 50000:
            # Medium graph: Use spring layout with more iterations
            logging.info("   Using spring layout with 100 iterations")
            positions = nx.spring_layout(
                G,
                k=2.0 / (actual_node_count ** 0.5),  # Optimal spacing
                iterations=100,
                scale=10000,
                seed=42  # Reproducible
            )
        else:
            # Large graph: Use spring layout with fewer iterations
            logging.info("   Using spring layout with 50 iterations (large graph optimization)")
            positions = nx.spring_layout(
                G,
                k=3.0 / (actual_node_count ** 0.5),  # More spacing for large graphs
                iterations=50,
                scale=20000,
                seed=42
            )

        logging.info(f"   ✅ Computed {len(positions):,} positions")

        # Step 3: Convert and save positions
        logging.info("💾 Step 3/3: Saving positions to Supabase...")

        # Convert numpy arrays to plain floats for JSON serialization
        positions_dict = {}
        for node_id, pos in positions.items():
            positions_dict[str(node_id)] = {
                'x': float(pos[0]),
                'y': float(pos[1])
            }

        success = store_graph_positions(repo_id, positions_dict)

        if success:
            elapsed = time.time() - start_time
            logging.info(f"✅ COMPLETE: repo_id={repo_id}")
            logging.info(f"   Nodes: {actual_node_count:,}")
            logging.info(f"   Time: {elapsed:.1f}s")
            logging.info("=" * 60)

            # Update preindexed_repos table if this is a pre-indexed repo
            try:
                from backend.api.supabase_client import get_supabase_client
                supabase = get_supabase_client()
                supabase.table('preindexed_repos')\
                    .update({'has_positions': True})\
                    .eq('repo_id', repo_id)\
                    .execute()
                logging.info("   Updated preindexed_repos.has_positions=True")
            except Exception as e:
                logging.debug(f"   (Not a preindexed repo or update skipped: {e})")

            return True
        else:
            logging.error("❌ Failed to save positions")
            return False

    except Exception as e:
        logging.error(f"❌ Error computing positions: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False


def list_repos_without_positions():
    """List all preindexed repos that don't have positions computed."""
    from backend.api.supabase_client import get_supabase_client

    logging.info("📋 Repos without pre-computed positions:")
    logging.info("=" * 60)

    try:
        supabase = get_supabase_client()

        # Get preindexed repos without positions
        result = supabase.table('preindexed_repos')\
            .select('repo_id, repo_name, node_count, chunk_count, has_positions')\
            .eq('has_positions', False)\
            .execute()

        if not result.data:
            logging.info("   All preindexed repos have positions! ✅")
            return []

        repos = []
        for repo in result.data:
            repos.append(repo)
            logging.info(f"   repo_id={repo['repo_id']}: {repo['repo_name']}")
            logging.info(f"      Nodes: {repo['node_count']:,}, Chunks: {repo['chunk_count']:,}")

        logging.info("=" * 60)
        logging.info(f"Total: {len(repos)} repos need positions")

        return repos

    except Exception as e:
        logging.error(f"❌ Error listing repos: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description='Compute graph positions for mega-repos')
    parser.add_argument('--repo-id', type=int, help='Specific repo_id to compute positions for')
    parser.add_argument('--all', action='store_true', help='Compute positions for all repos without positions')
    parser.add_argument('--list', action='store_true', help='List repos that need positions')
    args = parser.parse_args()

    if args.list:
        list_repos_without_positions()
        return

    if args.repo_id:
        success = compute_positions_for_repo(args.repo_id)
        sys.exit(0 if success else 1)

    if args.all:
        repos = list_repos_without_positions()
        if not repos:
            logging.info("Nothing to do!")
            return

        results = {}
        for repo in repos:
            success = compute_positions_for_repo(repo['repo_id'], repo['node_count'])
            results[repo['repo_name']] = success

        # Summary
        logging.info("\n" + "=" * 60)
        logging.info("POSITION COMPUTATION SUMMARY")
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

    parser.print_help()
    sys.exit(1)


if __name__ == '__main__':
    main()
