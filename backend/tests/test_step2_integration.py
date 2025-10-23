# backend/tests/test_step2_integration.py

"""
Integration tests for Step 2: Graph-Guided Hybrid Retrieval

Tests the complete retrieval pipeline with real-world-like data
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock
from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph
import networkx as nx


class TestStep2Integration(unittest.TestCase):

    def setUp(self):
        """Set up realistic test scenario"""
        # Simulated authentication-related codebase
        self.chunks = [
            {
                'chunk_id': 'routes/auth.py::login_endpoint::L15',
                'file_path': 'routes/auth.py',
                'type': 'function',
                'name': 'login_endpoint',
                'code': '''def login_endpoint(request):
    username = request.get('username')
    password = request.get('password')
    return authenticate_user(username, password)''',
                'start_line': 15,
                'end_line': 18,
                'metadata': {'imports': ['authenticate_user'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'auth/service.py::authenticate_user::L42',
                'file_path': 'auth/service.py',
                'type': 'function',
                'name': 'authenticate_user',
                'code': '''def authenticate_user(username, password):
    user = get_user(username)
    if verify_password(password, user.password_hash):
        return create_token(user.id)
    return None''',
                'start_line': 42,
                'end_line': 46,
                'metadata': {'imports': ['get_user', 'verify_password', 'create_token'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'auth/password.py::verify_password::L8',
                'file_path': 'auth/password.py',
                'type': 'function',
                'name': 'verify_password',
                'code': '''def verify_password(plain, hashed):
    return bcrypt.checkpw(plain, hashed)''',
                'start_line': 8,
                'end_line': 9,
                'metadata': {'imports': ['bcrypt'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'auth/token.py::create_token::L12',
                'file_path': 'auth/token.py',
                'type': 'function',
                'name': 'create_token',
                'code': '''def create_token(user_id):
    payload = {'user_id': user_id}
    return jwt.encode(payload, SECRET_KEY)''',
                'start_line': 12,
                'end_line': 14,
                'metadata': {'imports': ['jwt'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'db/users.py::get_user::L25',
                'file_path': 'db/users.py',
                'type': 'function',
                'name': 'get_user',
                'code': '''def get_user(username):
    return db.query(User).filter(User.username == username).first()''',
                'start_line': 25,
                'end_line': 26,
                'metadata': {'imports': ['db', 'User'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'payments/stripe.py::charge_card::L50',
                'file_path': 'payments/stripe.py',
                'type': 'function',
                'name': 'charge_card',
                'code': '''def charge_card(amount, token):
    return stripe.charge(amount, token)''',
                'start_line': 50,
                'end_line': 51,
                'metadata': {'imports': ['stripe'], 'file_type': 'py'}
            }
        ]

        # Create mock vector store
        self.mock_vector_store = Mock()

        # Mock vector store with similarity scores
        def mock_similarity_search(query, k=100):
            # Simulate vector search results
            results = []
            for chunk in self.chunks:
                # Simple heuristic: keyword matching
                score = 0.0
                if 'auth' in query.lower() and 'auth' in chunk['file_path'].lower():
                    score = 0.9
                elif 'password' in query.lower() and 'password' in chunk['name'].lower():
                    score = 0.8
                elif 'token' in query.lower() and 'token' in chunk['name'].lower():
                    score = 0.7
                else:
                    score = 0.3

                results.append((Mock(metadata={'chunk_id': chunk['chunk_id']}), 1 - score))

            return results[:k]

        self.mock_vector_store.similarity_search_with_score = mock_similarity_search

        # Build graph
        self.chunk_graph = build_chunk_graph(self.chunks)

    def test_bm25_finds_keyword_matches(self):
        """Test BM25 finds exact keyword matches"""
        retriever = HybridRetriever(
            chunks=self.chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        # Search for exact function name
        results = retriever.bm25_search("verify_password", top_k=10)

        # Should find the verify_password function
        chunk_ids = [chunk_id for chunk_id, score in results]
        self.assertIn('auth/password.py::verify_password::L8', chunk_ids)

    def test_graph_expansion_finds_related_code(self):
        """Test graph expansion finds functions called by initial result"""
        retriever = HybridRetriever(
            chunks=self.chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        # Start with login endpoint
        initial = ['routes/auth.py::login_endpoint::L15']

        # Expand using graph
        expanded = retriever.expand_with_graph(initial, max_expand=10, expand_depth=2)

        # Should include original
        self.assertIn('routes/auth.py::login_endpoint::L15', expanded)

        # Should include more chunks
        self.assertGreater(len(expanded), 1)

    def test_hybrid_search_full_pipeline(self):
        """Test complete hybrid search pipeline"""
        retriever = HybridRetriever(
            chunks=self.chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        # Query: "How does authentication work?"
        results = retriever.hybrid_search(
            query="authentication login password",
            top_k=5,
            expand=True
        )

        # Should return results
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 5)

        # Each result should be a chunk dict
        for chunk in results:
            self.assertIn('chunk_id', chunk)
            self.assertIn('code', chunk)
            self.assertIn('relevance_score', chunk)

        # Should prioritize auth-related functions
        chunk_names = [c['name'] for c in results]
        # At least some auth-related functions should be in top results
        auth_related = any('login' in name or 'auth' in name or 'verify' in name
                          for name in chunk_names)
        self.assertTrue(auth_related)

    def test_hybrid_search_without_graph_expansion(self):
        """Test hybrid search works even without graph expansion"""
        retriever = HybridRetriever(
            chunks=self.chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        # Search without expansion
        results = retriever.hybrid_search(
            query="password verification",
            top_k=3,
            expand=False  # No graph expansion
        )

        # Should still return results (BM25 + vector only)
        self.assertGreater(len(results), 0)

    def test_type_priority_ranking(self):
        """Test that functions rank higher than files"""
        # Create chunks with different types
        mixed_chunks = [
            {
                'chunk_id': 'func::1',
                'file_path': 'test.py',
                'type': 'function',
                'name': 'test_func',
                'code': 'def test(): pass',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': [], 'file_type': 'py'}
            },
            {
                'chunk_id': 'file::1',
                'file_path': 'config.txt',
                'type': 'file',
                'name': 'config.txt',
                'code': 'CONFIG = {}',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': [], 'file_type': 'txt'}
            }
        ]

        graph = build_chunk_graph(mixed_chunks)
        retriever = HybridRetriever(
            chunks=mixed_chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=graph
        )

        # Rank both
        ranked = retriever.multi_factor_ranking(
            ['func::1', 'file::1'],
            query="test",
            query_embedding=None
        )

        # Function should rank higher than file
        chunk_ids = [chunk_id for chunk_id, score in ranked]
        func_index = chunk_ids.index('func::1')
        file_index = chunk_ids.index('file::1')
        self.assertLess(func_index, file_index)

    def test_pagerank_computation(self):
        """Test PageRank is computed on initialization"""
        retriever = HybridRetriever(
            chunks=self.chunks,
            vector_store=self.mock_vector_store,
            chunk_graph=self.chunk_graph
        )

        # PageRank scores should exist
        self.assertGreater(len(retriever.pagerank_scores), 0)

        # Scores should sum to ~1.0 (PageRank property)
        total = sum(retriever.pagerank_scores.values())
        self.assertAlmostEqual(total, 1.0, places=1)


if __name__ == '__main__':
    unittest.main()
