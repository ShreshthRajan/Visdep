#!/usr/bin/env python3
"""
Upload local FAISS index to Supabase Storage for pre-indexed repos.

This fixes repos that were pre-indexed before the Supabase FAISS storage was added.

Usage:
    python scripts/upload_faiss_to_supabase.py --repo-id 13
"""

import os
import sys
import gzip
import argparse
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def upload_faiss(repo_id: int):
    """Upload local FAISS index to Supabase Storage."""
    from backend.api.data_storage import FAISS_DIR
    from backend.api.supabase_client import get_supabase_client
    import httpx
    
    # Find local FAISS index
    local_path = f"{FAISS_DIR}/{repo_id}"
    
    if not os.path.exists(local_path):
        logging.error(f"❌ Local FAISS index not found: {local_path}")
        return False
    
    logging.info(f"📥 Loading local FAISS index: {local_path}")
    
    # Check if it's a directory (FAISS saves as directory with index.faiss and index.pkl)
    if os.path.isdir(local_path):
        # FAISS saves as directory - need to zip it
        import shutil
        import tempfile
        
        logging.info(f"   FAISS index is a directory, creating archive...")
        
        # Create temporary zip file
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
            zip_path = tmp_zip.name
        
        # Create zip archive
        shutil.make_archive(zip_path.replace('.zip', ''), 'zip', local_path)
        
        # Read zip file
        with open(zip_path, 'rb') as f:
            faiss_data = f.read()
        
        # Clean up temp file
        os.unlink(zip_path)
        
        file_size_mb = len(faiss_data) / (1024 * 1024)
        logging.info(f"   Archive size: {file_size_mb:.1f} MB")
        
        # Compress with gzip
        compressed = gzip.compress(faiss_data)
        compressed_mb = len(compressed) / (1024 * 1024)
        logging.info(f"   Compressed: {file_size_mb:.1f}MB → {compressed_mb:.1f}MB ({100 * compressed_mb / file_size_mb:.0f}%)")
        
    else:
        # Single file (unlikely but handle it)
        with open(local_path, 'rb') as f:
            faiss_data = f.read()
        
        file_size_mb = len(faiss_data) / (1024 * 1024)
        logging.info(f"   File size: {file_size_mb:.1f} MB")
        
        # Compress with gzip
        compressed = gzip.compress(faiss_data)
        compressed_mb = len(compressed) / (1024 * 1024)
        logging.info(f"   Compressed: {file_size_mb:.1f}MB → {compressed_mb:.1f}MB ({100 * compressed_mb / file_size_mb:.0f}%)")
    
    # Supabase Storage has ~50MB file size limit, so split into chunks if needed
    CHUNK_SIZE_MB = 40  # Stay under 50MB limit
    CHUNK_SIZE_BYTES = CHUNK_SIZE_MB * 1024 * 1024
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
    
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/gzip",
        "x-upsert": "true"
    }
    
    if len(compressed) <= CHUNK_SIZE_BYTES:
        # Small enough to upload as single file
        storage_path = f"faiss/{repo_id}.faiss.gz"
        upload_url = f"{supabase_url}/storage/v1/object/repo-data/{storage_path}"
        
        logging.info(f"📤 Uploading {compressed_mb:.1f}MB as single file...")
        
        try:
            with httpx.Client(timeout=600.0) as client:
                response = client.post(
                    upload_url,
                    content=compressed,
                    headers=headers
                )
                if response.status_code >= 400:
                    logging.error(f"❌ Upload failed: {response.status_code}")
                    logging.error(f"   Response: {response.text}")
                    return False
                logging.info(f"   ✅ Upload successful: {response.status_code}")
        except Exception as e:
            logging.error(f"❌ Upload failed: {e}")
            return False
        
        # Store reference in table
        supabase = get_supabase_client()
        supabase.table('repo_faiss').upsert({
            'repo_id': repo_id,
            'storage_path': storage_path,
            'chunk_count': 1,
            'dimension': 1536
        }, on_conflict='repo_id').execute()
        
        logging.info(f"✅ FAISS index uploaded to Storage: repo-data/{storage_path}")
        return True
    
    else:
        # Too large - split into chunks
        num_chunks = (len(compressed) + CHUNK_SIZE_BYTES - 1) // CHUNK_SIZE_BYTES
        logging.info(f"📤 File too large ({compressed_mb:.1f}MB), splitting into {num_chunks} chunks...")
        
        chunk_paths = []
        for i in range(num_chunks):
            start = i * CHUNK_SIZE_BYTES
            end = min(start + CHUNK_SIZE_BYTES, len(compressed))
            chunk_data = compressed[start:end]
            chunk_mb = len(chunk_data) / (1024 * 1024)
            
            chunk_path = f"faiss/{repo_id}.faiss.gz.chunk{i:03d}"
            upload_url = f"{supabase_url}/storage/v1/object/repo-data/{chunk_path}"
            
            logging.info(f"   Uploading chunk {i+1}/{num_chunks} ({chunk_mb:.1f}MB)...")
            
            try:
                with httpx.Client(timeout=600.0) as client:
                    response = client.post(
                        upload_url,
                        content=chunk_data,
                        headers=headers
                    )
                    if response.status_code >= 400:
                        logging.error(f"❌ Chunk {i+1} upload failed: {response.status_code}")
                        logging.error(f"   Response: {response.text}")
                        return False
            except Exception as e:
                logging.error(f"❌ Chunk {i+1} upload failed: {e}")
                return False
            
            chunk_paths.append(chunk_path)
        
        # Store reference in table with chunk metadata
        supabase = get_supabase_client()
        supabase.table('repo_faiss').upsert({
            'repo_id': repo_id,
            'storage_path': f"faiss/{repo_id}.faiss.gz.chunk000",  # First chunk path (for reference)
            'chunk_count': num_chunks,
            'dimension': 1536
        }, on_conflict='repo_id').execute()
        
        logging.info(f"✅ FAISS index uploaded as {num_chunks} chunks to Storage")
        return True


def main():
    parser = argparse.ArgumentParser(description='Upload local FAISS index to Supabase')
    parser.add_argument('--repo-id', type=int, required=True, help='Repository ID')
    args = parser.parse_args()
    
    success = upload_faiss(args.repo_id)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

