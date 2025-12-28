#!/usr/bin/env python3
"""
Upload local graph JSON to Supabase Storage for pre-indexed repos.

This fixes repos that were pre-indexed before the Supabase graph storage was added.
Uses Supabase Storage for large files (>2MB) since the REST API has payload limits.

Usage:
    python scripts/upload_graph_to_supabase.py --repo-id 13
"""

import os
import sys
import json
import gzip
import argparse
import logging
import httpx

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Size threshold for using Storage vs Table (2MB)
STORAGE_THRESHOLD_MB = 2


def upload_graph(repo_id: int):
    """Upload local graph JSON to Supabase (Storage for large files, table for small)."""
    from backend.api.supabase_client import get_supabase_client
    
    # Find local graph file
    local_path = f"dependency_graph_{repo_id}.json"
    
    if not os.path.exists(local_path):
        logging.error(f"❌ Local graph file not found: {local_path}")
        return False
    
    logging.info(f"📥 Loading local graph: {local_path}")
    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    logging.info(f"   File size: {file_size_mb:.1f} MB")
    
    with open(local_path, 'r') as f:
        graph_data = json.load(f)
    
    node_count = len(graph_data.get('nodes', []))
    edge_count = len(graph_data.get('links', []))
    logging.info(f"   Nodes: {node_count:,}, Edges: {edge_count:,}")
    
    supabase = get_supabase_client()
    
    if file_size_mb > STORAGE_THRESHOLD_MB:
        # Large file: Use Supabase Storage via direct REST API
        logging.info(f"📤 File too large for table ({file_size_mb:.1f}MB > {STORAGE_THRESHOLD_MB}MB)")
        logging.info(f"   Compressing and uploading to Supabase Storage...")
        
        # Compress the JSON
        json_bytes = json.dumps(graph_data).encode('utf-8')
        compressed = gzip.compress(json_bytes)
        compressed_mb = len(compressed) / (1024 * 1024)
        logging.info(f"   Compressed: {file_size_mb:.1f}MB → {compressed_mb:.1f}MB ({100 * compressed_mb / file_size_mb:.0f}%)")
        
        # Storage path
        storage_path = f"{repo_id}.json.gz"
        
        # Upload using direct REST API (more reliable than SDK for large files)
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
        
        if not supabase_key:
            logging.error("❌ SUPABASE_SERVICE_KEY not found in environment")
            return False
        
        upload_url = f"{supabase_url}/storage/v1/object/repo-data/{storage_path}"
        
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/gzip",
            "x-upsert": "true"
        }
        
        logging.info(f"   Uploading {compressed_mb:.1f}MB to {upload_url}...")
        logging.info(f"   Service key length: {len(supabase_key)} chars")
        
        # Try to delete existing file first (in case of corruption)
        try:
            delete_url = f"{supabase_url}/storage/v1/object/repo-data/{storage_path}"
            with httpx.Client(timeout=30.0) as client:
                delete_response = client.delete(delete_url, headers=headers)
                if delete_response.status_code in [200, 204, 404]:
                    logging.info(f"   Cleared existing file (if any)")
        except:
            pass  # Ignore delete errors
        
        try:
            with httpx.Client(timeout=600.0) as client:  # 10 min timeout for large files
                response = client.post(
                    upload_url,
                    content=compressed,
                    headers=headers
                )
                if response.status_code >= 400:
                    logging.error(f"❌ Upload failed: {response.status_code}")
                    logging.error(f"   Response: {response.text}")
                    logging.error(f"   URL: {upload_url}")
                    logging.error(f"   Headers: {list(headers.keys())}")
                    return False
                logging.info(f"   ✅ Upload successful: {response.status_code}")
        except httpx.TimeoutException:
            logging.error(f"❌ Upload timed out (file too large or slow connection)")
            return False
        except Exception as e:
            logging.error(f"❌ Upload failed: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False
        
        # Store reference in table
        supabase.table('repo_graphs').upsert({
            'repo_id': repo_id,
            'graph_data': {'storage_path': storage_path, 'compressed': True, 'node_count': node_count}
        }, on_conflict='repo_id').execute()
        
        logging.info(f"✅ Graph uploaded to Storage: repo-data/{storage_path}")
        return True
        
    else:
        # Small file: Use table directly
        logging.info(f"📤 Uploading to Supabase repo_graphs table...")
        
        result = supabase.table('repo_graphs').upsert({
            'repo_id': repo_id,
            'graph_data': graph_data
        }, on_conflict='repo_id').execute()
        
        if result.data:
            logging.info(f"✅ Graph uploaded successfully for repo_id={repo_id}")
            return True
        else:
            logging.error(f"❌ Failed to upload graph")
            return False


def main():
    parser = argparse.ArgumentParser(description='Upload local graph JSON to Supabase')
    parser.add_argument('--repo-id', type=int, required=True, help='Repository ID')
    args = parser.parse_args()
    
    success = upload_graph(args.repo_id)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
