# backend/tests/test_hybrid_retrieval.py

"""
Unit tests for hybrid retrieval system
"""

import unittest
import networkx as nx
from unittest.mock import Mock, MagicMock
from backend.api.hybrid_retrieval import (
    HybridRetriever,
    build_chunk_graph,
    get_type_priority
)


class TestHybridRetrieval(unittest.TestCase):

    def setUp(self):
        """Set up test chunks and mock vector store"""
        self.test_chunks = [
            {
                'chunk_id': 'auth.py::login::L10',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'login',
                'code': 'def login(user, password):\n    return verify(password)',
                'start_line': 10,
                'end_line': 11,
                'metadata': {'imports': ['verify'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'auth.py::verify::L20',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'verify',
                'code': 'def verify(password):\n    return hash(password)',
                'start_line': 20,
                'end_line': 21,
                'metadata': {'imports': ['hash'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'utils.py::hash::L5',
                'file_path': 'utils.py',
                'type': 'function',
                'name': 'hash',
                'code': 'def hash(text):\n    return md5(text)',
                'start_line': 5,
                'end_line': 6,
                'metadata': {'imports': ['md5'], 'file_type': 'py'}
            }
        ]

        # Mock vector store
        self.mock_vector_store = Mock()
        self.mock_vector_store.similarity_search_with_score = Mock(return_value=[])

        # Build chunk graph
        self.chunk_graph = build_chunk_graph(self.test_chunks)

    def test_build_chunk_graph(self):
        """Test chunk graph creation"""
        G = build_chunk_graph(self.test_chunks)

        # Should have all chunks as nodes
        self.assertEqual(len(G.nodes()), 3)
        self.assertIn('auth.py::login::L10', G.nodes())
        self.assertIn('auth.py::verify::L20', G.nodes())
        self.assertIn('utils.py::hash::L5', G.nodes())

        # Should have edges based on imports
        self.assertGreater(len(G.edges()), 0)

    def test_hybrid_retriever_initialization(self):
        """Test HybridRetriever initializes correctly"""
        retriever = HybridRetriever(
            chunks=self.test_chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        self.assertEqual(len(retriever.chunks), 3)
        self.assertEqual(len(retriever.chunk_index), 3)
        self.assertIsNotNone(retriever.bm25)
        self.assertIsNotNone(retriever.pagerank_scores)

    def test_bm25_search(self):
        """Test BM25 keyword search"""
        retriever = HybridRetriever(
            chunks=self.test_chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        # Search for "login"
        results = retriever.bm25_search("login", top_k=10)

        # Should return results
        self.assertGreater(len(results), 0)

        # First result should be the login function
        chunk_ids = [chunk_id for chunk_id, score in results]
        self.assertIn('auth.py::login::L10', chunk_ids)

    def test_reciprocal_rank_fusion(self):
        """Test RRF fusion algorithm"""
        retriever = HybridRetriever(
            chunks=self.test_chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        bm25_results = [
            ('auth.py::login::L10', 0.9),
            ('auth.py::verify::L20', 0.5)
        ]

        vector_results = [
            ('auth.py::verify::L20', 0.8),
            ('utils.py::hash::L5', 0.6)
        ]

        fused = retriever.reciprocal_rank_fusion(bm25_results, vector_results)

        # Should merge both lists
        self.assertGreater(len(fused), 0)

        # All chunks should appear
        chunk_ids = [chunk_id for chunk_id, score in fused]
        self.assertIn('auth.py::login::L10', chunk_ids)
        self.assertIn('auth.py::verify::L20', chunk_ids)
        self.assertIn('utils.py::hash::L5', chunk_ids)

        # verify should rank high (appears in both lists)
        verify_rank = chunk_ids.index('auth.py::verify::L20')
        self.assertLessEqual(verify_rank, 1)  # Should be top 2

    def test_expand_with_graph(self):
        """Test graph-based expansion"""
        retriever = HybridRetriever(
            chunks=self.test_chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        # Start with just login function
        initial = ['auth.py::login::L10']

        # Expand
        expanded = retriever.expand_with_graph(initial, max_expand=10, expand_depth=2)

        # Should include more chunks
        self.assertGreater(len(expanded), len(initial))

        # Should still include original
        self.assertIn('auth.py::login::L10', expanded)

    def test_multi_factor_ranking(self):
        """Test multi-factor ranking"""
        retriever = HybridRetriever(
            chunks=self.test_chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        chunk_ids = ['auth.py::login::L10', 'auth.py::verify::L20', 'utils.py::hash::L5']
        query = "authentication"
        query_embedding = None  # Not used in current implementation

        ranked = retriever.multi_factor_ranking(chunk_ids, query, query_embedding)

        # Should return all chunks with scores
        self.assertEqual(len(ranked), 3)

        # Each result should be (chunk_id, score)
        for chunk_id, score in ranked:
            self.assertIn(chunk_id, chunk_ids)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 1)

    def test_get_type_priority(self):
        """Test type priority mapping"""
        self.assertEqual(get_type_priority('function'), 1.0)
        self.assertEqual(get_type_priority('class'), 0.9)
        self.assertEqual(get_type_priority('method'), 0.8)
        self.assertEqual(get_type_priority('file'), 0.5)
        self.assertLess(get_type_priority('unknown'), 1.0)

    def test_chunk_graph_has_edges(self):
        """Test that chunk graph creates edges from imports"""
        G = build_chunk_graph(self.test_chunks)

        # Should have edges (either import or same_file)
        self.assertGreater(len(G.edges()), 0)

        # Check edge attributes exist
        for u, v, data in G.edges(data=True):
            self.assertIn('relation', data)

    def test_hybrid_retriever_with_empty_graph(self):
        """Test hybrid retriever handles empty graph gracefully"""
        empty_graph = nx.DiGraph()

        retriever = HybridRetriever(
            chunks=self.test_chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=empty_graph
        )

        # Should still initialize
        self.assertIsNotNone(retriever)
        self.assertEqual(len(retriever.pagerank_scores), 0)

        # Expansion should return original list
        expanded = retriever.expand_with_graph(['auth.py::login::L10'], max_expand=10)
        self.assertEqual(len(expanded), 1)


if __name__ == '__main__':
    unittest.main()
