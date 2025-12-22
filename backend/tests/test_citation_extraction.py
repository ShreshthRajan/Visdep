"""
Unit tests for citation extraction with both absolute and relative formats

Tests the fix for per-node query citation extraction.
"""

import pytest
from backend.api.reranker import extract_citations_from_response


class TestAbsoluteCitations:
    """Test absolute citation format (file.py:42-68) for generic queries"""

    def test_single_absolute_citation(self):
        response = "The function is defined in models.py:947-980"
        citations = extract_citations_from_response(response)

        assert len(citations) == 1
        assert citations[0]['file'] == 'models.py'
        assert citations[0]['start_line'] == 947
        assert citations[0]['end_line'] == 980

    def test_multiple_absolute_citations(self):
        response = """
        Check models.py:947-980 for JSON handling.
        Authentication is in auth.py:25-66.
        See also sessions.py:333-353 for redirects.
        """
        citations = extract_citations_from_response(response)

        assert len(citations) == 3
        assert citations[0]['file'] == 'models.py'
        assert citations[1]['file'] == 'auth.py'
        assert citations[2]['file'] == 'sessions.py'

    def test_single_line_citation(self):
        response = "See utils.py:42 for the implementation"
        citations = extract_citations_from_response(response)

        assert len(citations) == 1
        assert citations[0]['start_line'] == 42
        assert citations[0]['end_line'] == 42

    def test_file_with_path(self):
        response = "Check src/requests/models.py:100-200"
        citations = extract_citations_from_response(response)

        assert len(citations) == 1
        assert citations[0]['file'] == 'src/requests/models.py'


class TestRelativeCitations:
    """Test relative citation format (lines 25-35) for per-node queries"""

    def test_parenthesized_line_range(self):
        response = "**to_native_string() function (lines 25-35)**"
        node_context = {'chunk_id': '_internal_utils.py', 'name': '_internal_utils.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        assert len(citations) == 1
        assert citations[0]['file'] == '_internal_utils.py'
        assert citations[0]['start_line'] == 25
        assert citations[0]['end_line'] == 35

    def test_parenthesized_single_line(self):
        response = "**HEADER_VALIDATORS (line 19)**"
        node_context = {'chunk_id': '_internal_utils.py', 'name': '_internal_utils.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        assert len(citations) == 1
        assert citations[0]['file'] == '_internal_utils.py'
        assert citations[0]['start_line'] == 19
        assert citations[0]['end_line'] == 19

    def test_multiple_relative_citations(self):
        response = """
        **HEADER_VALIDATORS (line 19)**
        **to_native_string() function (lines 25-35)**
        **unicode_is_ascii() function (lines 38-50)**
        """
        node_context = {'chunk_id': 'src/requests/_internal_utils.py', 'name': '_internal_utils.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        assert len(citations) == 3
        assert all(c['file'] == 'src/requests/_internal_utils.py' for c in citations)
        assert citations[0]['start_line'] == 19
        assert citations[1]['start_line'] == 25
        assert citations[2]['start_line'] == 38

    def test_no_node_context_no_relative_extraction(self):
        """Without node_context, relative patterns should NOT be extracted"""
        response = "The function is at (lines 25-35)"

        citations = extract_citations_from_response(response, node_context=None)

        assert len(citations) == 0  # No absolute pattern, no node_context → no extraction

    def test_absolute_preferred_over_relative(self):
        """If absolute citations found, don't try relative extraction"""
        response = "See models.py:100-200. Also check (lines 25-35)"
        node_context = {'chunk_id': 'utils.py', 'name': 'utils.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        # Should only extract absolute citation, not relative
        assert len(citations) == 1
        assert citations[0]['file'] == 'models.py'


class TestEdgeCases:
    """Test edge cases and robustness"""

    def test_empty_response(self):
        citations = extract_citations_from_response("")
        assert len(citations) == 0

    def test_no_citations_in_response(self):
        response = "This code handles authentication for the library."
        citations = extract_citations_from_response(response)
        assert len(citations) == 0

    def test_malformed_line_numbers(self):
        response = "See file.py:abc-def"
        citations = extract_citations_from_response(response)
        assert len(citations) == 0  # Won't match due to non-numeric lines

    def test_case_insensitive_relative(self):
        """Relative patterns should be case-insensitive"""
        response = "Check (Line 19) and (LINES 25-35)"
        node_context = {'chunk_id': 'test.py', 'name': 'test.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        assert len(citations) == 2


class TestRealWorldScenarios:
    """Test with actual response formats from Claude"""

    def test_generic_query_response(self):
        """Simulate actual Claude response for generic query"""
        response = """
        Based on the provided code context, this appears to be part of the **Requests library**.

        ## Core HTTP Response Handling
        - **`Response.json()` (models.py:947-980)**: Decodes JSON response bodies
        - **`Response.iter_content()` (models.py:799-855)**: Streams response data
        - **`_basic_auth_str()` (auth.py:25-66)**: Creates Basic Auth headers
        """

        citations = extract_citations_from_response(response)

        assert len(citations) == 3
        assert citations[0]['file'] == 'models.py'
        assert citations[1]['file'] == 'models.py'
        assert citations[2]['file'] == 'auth.py'

    def test_per_node_query_response_with_absolute(self):
        """Per-node query where Claude follows format instruction"""
        response = """
        The `_internal_utils.py` file contains:

        **to_native_string() (_internal_utils.py:25-35)**
        **unicode_is_ascii() (_internal_utils.py:38-50)**
        """
        node_context = {'chunk_id': 'src/requests/_internal_utils.py', 'name': '_internal_utils.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        # Should extract absolute citations (Claude followed instructions)
        assert len(citations) == 2
        assert citations[0]['file'] == '_internal_utils.py'

    def test_per_node_query_response_with_relative(self):
        """Per-node query where Claude uses relative format (fallback case)"""
        response = """
        The `_internal_utils.py` file contains:

        **HEADER_VALIDATORS (line 19)**
        **to_native_string() function (lines 25-35)**
        **unicode_is_ascii() function (lines 38-50)**
        """
        node_context = {'chunk_id': 'src/requests/_internal_utils.py', 'name': '_internal_utils.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        # Should extract relative citations with filename from node_context
        assert len(citations) == 3
        assert all(c['file'] == 'src/requests/_internal_utils.py' for c in citations)
        assert citations[0]['start_line'] == 19
        assert citations[1]['start_line'] == 25
        assert citations[2]['start_line'] == 38


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])
