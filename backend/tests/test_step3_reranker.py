# backend/tests/test_step3_reranker.py

"""
Unit tests for Step 3: Reranking and Context Assembly
"""

import unittest
from unittest.mock import Mock, patch
from backend.api.reranker import (
    CodeReranker,
    ContextAssembler,
    extract_citations_from_response
)


class TestReranker(unittest.TestCase):

    def setUp(self):
        """Set up test chunks"""
        self.test_chunks = [
            {
                'chunk_id': 'auth.py::login::L10',
                'file_path': 'auth.py',
                'type': 'function',
                'name': 'login',
                'code': 'def login(user, password):\n    return authenticate(user, password)',
                'start_line': 10,
                'end_line': 11,
                'metadata': {'file_type': 'py'}
            },
            {
                'chunk_id': 'utils.py::helper::L5',
                'file_path': 'utils.py',
                'type': 'function',
                'name': 'helper',
                'code': 'def helper():\n    return True',
                'start_line': 5,
                'end_line': 6,
                'metadata': {'file_type': 'py'}
            }
        ]

    @patch('backend.api.reranker.CrossEncoder')
    def test_reranker_initialization(self, mock_cross_encoder):
        """Test CodeReranker initializes correctly"""
        mock_model = Mock()
        mock_cross_encoder.return_value = mock_model

        reranker = CodeReranker()

        mock_cross_encoder.assert_called_once()
        self.assertIsNotNone(reranker.model)

    @patch('backend.api.reranker.CrossEncoder')
    def test_rerank_returns_top_k(self, mock_cross_encoder):
        """Test reranking returns correct number of results"""
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[0.9, 0.3])  # Scores for 2 chunks
        mock_cross_encoder.return_value = mock_model

        reranker = CodeReranker()
        reranked = reranker.rerank("test query", self.test_chunks, top_k=1)

        # Should return only top 1
        self.assertEqual(len(reranked), 1)

        # Should be the first chunk (higher score)
        self.assertEqual(reranked[0]['chunk_id'], 'auth.py::login::L10')
        self.assertIn('rerank_score', reranked[0])

    @patch('backend.api.reranker.CrossEncoder')
    def test_rerank_sorts_by_score(self, mock_cross_encoder):
        """Test reranking sorts by score correctly"""
        mock_model = Mock()
        # Second chunk scores higher
        mock_model.predict = Mock(return_value=[0.3, 0.9])
        mock_cross_encoder.return_value = mock_model

        reranker = CodeReranker()
        reranked = reranker.rerank("test query", self.test_chunks, top_k=2)

        # Second chunk should be first now
        self.assertEqual(reranked[0]['chunk_id'], 'utils.py::helper::L5')
        self.assertEqual(reranked[1]['chunk_id'], 'auth.py::login::L10')

    @patch('backend.api.reranker.CrossEncoder')
    def test_rerank_adds_scores(self, mock_cross_encoder):
        """Test reranking adds scores to chunks"""
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[0.85, 0.42])
        mock_cross_encoder.return_value = mock_model

        reranker = CodeReranker()
        reranked = reranker.rerank("test", self.test_chunks, top_k=2)

        # Check scores added
        self.assertAlmostEqual(reranked[0]['rerank_score'], 0.85, places=2)
        self.assertAlmostEqual(reranked[1]['rerank_score'], 0.42, places=2)


class TestContextAssembler(unittest.TestCase):

    def setUp(self):
        """Set up test chunks"""
        self.test_chunks = [
            {
                'chunk_id': 'file1.py::func1::L1',
                'file_path': 'file1.py',
                'type': 'function',
                'name': 'func1',
                'code': 'def func1():\n    return 1',
                'start_line': 1,
                'end_line': 2,
                'metadata': {'file_type': 'py'}
            },
            {
                'chunk_id': 'file2.py::func2::L10',
                'file_path': 'file2.py',
                'type': 'function',
                'name': 'func2',
                'code': 'def func2():\n    return 2',
                'start_line': 10,
                'end_line': 11,
                'metadata': {'file_type': 'py'}
            }
        ]

    def test_assembler_initialization(self):
        """Test ContextAssembler initializes"""
        assembler = ContextAssembler(max_tokens=5000)
        self.assertEqual(assembler.max_tokens, 5000)

    def test_estimate_tokens(self):
        """Test token estimation"""
        assembler = ContextAssembler()

        # Test with known text
        text = "hello world this is a test"  # 6 words
        tokens = assembler.estimate_tokens(text)

        # Should be roughly 10 tokens (6 words / 0.6)
        self.assertGreater(tokens, 5)
        self.assertLess(tokens, 15)

    def test_assemble_context_structure(self):
        """Test assembled context has correct structure"""
        assembler = ContextAssembler(max_tokens=10000)

        result = assembler.assemble_context(self.test_chunks, include_full_code_top_n=2)

        # Check structure
        self.assertIn('context_parts', result)
        self.assertIn('citations', result)
        self.assertIn('graph_highlights', result)
        self.assertIn('total_tokens', result)
        self.assertIn('chunks_included', result)

        # Should include both chunks (under token budget)
        self.assertEqual(result['chunks_included'], 2)
        self.assertEqual(len(result['citations']), 2)
        self.assertEqual(len(result['graph_highlights']), 2)

    def test_assemble_respects_token_budget(self):
        """Test context assembly respects token limit"""
        assembler = ContextAssembler(max_tokens=50)  # Very small budget

        # Create chunk with lots of text
        big_chunks = [
            {
                'chunk_id': 'big.py::big_func::L1',
                'file_path': 'big.py',
                'type': 'function',
                'name': 'big_func',
                'code': 'def big_func():\n    ' + ' '.join(['code'] * 100),  # Lots of text
                'start_line': 1,
                'end_line': 2,
                'metadata': {'file_type': 'py'}
            }
        ]

        result = assembler.assemble_context(big_chunks)

        # Should respect budget
        self.assertLessEqual(result['total_tokens'], 50)

    def test_top_n_get_full_code(self):
        """Test top N chunks get full code, rest get summaries"""
        assembler = ContextAssembler(max_tokens=10000)

        # 5 chunks, top 2 should get full code
        chunks = [self.test_chunks[0].copy() for _ in range(5)]
        for i, chunk in enumerate(chunks):
            chunk['chunk_id'] = f'file{i}.py::func{i}::L{i}'

        result = assembler.assemble_context(chunks, include_full_code_top_n=2)

        context_text = "\n".join(result['context_parts'])

        # Top 2 should have code blocks (```)
        self.assertGreater(context_text.count('```'), 0)

        # Should have markdown headers for full code
        self.assertIn('##', context_text)

    def test_citations_extracted(self):
        """Test citations are tracked"""
        assembler = ContextAssembler()

        result = assembler.assemble_context(self.test_chunks)

        # Should have citations for both chunks
        self.assertEqual(len(result['citations']), 2)

        # Citation format: (file, start, end)
        cite1 = result['citations'][0]
        self.assertEqual(cite1[0], 'file1.py')
        self.assertEqual(cite1[1], 1)
        self.assertEqual(cite1[2], 2)

    def test_graph_highlights_tracked(self):
        """Test graph highlights are tracked"""
        assembler = ContextAssembler()

        result = assembler.assemble_context(self.test_chunks)

        # Should track chunk IDs for graph highlighting
        self.assertEqual(len(result['graph_highlights']), 2)
        self.assertIn('file1.py::func1::L1', result['graph_highlights'])
        self.assertIn('file2.py::func2::L10', result['graph_highlights'])


class TestCitationExtraction(unittest.TestCase):

    def test_extract_simple_citation(self):
        """Test extracting simple file:line citation"""
        response = "The function is in auth.py:42 and does authentication."

        citations = extract_citations_from_response(response)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]['file'], 'auth.py')
        self.assertEqual(citations[0]['start_line'], 42)
        self.assertEqual(citations[0]['end_line'], 42)

    def test_extract_range_citation(self):
        """Test extracting file:start-end citation"""
        response = "See the implementation in utils/auth.py:42-68 for details."

        citations = extract_citations_from_response(response)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]['file'], 'utils/auth.py')
        self.assertEqual(citations[0]['start_line'], 42)
        self.assertEqual(citations[0]['end_line'], 68)

    def test_extract_multiple_citations(self):
        """Test extracting multiple citations"""
        response = """
        Authentication works as follows:
        1. User login in auth/login.py:15-20
        2. Password verification in auth/password.py:42
        3. Token creation in auth/token.py:100-110
        """

        citations = extract_citations_from_response(response)

        self.assertEqual(len(citations), 3)
        self.assertEqual(citations[0]['file'], 'auth/login.py')
        self.assertEqual(citations[1]['file'], 'auth/password.py')
        self.assertEqual(citations[2]['file'], 'auth/token.py')

    def test_extract_no_citations(self):
        """Test handles response with no citations"""
        response = "I don't have enough information to answer that."

        citations = extract_citations_from_response(response)

        self.assertEqual(len(citations), 0)

    def test_extract_with_various_extensions(self):
        """Test works with different file extensions"""
        response = "See index.js:10, App.tsx:42-50, and utils.java:100"

        citations = extract_citations_from_response(response)

        self.assertEqual(len(citations), 3)
        self.assertEqual(citations[0]['file'], 'index.js')
        self.assertEqual(citations[1]['file'], 'App.tsx')
        self.assertEqual(citations[2]['file'], 'utils.java')


if __name__ == '__main__':
    unittest.main()
