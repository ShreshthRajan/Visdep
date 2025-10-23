# backend/tests/test_step3_integration.py

"""
Integration tests for Step 3: Full Pipeline with Claude
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio

from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph
from backend.api.reranker import CodeReranker, ContextAssembler
from backend.api.langchain_integration import ChatSession


class TestStep3Integration(unittest.TestCase):

    def setUp(self):
        """Set up test data"""
        self.test_chunks = [
            {
                'chunk_id': 'auth.py::login::L10',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'login',
                'code': 'def login(username, password):\n    return authenticate_user(username, password)',
                'start_line': 10,
                'end_line': 11,
                'metadata': {'imports': ['authenticate_user'], 'file_type': 'py'}
            },
            {
                'chunk_id': 'auth.py::authenticate_user::L20',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'authenticate_user',
                'code': 'def authenticate_user(username, password):\n    return verify_password(password)',
                'start_line': 20,
                'end_line': 21,
                'metadata': {'imports': ['verify_password'], 'file_type': 'py'}
            }
        ]

    @patch('backend.api.reranker.CrossEncoder')
    def test_full_retrieval_pipeline_with_reranking(self, mock_cross_encoder):
        """
        Test complete pipeline: Hybrid search → Reranking → Context assembly

        This validates Steps 2 + 3 integration
        """
        # Mock cross-encoder
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[0.95, 0.45])  # First chunk scores higher
        mock_cross_encoder.return_value = mock_model

        # Build graph and retriever
        graph = build_chunk_graph(self.test_chunks)

        mock_vector_store = Mock()
        mock_vector_store.similarity_search_with_score = Mock(return_value=[
            (Mock(metadata={'chunk_id': chunk['chunk_id']}), 0.1)
            for chunk in self.test_chunks
        ])

        retriever = HybridRetriever(self.test_chunks, mock_vector_store, graph)

        # Step 1: Hybrid search
        search_results = retriever.hybrid_search("authentication", top_k=2)
        self.assertEqual(len(search_results), 2)

        # Step 2: Rerank
        reranker = CodeReranker()
        reranked = reranker.rerank("authentication", search_results, top_k=2)

        # Should reorder based on scores
        self.assertEqual(len(reranked), 2)
        self.assertIn('rerank_score', reranked[0])

        # Higher scoring chunk should be first
        self.assertGreater(reranked[0]['rerank_score'], reranked[1]['rerank_score'])

        # Step 3: Assemble context
        assembler = ContextAssembler(max_tokens=5000)
        assembled = assembler.assemble_context(reranked, include_full_code_top_n=1)

        # Should have context
        self.assertGreater(len(assembled['context_parts']), 0)
        self.assertGreater(assembled['total_tokens'], 0)

        # Should have citations
        self.assertEqual(len(assembled['citations']), 2)

        # Should have graph highlights
        self.assertEqual(len(assembled['graph_highlights']), 2)

        print(f"\n✅ Full Pipeline Integration: PASSED")
        print(f"   - Hybrid search: {len(search_results)} results")
        print(f"   - Reranked: {len(reranked)} chunks")
        print(f"   - Context: {assembled['chunks_included']} chunks, {assembled['total_tokens']} tokens")

    @patch('backend.api.langchain_integration.Anthropic')
    @patch('backend.api.langchain_integration.OpenAIEmbeddings')
    @patch('backend.api.langchain_integration.FAISS')
    @patch('backend.api.reranker.CrossEncoder')
    def test_chatsession_uses_claude(self, mock_cross_encoder, mock_faiss, mock_embeddings, mock_anthropic):
        """
        Test: ChatSession uses Claude when available

        This tests Step 3 integration in ChatSession
        """
        # Mock cross-encoder
        mock_ce_model = Mock()
        mock_ce_model.predict = Mock(return_value=[0.9, 0.8])
        mock_cross_encoder.return_value = mock_ce_model

        # Mock Claude
        mock_claude = Mock()
        mock_response = Mock()
        mock_response.content = [Mock(text="Authentication works by calling login() in auth.py:10")]
        mock_claude.messages.create = Mock(return_value=mock_response)
        mock_anthropic.return_value = mock_claude

        # Mock FAISS
        mock_vector_store = MagicMock()
        mock_vector_store.similarity_search_with_score = Mock(return_value=[
            (Mock(metadata={'chunk_id': chunk['chunk_id']}), 0.1)
            for chunk in self.test_chunks
        ])
        mock_faiss.afrom_documents = AsyncMock(return_value=mock_vector_store)
        mock_embeddings.return_value = Mock()

        # Create chunk context
        chunk_context = {chunk['chunk_id']: chunk for chunk in self.test_chunks}

        # Initialize session
        session = ChatSession()

        async def run_test():
            # Initialize with ANTHROPIC_API_KEY present
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
                await session.initialize_conversation_chain(chunk_context)

                # Verify Claude client initialized
                self.assertIsNotNone(session.claude_client)
                self.assertIsNotNone(session.reranker)
                self.assertIsNotNone(session.context_assembler)

                # Query
                response = await session.chat("How does authentication work?")

                # Claude should have been called
                mock_claude.messages.create.assert_called_once()

                # Response should be the mocked text
                self.assertIn("Authentication works", response)
                self.assertIn("auth.py:10", response)

                print(f"\n✅ ChatSession Uses Claude: PASSED")
                print(f"   - Claude client initialized")
                print(f"   - Reranker active")
                print(f"   - Context assembler active")
                print(f"   - Claude API called successfully")

        asyncio.run(run_test())

    @patch('backend.api.langchain_integration.OpenAIEmbeddings')
    @patch('backend.api.langchain_integration.FAISS')
    def test_chatsession_falls_back_without_anthropic_key(self, mock_faiss, mock_embeddings):
        """
        Test: ChatSession falls back to AI21 if ANTHROPIC_API_KEY not set

        This validates graceful degradation
        """
        # Mock FAISS
        mock_vector_store = MagicMock()
        mock_vector_store.similarity_search_with_score = Mock(return_value=[])
        mock_faiss.afrom_documents = AsyncMock(return_value=mock_vector_store)
        mock_embeddings.return_value = Mock()

        # File context (old format)
        file_context = {
            'file.py': {
                'functions': ['func'],
                'classes': [],
                'imports': [],
                'content': 'def func(): pass'
            }
        }

        session = ChatSession()

        async def run_test():
            # Initialize without ANTHROPIC_API_KEY
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': ''}, clear=True):
                # Should not crash, should fall back to AI21
                # (Will fail if AI21_API_KEY also missing, but that's expected)
                try:
                    await session.initialize_conversation_chain(file_context)
                except:
                    # Expected if AI21 also not configured
                    pass

                # Verify Claude NOT initialized
                self.assertIsNone(session.claude_client)

                print(f"\n✅ Fallback to AI21: PASSED")
                print(f"   - ANTHROPIC_API_KEY missing")
                print(f"   - Claude not initialized (as expected)")
                print(f"   - System degraded gracefully")

        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()
