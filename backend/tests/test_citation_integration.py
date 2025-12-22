"""
Integration test for citation extraction in full query pipeline

Verifies that per-node queries correctly extract citations and return highlighted_nodes.
"""

import pytest
from backend.api.reranker import extract_citations_from_response


class TestCitationIntegration:
    """Test citation extraction with real Claude response formats"""

    def test_per_node_query_extraction_with_relative_format(self):
        """
        Test extraction from actual per-node query response
        Simulates the exact response format Claude produces
        """
        # Actual response from Claude for per-node query about _internal_utils.py
        response = """The `_internal_utils.py` file contains internal utility functions for the Requests library that handle string encoding and validation operations.

## Key Components:

**HEADER_VALIDATORS (line 19)**
- A dictionary mapping data types (`bytes` and `str`) to their respective header validation functions
- References `_HEADER_VALIDATORS_BYTE` and `_HEADER_VALIDATORS_STR` (defined elsewhere in the module)

**to_native_string() function (lines 25-35)**
- Converts any string object to the native string type for the current Python version
- Takes a `string` parameter and optional `encoding` (defaults to "ascii")
- If the input is already a `builtin_str`, returns it unchanged
- Otherwise, decodes the string using the specified encoding
- Handles the complexity of string type differences across Python versions

**unicode_is_ascii() function (lines 38-50)**
- Determines whether a Unicode string contains only ASCII characters
- Takes a `u_string` parameter that must be a Unicode string (Python 3 `str`)
- Uses a try/except approach: attempts to encode the string as ASCII
- Returns `True` if encoding succeeds, `False` if a `UnicodeEncodeError` occurs
- Includes an assertion to ensure the input is actually a string type

This module essentially provides low-level string handling utilities that help the Requests library manage text encoding consistently across different scenarios and Python environments."""

        # Simulate node_context from per-node query
        node_context = {
            'chunk_id': 'src/requests/_internal_utils.py',
            'name': '_internal_utils.py',
            'type': 'file'
        }

        # Extract citations with node context
        citations = extract_citations_from_response(response, node_context)

        # Should extract 3 citations: line 19, lines 25-35, lines 38-50
        assert len(citations) == 3, f"Expected 3 citations, got {len(citations)}"

        # Verify they're in text order (not pattern order)
        assert citations[0]['start_line'] == 19
        assert citations[0]['end_line'] == 19
        assert citations[0]['file'] == 'src/requests/_internal_utils.py'

        assert citations[1]['start_line'] == 25
        assert citations[1]['end_line'] == 35
        assert citations[1]['file'] == 'src/requests/_internal_utils.py'

        assert citations[2]['start_line'] == 38
        assert citations[2]['end_line'] == 50
        assert citations[2]['file'] == 'src/requests/_internal_utils.py'

    def test_generic_query_still_works(self):
        """
        Verify generic queries (without node_context) still work
        Regression test to ensure we didn't break existing functionality
        """
        # Actual response from Claude for generic query
        response = """Based on the provided code context, this appears to be part of the **Requests library**.

## Core HTTP Response Handling
- **`Response.json()` (models.py:947-980)**: Decodes JSON response bodies
- **`Response.iter_content()` (models.py:799-855)**: Streams response data in chunks
- **`_basic_auth_str()` (auth.py:25-66)**: Creates HTTP Basic Authentication headers"""

        # No node_context (generic query)
        citations = extract_citations_from_response(response, node_context=None)

        # Should extract 3 absolute citations
        assert len(citations) == 3
        assert citations[0]['file'] == 'models.py'
        assert citations[1]['file'] == 'models.py'
        assert citations[2]['file'] == 'auth.py'

    def test_per_node_with_absolute_format(self):
        """
        Test when Claude follows the new prompt instruction and uses absolute format
        This is the ideal case after the prompt fix
        """
        response = """The `_internal_utils.py` file contains:

**HEADER_VALIDATORS (_internal_utils.py:19)**
**to_native_string() (_internal_utils.py:25-35)**
**unicode_is_ascii() (_internal_utils.py:38-50)**"""

        node_context = {
            'chunk_id': 'src/requests/_internal_utils.py',
            'name': '_internal_utils.py',
            'type': 'file'
        }

        citations = extract_citations_from_response(response, node_context)

        # Should extract absolute citations (not use fallback)
        assert len(citations) == 3
        assert citations[0]['file'] == '_internal_utils.py'

    def test_mixed_formats_prioritizes_absolute(self):
        """
        If response has BOTH absolute and relative, use only absolute
        """
        response = """
        Check models.py:100-200 for details.
        Also see (line 42) in the same file.
        """
        node_context = {'chunk_id': 'models.py', 'name': 'models.py', 'type': 'file'}

        citations = extract_citations_from_response(response, node_context)

        # Should only extract absolute (models.py:100-200), not relative
        assert len(citations) == 1
        assert citations[0]['file'] == 'models.py'
        assert citations[0]['start_line'] == 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
