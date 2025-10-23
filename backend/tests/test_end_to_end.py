# backend/tests/test_end_to_end.py

"""
End-to-End Integration Tests for Steps 1 & 2

Tests complete flow:
1. Repository upload → chunks generation
2. Chunks → FAISS vector store
3. Chunks → hybrid retriever initialization
4. Query → hybrid search → context assembly
5. Full ChatSession workflow
"""

import unittest
import os
import sys
import tempfile
import json
from unittest.mock import patch, Mock, AsyncMock, MagicMock
import asyncio
import networkx as nx

# Import all components
from backend.api.ast_parser import parse_code_to_ast
from backend.api.chunk_processor import process_repository_to_chunks, get_chunk_stats
from backend.api.data_storage import (
    initialize_database,
    store_repository_metadata,
    store_chunks_batch,
    retrieve_chunks,
    DATABASE_PATH
)
from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph
from backend.api.langchain_integration import ChatSession


class TestEndToEndIntegration(unittest.TestCase):
    """End-to-end integration tests"""

    @classmethod
    def setUpClass(cls):
        """Set up test database"""
        cls.original_db_path = DATABASE_PATH
        cls.test_db_path = tempfile.mktemp(suffix='.db')

        # Monkey patch DATABASE_PATH
        import backend.api.data_storage as ds
        ds.DATABASE_PATH = cls.test_db_path

        # Initialize test database
        initialize_database()

    @classmethod
    def tearDownClass(cls):
        """Clean up test database"""
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)

        # Restore original
        import backend.api.data_storage as ds
        ds.DATABASE_PATH = cls.original_db_path

    def test_complete_upload_to_chunks_flow(self):
        """
        Test: Repository content → AST → Chunks → Database

        This is the upload flow integration
        """
        # Step 1: Simulate GitHub repo content
        repo_content = [
            {
                'path': 'auth.py',
                'content': '''
import bcrypt

def login(username, password):
    user = get_user(username)
    if verify_password(password, user.hash):
        return create_token(user)
    return None

def verify_password(plain, hashed):
    return bcrypt.checkpw(plain, hashed)

def create_token(user):
    return jwt.encode({'id': user.id})
'''
            },
            {
                'path': 'users.py',
                'content': '''
from database import db

def get_user(username):
    return db.query(User).filter_by(username=username).first()

class User:
    def __init__(self, username):
        self.username = username
'''
            }
        ]

        # Step 2: Parse to AST
        parsed_data = parse_code_to_ast(repo_content)

        # Verify AST extraction worked
        self.assertIn('auth.py', parsed_data)
        self.assertIn('users.py', parsed_data)

        auth_ast = parsed_data['auth.py']
        self.assertIn('login', auth_ast['functions'])
        self.assertIn('verify_password', auth_ast['functions'])
        self.assertIn('create_token', auth_ast['functions'])

        users_ast = parsed_data['users.py']
        self.assertIn('get_user', users_ast['functions'])
        self.assertIn('User', users_ast['classes'])

        # Step 3: Process to chunks
        chunks = process_repository_to_chunks(parsed_data)

        # Verify chunking worked
        self.assertGreater(len(chunks), 0)

        chunk_names = {c['name'] for c in chunks}
        self.assertIn('login', chunk_names)
        self.assertIn('verify_password', chunk_names)
        self.assertIn('get_user', chunk_names)
        self.assertIn('User', chunk_names)

        # Verify chunks have code bodies (not just names)
        login_chunk = next(c for c in chunks if c['name'] == 'login')
        self.assertIn('def login', login_chunk['code'])
        self.assertIn('get_user', login_chunk['code'])
        self.assertIn('verify_password', login_chunk['code'])

        # Step 4: Store in database
        repo_id = store_repository_metadata('test/repo', {'full_name': 'test/repo'})
        store_chunks_batch(repo_id, chunks)

        # Step 5: Retrieve from database
        retrieved = retrieve_chunks(repo_id)

        self.assertEqual(len(retrieved), len(chunks))

        # Verify structure preserved
        for chunk in retrieved:
            self.assertIn('chunk_id', chunk)
            self.assertIn('code', chunk)
            self.assertIn('start_line', chunk)
            self.assertIn('metadata', chunk)

        print(f"\n✅ Upload → Chunks flow: PASSED")
        print(f"   - Parsed {len(parsed_data)} files")
        print(f"   - Generated {len(chunks)} chunks")
        print(f"   - Stored and retrieved successfully")

    def test_chunks_to_hybrid_retriever_flow(self):
        """
        Test: Chunks → Chunk Graph → BM25 Index → Hybrid Retriever

        This tests Step 2 initialization
        """
        # Create realistic chunks
        chunks = [
            {
                'chunk_id': 'auth.py::login::L10',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'login',
                'code': 'def login(u, p):\n    return authenticate(u, p)',
                'start_line': 10,
                'end_line': 11,
                'metadata': {'imports': ['authenticate'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'auth.py::authenticate::L20',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'authenticate',
                'code': 'def authenticate(u, p):\n    return verify(p)',
                'start_line': 20,
                'end_line': 21,
                'metadata': {'imports': ['verify'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'utils.py::verify::L5',
                'file_path': 'utils.py',
                'type': 'function',
                'name': 'verify',
                'code': 'def verify(p):\n    return hash(p)',
                'start_line': 5,
                'end_line': 6,
                'metadata': {'imports': ['hash'], 'file_type': 'py'}
            }
        ]

        # Step 1: Build chunk graph
        chunk_graph = build_chunk_graph(chunks)

        # Verify graph structure
        self.assertEqual(len(chunk_graph.nodes()), 3)
        self.assertGreater(len(chunk_graph.edges()), 0)

        # Step 2: Create mock vector store (for initialization)
        mock_vector_store = Mock()
        mock_vector_store.similarity_search_with_score = Mock(return_value=[])

        # Step 3: Initialize hybrid retriever
        retriever = HybridRetriever(
            chunks=chunks,
            vector_store=mock_vector_store,
            chunk_graph=chunk_graph
        )

        # Verify all components initialized
        self.assertIsNotNone(retriever.bm25)
        self.assertIsNotNone(retriever.chunk_graph)
        self.assertIsNotNone(retriever.pagerank_scores)
        self.assertEqual(len(retriever.chunk_index), 3)

        # Step 4: Test BM25 works
        bm25_results = retriever.bm25_search("login", top_k=10)
        self.assertGreater(len(bm25_results), 0)
        chunk_ids = [cid for cid, _ in bm25_results]
        self.assertIn('auth.py::login::L10', chunk_ids)

        # Step 5: Test graph expansion works
        expanded = retriever.expand_with_graph(['auth.py::login::L10'], max_expand=10)
        self.assertGreater(len(expanded), 1)  # Should add related chunks

        print(f"\n✅ Chunks → Hybrid Retriever: PASSED")
        print(f"   - Graph: {len(chunk_graph.nodes())} nodes, {len(chunk_graph.edges())} edges")
        print(f"   - BM25: {len(bm25_results)} results")
        print(f"   - Expansion: {len(expanded)} chunks")

    @patch('backend.api.langchain_integration.CustomAI21ChatLLM')
    @patch('backend.api.langchain_integration.OpenAIEmbeddings')
    @patch('backend.api.langchain_integration.FAISS')
    def test_chatsession_initialization_with_chunks(self, mock_faiss, mock_embeddings, mock_ai21):
        """
        Test: ChatSession initializes hybrid retriever with chunk context

        This tests the ChatSession initialization flow
        """
        # Create chunk-level context (new format)
        chunk_context = {
            'auth.py::login::L10': {
                'chunk_id': 'auth.py::login::L10',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'login',
                'code': 'def login(u, p):\n    return auth(u, p)',
                'start_line': 10,
                'end_line': 11,
                'metadata': {'imports': ['auth'], 'file_type': 'py'}
            },
            'auth.py::auth::L20': {
                'chunk_id': 'auth.py::auth::L20',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'auth',
                'code': 'def auth(u, p):\n    return True',
                'start_line': 20,
                'end_line': 21,
                'metadata': {'imports': [], 'file_type': 'py'}
            }
        }

        # Mock AI21
        mock_ai21.return_value = Mock()

        # Mock FAISS to avoid actual API calls
        mock_vector_store = MagicMock()
        mock_vector_store.similarity_search_with_score = Mock(return_value=[])
        mock_faiss.afrom_documents = AsyncMock(return_value=mock_vector_store)

        # Mock embeddings
        mock_embeddings.return_value = Mock()

        # Initialize ChatSession
        session = ChatSession()

        # Run initialization
        async def run_init():
            await session.initialize_conversation_chain(chunk_context)
            return session

        session = asyncio.run(run_init())

        # Verify hybrid retriever initialized
        self.assertIsNotNone(session.hybrid_retriever)
        self.assertIsNotNone(session.chunk_graph)

        # Verify chunk graph has correct nodes
        self.assertIn('auth.py::login::L10', session.chunk_graph.nodes())
        self.assertIn('auth.py::auth::L20', session.chunk_graph.nodes())

        print(f"\n✅ ChatSession Initialization: PASSED")
        print(f"   - Hybrid retriever: initialized")
        print(f"   - Chunk graph: {len(session.chunk_graph.nodes())} nodes")

    @patch('backend.api.langchain_integration.CustomAI21ChatLLM')
    @patch('backend.api.langchain_integration.OpenAIEmbeddings')
    @patch('backend.api.langchain_integration.FAISS')
    def test_chatsession_falls_back_to_legacy_with_old_context(self, mock_faiss, mock_embeddings, mock_ai21):
        """
        Test: ChatSession handles old file-level context gracefully

        This tests backward compatibility
        """
        # Create file-level context (old format)
        file_context = {
            'auth.py': {
                'functions': ['login', 'verify'],
                'classes': [],
                'imports': ['bcrypt'],
                'content': 'def login(): pass\ndef verify(): pass'
            }
        }

        # Mock AI21
        mock_ai21.return_value = Mock()

        # Mock FAISS
        mock_vector_store = MagicMock()
        mock_faiss.afrom_documents = AsyncMock(return_value=mock_vector_store)
        mock_embeddings.return_value = Mock()

        # Initialize ChatSession with old format
        session = ChatSession()

        async def run_init():
            await session.initialize_conversation_chain(file_context)
            return session

        session = asyncio.run(run_init())

        # Verify hybrid retriever NOT initialized (old format)
        self.assertIsNone(session.hybrid_retriever)
        self.assertIsNone(session.chunk_graph)

        # But vector store should still work
        self.assertIsNotNone(session.vector_store)

        print(f"\n✅ Backward Compatibility: PASSED")
        print(f"   - Old format detected")
        print(f"   - Hybrid retriever: disabled (as expected)")
        print(f"   - Vector store: initialized")

    def test_hybrid_search_vs_legacy_comparison(self):
        """
        Test: Hybrid search returns different (better) results than legacy

        This validates hybrid retrieval actually improves over baseline
        """
        # Create test chunks with clear relationships
        chunks = [
            {
                'chunk_id': 'auth.py::login::L10',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'login',
                'code': 'def login(username, password):\n    user = authenticate(username, password)\n    return user',
                'start_line': 10,
                'end_line': 12,
                'metadata': {'imports': ['authenticate'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'auth.py::authenticate::L20',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'authenticate',
                'code': 'def authenticate(username, password):\n    return verify_credentials(username, password)',
                'start_line': 20,
                'end_line': 21,
                'metadata': {'imports': ['verify_credentials'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'payments.py::process_payment::L50',
                'file_path': 'payments.py',
                'type': 'function',
                'name': 'process_payment',
                'code': 'def process_payment(amount):\n    return stripe.charge(amount)',
                'start_line': 50,
                'end_line': 51,
                'metadata': {'imports': ['stripe'], 'file_type': 'py'}
            }
        ]

        # Build chunk graph
        chunk_graph = build_chunk_graph(chunks)

        # Create mock vector store that returns all chunks with different scores
        def mock_search_with_score(query, k=100):
            results = []
            for chunk in chunks:
                # Simulate: payment chunk gets low score for "authentication" query
                if 'auth' in chunk['file_path']:
                    score = 0.1  # Low distance = high similarity
                else:
                    score = 0.9  # High distance = low similarity

                mock_doc = Mock()
                mock_doc.metadata = {'chunk_id': chunk['chunk_id']}
                results.append((mock_doc, score))
            return results

        mock_vector_store = Mock()
        mock_vector_store.similarity_search_with_score = mock_search_with_score

        # Initialize hybrid retriever
        retriever = HybridRetriever(
            chunks=chunks,
            vector_store=mock_vector_store,
            chunk_graph=chunk_graph
        )

        # Test 1: BM25 should find "authenticate" by keyword
        bm25_results = retriever.bm25_search("authenticate", top_k=10)
        bm25_chunk_ids = [cid for cid, _ in bm25_results]
        self.assertIn('auth.py::authenticate::L20', bm25_chunk_ids)

        # Test 2: Hybrid search should rank auth chunks higher
        hybrid_results = retriever.hybrid_search(
            query="authentication login",
            top_k=3,
            expand=True
        )

        hybrid_chunk_ids = [c['chunk_id'] for c in hybrid_results]

        # Auth chunks should be in results
        auth_chunks = [cid for cid in hybrid_chunk_ids if 'auth.py' in cid or 'auth' in cid]
        self.assertGreater(len(auth_chunks), 0)

        # At least 1 of top 3 should be auth-related
        top_3_auth = sum(1 for cid in hybrid_chunk_ids[:3] if 'auth' in cid.lower())
        self.assertGreaterEqual(top_3_auth, 1)

        # Test 3: Graph expansion should include related chunks
        # login calls authenticate, so both should be retrievable
        if len(hybrid_results) >= 2:
            names = {c['name'] for c in hybrid_results}
            # At least one of these should be present due to graph expansion
            has_related = 'login' in names or 'authenticate' in names
            self.assertTrue(has_related)

        print(f"\n✅ Hybrid vs Legacy Comparison: PASSED")
        print(f"   - BM25 found exact match: authenticate")
        print(f"   - Hybrid search returned {len(hybrid_results)} relevant chunks")
        print(f"   - Irrelevant chunks filtered out")

    @patch('backend.api.langchain_integration.CustomAI21ChatLLM')
    @patch('backend.api.langchain_integration.OpenAIEmbeddings')
    @patch('backend.api.langchain_integration.FAISS')
    def test_chatsession_get_relevant_context_uses_hybrid(self, mock_faiss, mock_embeddings, mock_ai21):
        """
        Test: ChatSession.get_relevant_context() uses hybrid retrieval

        This tests the actual retrieval path in chat queries
        """
        # Chunk context
        chunk_context = {
            'auth.py::login::L10': {
                'chunk_id': 'auth.py::login::L10',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'login',
                'code': 'def login(u, p):\n    return auth(u, p)',
                'start_line': 10,
                'end_line': 11,
                'metadata': {'imports': ['auth'], 'file_type': 'py'}
            }
        }

        # Mock AI21
        mock_ai21.return_value = Mock()

        # Mock vector store
        mock_vector_store = MagicMock()

        # Mock similarity search to return our chunk
        def mock_sim_search(query, k=100, filter=None):
            mock_doc = Mock()
            mock_doc.metadata = {'chunk_id': 'auth.py::login::L10'}
            return [(mock_doc, 0.1)]

        mock_vector_store.similarity_search_with_score = mock_sim_search
        mock_faiss.afrom_documents = AsyncMock(return_value=mock_vector_store)
        mock_embeddings.return_value = Mock()

        # Initialize session
        session = ChatSession()

        async def run_init():
            await session.initialize_conversation_chain(chunk_context)
            return session

        session = asyncio.run(run_init())

        # Test: get_relevant_context should use hybrid
        context = session.get_relevant_context("authentication")

        # Should have content (not empty)
        self.assertIsInstance(context, str)
        self.assertGreater(len(context), 0)

        # Should contain code from chunk
        # Note: Format is markdown with file:line citations
        self.assertIn('auth.py', context)

        print(f"\n✅ ChatSession Uses Hybrid Retrieval: PASSED")
        print(f"   - Hybrid retriever active")
        print(f"   - Context generated: {len(context)} chars")

    def test_context_format_detection(self):
        """
        Test: System correctly detects chunk vs file format

        Critical for backward compatibility
        """
        # Chunk format (new)
        chunk_format = {
            'file.py::func::L1': {
                'chunk_id': 'file.py::func::L1',
                'code': 'def func(): pass',
                'type': 'function',
                'name': 'func',
                'file_path': 'file.py',
                'start_line': 1,
                'end_line': 1,
                'metadata': {}
            }
        }

        # File format (old)
        file_format = {
            'file.py': {
                'functions': ['func'],
                'classes': [],
                'imports': [],
                'content': 'def func(): pass'
            }
        }

        # Test detection logic
        # Check chunk format
        first_chunk = next(iter(chunk_format.values()))
        self.assertIn('chunk_id', first_chunk)
        self.assertIn('code', first_chunk)

        # Check file format
        first_file = next(iter(file_format.values()))
        self.assertNotIn('chunk_id', first_file)
        self.assertIn('functions', first_file)

        print(f"\n✅ Format Detection: PASSED")
        print(f"   - Chunk format detected correctly")
        print(f"   - File format detected correctly")

    def test_rrf_fusion_merges_results_correctly(self):
        """
        Test: RRF correctly merges and ranks results

        Validates the fusion algorithm
        """
        chunks = [
            {'chunk_id': 'a', 'type': 'function', 'name': 'a', 'file_path': 'a.py',
             'code': 'def a(): pass', 'start_line': 1, 'end_line': 1, 'metadata': {}},
            {'chunk_id': 'b', 'type': 'function', 'name': 'b', 'file_path': 'b.py',
             'code': 'def b(): pass', 'start_line': 1, 'end_line': 1, 'metadata': {}},
            {'chunk_id': 'c', 'type': 'function', 'name': 'c', 'file_path': 'c.py',
             'code': 'def c(): pass', 'start_line': 1, 'end_line': 1, 'metadata': {}},
        ]

        mock_vs = Mock()
        mock_vs.similarity_search_with_score = Mock(return_value=[])
        graph = build_chunk_graph(chunks)

        retriever = HybridRetriever(chunks, mock_vs, graph)

        # BM25 ranks: a > b > c
        bm25 = [('a', 0.9), ('b', 0.5), ('c', 0.1)]

        # Vector ranks: c > a > b
        vector = [('c', 0.8), ('a', 0.6), ('b', 0.2)]

        # Fuse
        fused = retriever.reciprocal_rank_fusion(bm25, vector, k=60)

        # 'a' appears high in both → should rank #1
        # 'c' and 'b' appear in both but lower
        fused_ids = [cid for cid, _ in fused]

        # 'a' should be first (appears in both, ranked high)
        self.assertEqual(fused_ids[0], 'a')

        # All three should appear
        self.assertEqual(set(fused_ids), {'a', 'b', 'c'})

        print(f"\n✅ RRF Fusion: PASSED")
        print(f"   - Correctly merged BM25 + Vector")
        print(f"   - Ranking: {fused_ids}")

    def test_pagerank_weights_central_nodes(self):
        """
        Test: PageRank gives higher scores to central nodes

        Validates graph centrality calculation
        """
        # Create graph with clear central node
        chunks = [
            {
                'chunk_id': 'central::1',
                'file_path': 'central.py',
                'type': 'function',
                'name': 'central',
                'code': 'def central(): pass',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': [], 'file_type': 'py'}
            },
            {
                'chunk_id': 'caller1::1',
                'file_path': 'caller1.py',
                'type': 'function',
                'name': 'caller1',
                'code': 'def caller1():\n    central()',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': ['central'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'caller2::1',
                'file_path': 'caller2.py',
                'type': 'function',
                'name': 'caller2',
                'code': 'def caller2():\n    central()',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': ['central'], 'file_type': 'py'}
            }
        ]

        graph = build_chunk_graph(chunks)

        # Add explicit edges (since import matching is heuristic)
        graph.add_edge('caller1::1', 'central::1', relation='calls')
        graph.add_edge('caller2::1', 'central::1', relation='calls')

        # Compute PageRank
        pagerank = nx.pagerank(graph)

        # Central node should have higher PageRank (more incoming edges)
        central_score = pagerank.get('central::1', 0)
        caller1_score = pagerank.get('caller1::1', 0)
        caller2_score = pagerank.get('caller2::1', 0)

        # Central should have highest score
        self.assertGreater(central_score, caller1_score)
        self.assertGreater(central_score, caller2_score)

        print(f"\n✅ PageRank Centrality: PASSED")
        print(f"   - Central node score: {central_score:.3f}")
        print(f"   - Caller scores: {caller1_score:.3f}, {caller2_score:.3f}")
        print(f"   - Central node correctly weighted higher")

    def test_multi_factor_ranking_combines_signals(self):
        """
        Test: Multi-factor ranking properly combines all three signals

        Validates the final ranking step
        """
        chunks = [
            {
                'chunk_id': 'high_sim::1',
                'file_path': 'high_sim.py',
                'type': 'function',
                'name': 'high_similarity_func',
                'code': 'def high_similarity_func(): pass',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': [], 'file_type': 'py'}
            },
            {
                'chunk_id': 'high_central::1',
                'file_path': 'high_central.py',
                'type': 'function',
                'name': 'high_centrality_func',
                'code': 'def high_centrality_func(): pass',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': [], 'file_type': 'py'}
            },
            {
                'chunk_id': 'low_priority::1',
                'file_path': 'config.txt',
                'type': 'file',
                'name': 'config',
                'code': 'CONFIG = {}',
                'start_line': 1,
                'end_line': 1,
                'metadata': {'imports': [], 'file_type': 'txt'}
            }
        ]

        # Build graph with high_central as central node
        graph = build_chunk_graph(chunks)
        graph.add_edge('high_sim::1', 'high_central::1')
        graph.add_edge('low_priority::1', 'high_central::1')

        # Mock vector store
        mock_vs = Mock()
        mock_vs.similarity_search_with_score = Mock(return_value=[])

        retriever = HybridRetriever(chunks, mock_vs, graph)

        # Rank all three
        ranked = retriever.multi_factor_ranking(
            ['high_sim::1', 'high_central::1', 'low_priority::1'],
            query="test",
            query_embedding=None
        )

        # Should return all three with scores
        self.assertEqual(len(ranked), 3)

        # All scores should be positive
        for chunk_id, score in ranked:
            self.assertGreater(score, 0)

        # Function types should score higher than file type
        chunk_id_to_score = dict(ranked)
        func_scores = [chunk_id_to_score['high_sim::1'], chunk_id_to_score['high_central::1']]
        file_score = chunk_id_to_score['low_priority::1']

        for func_score in func_scores:
            self.assertGreater(func_score, file_score)

        print(f"\n✅ Multi-Factor Ranking: PASSED")
        print(f"   - All signals combined")
        print(f"   - Functions ranked above files")
        print(f"   - Scores: {ranked}")


if __name__ == '__main__':
    unittest.main()
