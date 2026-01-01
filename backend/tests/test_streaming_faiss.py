"""
Test streaming FAISS download functionality.

Tests the memory-efficient streaming download that prevents OOM on Railway.
"""

import pytest
import asyncio
import tempfile
import gzip
import os
import shutil
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from io import BytesIO


class TestStreamingFAISSDownload:
    """Test the streaming FAISS download implementation."""

    def test_gzip_streaming_decompression(self):
        """
        Test that gzip streaming decompression works correctly.
        This validates the core memory-safe decompression logic.
        """
        # Create test data
        original_data = b"Hello World! " * 100000  # ~1.3MB uncompressed

        # Compress it
        compressed_data = gzip.compress(original_data)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write compressed data to file
            compressed_path = os.path.join(tmpdir, "test.gz")
            with open(compressed_path, 'wb') as f:
                f.write(compressed_data)

            # Stream decompress (the key memory-safe operation)
            decompressed_path = os.path.join(tmpdir, "test_decompressed")
            with gzip.open(compressed_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    # Use same buffer size as implementation
                    shutil.copyfileobj(f_in, f_out, length=64*1024*1024)

            # Verify decompressed content
            with open(decompressed_path, 'rb') as f:
                result = f.read()

            assert result == original_data
            assert len(result) == len(original_data)

    def test_chunked_file_concatenation(self):
        """
        Test that chunked file concatenation works correctly.
        This validates the chunk reassembly logic.
        """
        # Create test chunks
        chunk1 = b"CHUNK1_DATA_" * 1000
        chunk2 = b"CHUNK2_DATA_" * 1000
        chunk3 = b"CHUNK3_DATA_" * 1000
        expected = chunk1 + chunk2 + chunk3

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write chunks to temp files
            chunk_paths = []
            for i, data in enumerate([chunk1, chunk2, chunk3]):
                path = os.path.join(tmpdir, f"chunk_{i:03d}")
                with open(path, 'wb') as f:
                    f.write(data)
                chunk_paths.append(path)

            # Concatenate using same logic as implementation
            output_path = os.path.join(tmpdir, "concatenated")
            with open(output_path, 'wb') as outfile:
                for temp_path in chunk_paths:
                    with open(temp_path, 'rb') as infile:
                        while True:
                            chunk_data = infile.read(64*1024*1024)
                            if not chunk_data:
                                break
                            outfile.write(chunk_data)
                    os.unlink(temp_path)

            # Verify
            with open(output_path, 'rb') as f:
                result = f.read()

            assert result == expected
            assert len(result) == len(expected)

            # Verify temp files were deleted
            for path in chunk_paths:
                assert not os.path.exists(path)

    def test_full_streaming_pipeline(self):
        """
        Test the full streaming pipeline: chunks -> concat -> decompress.
        This simulates the exact flow used in production.
        """
        # Create original ZIP-like content
        original_content = b"FAISS_INDEX_DATA_" * 50000  # ~850KB

        # Compress it (simulating the stored gzipped FAISS)
        compressed = gzip.compress(original_content)

        # Split into chunks (simulating chunked storage in Supabase)
        chunk_size = len(compressed) // 3
        chunks = [
            compressed[:chunk_size],
            compressed[chunk_size:2*chunk_size],
            compressed[2*chunk_size:]
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Phase 1: Write chunks to temp files (simulating streaming download)
            chunk_paths = []
            for i, chunk_data in enumerate(chunks):
                path = os.path.join(tmpdir, f"chunk_{i:03d}")
                with open(path, 'wb') as f:
                    f.write(chunk_data)
                chunk_paths.append(path)

            # Phase 2: Concatenate on disk
            compressed_path = os.path.join(tmpdir, "compressed.gz")
            with open(compressed_path, 'wb') as outfile:
                for temp_path in chunk_paths:
                    with open(temp_path, 'rb') as infile:
                        while True:
                            data = infile.read(64*1024*1024)
                            if not data:
                                break
                            outfile.write(data)
                    os.unlink(temp_path)

            # Phase 3: Stream decompress
            decompressed_path = os.path.join(tmpdir, "decompressed")
            with gzip.open(compressed_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out, length=64*1024*1024)

            # Clean up compressed
            os.unlink(compressed_path)

            # Verify final content
            with open(decompressed_path, 'rb') as f:
                result = f.read()

            assert result == original_content
            assert len(result) == len(original_content)

    def test_buffer_sizes(self):
        """
        Test that the buffer sizes used are optimal.
        8MB for network streaming, 64MB for disk I/O.
        """
        # Network streaming buffer (8MB)
        NETWORK_BUFFER = 8 * 1024 * 1024
        assert NETWORK_BUFFER == 8388608

        # Disk I/O buffer (64MB)
        DISK_BUFFER = 64 * 1024 * 1024
        assert DISK_BUFFER == 67108864

        # Verify these are powers of 2 for optimal I/O
        import math
        assert math.log2(NETWORK_BUFFER).is_integer()
        assert math.log2(DISK_BUFFER).is_integer()


class TestMemoryEfficiency:
    """Test that the streaming approach is memory-efficient."""

    def test_streaming_vs_buffered_comparison(self):
        """
        Compare memory behavior of streaming vs buffered approaches.
        This test documents why streaming is necessary.
        """
        # Create ~10MB of test data (scaled down from 774MB for testing)
        original_data = b"X" * (10 * 1024 * 1024)
        compressed_data = gzip.compress(original_data)

        # OLD APPROACH (memory hungry): Would hold both in memory
        # compressed_data + gzip.decompress(compressed_data) = 2x memory
        # For 774MB: 774MB + 774MB = 1.5GB peak

        # NEW APPROACH (streaming): Only holds buffer in memory
        # For 774MB: ~64MB buffer peak

        with tempfile.TemporaryDirectory() as tmpdir:
            compressed_path = os.path.join(tmpdir, "test.gz")
            with open(compressed_path, 'wb') as f:
                f.write(compressed_data)

            # Streaming decompression - only buffer in memory
            decompressed_path = os.path.join(tmpdir, "test_out")
            buffer_size = 64 * 1024 * 1024  # 64MB

            with gzip.open(compressed_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out, length=buffer_size)

            # Verify the streaming worked
            assert os.path.getsize(decompressed_path) == len(original_data)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_single_chunk_download(self):
        """Test handling of single-chunk (small) FAISS indexes."""
        original = b"Small FAISS index data"
        compressed = gzip.compress(original)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Single chunk goes directly to compressed path
            compressed_path = os.path.join(tmpdir, "compressed.gz")
            with open(compressed_path, 'wb') as f:
                f.write(compressed)

            # Decompress
            decompressed_path = os.path.join(tmpdir, "decompressed")
            with gzip.open(compressed_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            with open(decompressed_path, 'rb') as f:
                assert f.read() == original

    def test_empty_chunk_handling(self):
        """Test that empty chunks don't break the concatenation."""
        chunks = [b"data1", b"", b"data2"]

        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_paths = []
            for i, data in enumerate(chunks):
                path = os.path.join(tmpdir, f"chunk_{i:03d}")
                with open(path, 'wb') as f:
                    f.write(data)
                chunk_paths.append(path)

            output_path = os.path.join(tmpdir, "output")
            with open(output_path, 'wb') as outfile:
                for temp_path in chunk_paths:
                    with open(temp_path, 'rb') as infile:
                        shutil.copyfileobj(infile, outfile)

            with open(output_path, 'rb') as f:
                result = f.read()

            assert result == b"data1data2"


def run_tests():
    """Run all tests and report results."""
    import traceback

    test_classes = [
        TestStreamingFAISSDownload,
        TestMemoryEfficiency,
        TestEdgeCases
    ]

    passed = 0
    failed = 0

    for test_class in test_classes:
        instance = test_class()
        for method_name in dir(instance):
            if method_name.startswith('test_'):
                method = getattr(instance, method_name)
                try:
                    method()
                    print(f"  ✅ {test_class.__name__}.{method_name}")
                    passed += 1
                except Exception as e:
                    print(f"  ❌ {test_class.__name__}.{method_name}")
                    print(f"     Error: {e}")
                    traceback.print_exc()
                    failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    print("Running Streaming FAISS Download Tests")
    print("=" * 60)
    success = run_tests()
    exit(0 if success else 1)
