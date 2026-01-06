"""
Tests for Query Enhancement Module

Tests the SOTA LLM-based query intent language detection that fixes
language mismatch in query expansion.

Research basis:
- "User intent understanding goes beyond traditional keyword matching"
  (Knowledge-Oriented RAG Survey, 2025)
- MIND-RAG (ICCV 2025): Intent detection guides modality selection

Date: January 2026
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.api.query_enhancement import (
    detect_primary_language,
    detect_query_intent_language,
    detect_query_intent_language_llm,
    get_language_specific_terms,
    _QUERY_INTENT_CACHE
)


class TestDetectQueryIntentLanguageHeuristic:
    """Tests for the fast heuristic-based fallback (synchronous)"""

    # =========================================================================
    # HIGH-CONFIDENCE FRONTEND SIGNALS
    # =========================================================================

    def test_react_keyword_overrides_python(self):
        """React keyword should override Python codebase language"""
        result = detect_query_intent_language(
            "give me complete set of rest endpoints used in frontend react hooks",
            "python"
        )
        assert result == "javascript", "React query should use JavaScript, not Python"

    def test_vue_keyword_overrides_python(self):
        """Vue keyword should use JavaScript"""
        result = detect_query_intent_language("vue components", "python")
        assert result == "javascript"

    def test_angular_keyword_overrides_rust(self):
        """Angular keyword should use JavaScript"""
        result = detect_query_intent_language("angular services", "rust")
        assert result == "javascript"

    def test_webpack_keyword(self):
        """Webpack keyword should use JavaScript"""
        result = detect_query_intent_language("webpack config", "python")
        assert result == "javascript"

    def test_npm_keyword(self):
        """NPM keyword should use JavaScript"""
        result = detect_query_intent_language("npm scripts", "python")
        assert result == "javascript"

    # =========================================================================
    # HIGH-CONFIDENCE BACKEND SIGNALS
    # =========================================================================

    def test_flask_keyword_overrides_javascript(self):
        """Flask keyword should use Python"""
        result = detect_query_intent_language(
            "where are the Flask routes defined",
            "javascript"
        )
        assert result == "python"

    def test_fastapi_keyword_overrides_javascript(self):
        """FastAPI keyword should use Python"""
        result = detect_query_intent_language(
            "show me the FastAPI endpoints",
            "javascript"
        )
        assert result == "python"

    def test_django_keyword(self):
        """Django keyword should use Python"""
        result = detect_query_intent_language("django models", "javascript")
        assert result == "python"

    # =========================================================================
    # HIGH-CONFIDENCE RUST SIGNALS
    # =========================================================================

    def test_cargo_keyword_uses_rust(self):
        """Cargo keyword should use Rust"""
        result = detect_query_intent_language(
            "how does cargo resolve dependencies",
            "python"
        )
        assert result == "rust"

    def test_tokio_keyword_uses_rust(self):
        """Tokio keyword should use Rust"""
        result = detect_query_intent_language(
            "explain the tokio async runtime",
            "c"
        )
        assert result == "rust"

    # =========================================================================
    # CONTEXTUAL FRONTEND INDICATOR
    # =========================================================================

    def test_frontend_keyword_overrides_python(self):
        """Frontend keyword should override Python codebase to JavaScript"""
        result = detect_query_intent_language(
            "list all endpoints used in frontend",
            "python"
        )
        assert result == "javascript"

    def test_frontend_keyword_overrides_php(self):
        """Frontend keyword should override PHP codebase to JavaScript"""
        result = detect_query_intent_language(
            "frontend components",
            "php"
        )
        assert result == "javascript"

    def test_frontend_does_not_override_javascript(self):
        """Frontend keyword should NOT override JavaScript codebase"""
        result = detect_query_intent_language(
            "frontend components",
            "javascript"
        )
        assert result == "javascript"

    # =========================================================================
    # FALLBACK TO CODEBASE LANGUAGE
    # =========================================================================

    def test_generic_query_uses_codebase_python(self):
        """Generic query should use codebase language"""
        result = detect_query_intent_language(
            "how does authentication work",
            "python"
        )
        assert result == "python"

    def test_generic_query_uses_codebase_rust(self):
        """Generic query in Rust codebase should use Rust"""
        result = detect_query_intent_language(
            "show me the error handling",
            "rust"
        )
        assert result == "rust"

    def test_generic_query_uses_codebase_go(self):
        """Generic query in Go codebase should use Go"""
        result = detect_query_intent_language(
            "explain the main function",
            "go"
        )
        assert result == "go"

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_empty_query_uses_codebase(self):
        """Empty query should use codebase language"""
        result = detect_query_intent_language("", "python")
        assert result == "python"


class TestDetectQueryIntentLanguageLLM:
    """Tests for the SOTA LLM-based detection (async)"""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Create a mock Anthropic client"""
        client = MagicMock()
        return client

    def test_llm_detection_frontend_query(self, mock_anthropic_client):
        """LLM should detect JavaScript for frontend query"""
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="javascript")]
        mock_anthropic_client.messages.create.return_value = mock_response

        # Clear cache
        _QUERY_INTENT_CACHE.clear()

        result = asyncio.run(detect_query_intent_language_llm(
            query="frontend react hooks API calls",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        assert result == "javascript"
        mock_anthropic_client.messages.create.assert_called_once()

    def test_llm_detection_backend_query(self, mock_anthropic_client):
        """LLM should detect Python for Flask query"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="python")]
        mock_anthropic_client.messages.create.return_value = mock_response

        _QUERY_INTENT_CACHE.clear()

        result = asyncio.run(detect_query_intent_language_llm(
            query="Flask API routes",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        assert result == "python"

    def test_llm_detection_generic_query_uses_primary(self, mock_anthropic_client):
        """LLM should use primary language for generic query"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="python")]  # LLM returns primary
        mock_anthropic_client.messages.create.return_value = mock_response

        _QUERY_INTENT_CACHE.clear()

        result = asyncio.run(detect_query_intent_language_llm(
            query="how does authentication work",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        assert result == "python"

    def test_llm_detection_validates_against_codebase(self, mock_anthropic_client):
        """LLM result should be validated against codebase languages"""
        # LLM returns a language not in codebase
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="kotlin")]  # Not in codebase
        mock_anthropic_client.messages.create.return_value = mock_response

        _QUERY_INTENT_CACHE.clear()

        result = asyncio.run(detect_query_intent_language_llm(
            query="some query",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        # Should fall back to primary (python has most files)
        assert result == "python"

    def test_llm_detection_handles_aliases(self, mock_anthropic_client):
        """LLM result aliases should be normalized"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="js")]  # Alias for javascript
        mock_anthropic_client.messages.create.return_value = mock_response

        _QUERY_INTENT_CACHE.clear()

        result = asyncio.run(detect_query_intent_language_llm(
            query="frontend components",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        assert result == "javascript"

    def test_llm_detection_caching(self, mock_anthropic_client):
        """Results should be cached"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="javascript")]
        mock_anthropic_client.messages.create.return_value = mock_response

        _QUERY_INTENT_CACHE.clear()

        # First call
        result1 = asyncio.run(detect_query_intent_language_llm(
            query="react hooks",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=True
        ))

        # Second call with same query
        result2 = asyncio.run(detect_query_intent_language_llm(
            query="react hooks",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=True
        ))

        assert result1 == result2 == "javascript"
        # Should only be called once due to caching
        assert mock_anthropic_client.messages.create.call_count == 1

    def test_llm_detection_fallback_on_error(self, mock_anthropic_client):
        """Should fall back to primary on LLM error"""
        mock_anthropic_client.messages.create.side_effect = Exception("API Error")

        _QUERY_INTENT_CACHE.clear()

        result = asyncio.run(detect_query_intent_language_llm(
            query="some query",
            codebase_languages={"python": 100, "javascript": 20},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        # Should fall back to primary language
        assert result == "python"


class TestDetectPrimaryLanguage:
    """Tests for codebase language detection from chunks"""

    def test_python_chunks(self):
        """Python chunks should detect Python"""
        chunks = [
            {'metadata': {'file_type': 'py'}},
            {'metadata': {'file_type': 'py'}},
            {'metadata': {'file_type': 'py'}},
        ]
        result = detect_primary_language(chunks)
        assert result == "python"

    def test_javascript_chunks(self):
        """JavaScript chunks should detect JavaScript"""
        chunks = [
            {'metadata': {'file_type': 'js'}},
            {'metadata': {'file_type': 'js'}},
        ]
        result = detect_primary_language(chunks)
        assert result == "javascript"

    def test_rust_chunks(self):
        """Rust chunks should detect Rust"""
        chunks = [
            {'metadata': {'file_type': 'rs'}},
            {'metadata': {'file_type': 'rs'}},
        ]
        result = detect_primary_language(chunks)
        assert result == "rust"

    def test_mixed_chunks_majority_wins(self):
        """Mixed chunks should detect majority language"""
        chunks = [
            {'metadata': {'file_type': 'py'}},
            {'metadata': {'file_type': 'py'}},
            {'metadata': {'file_type': 'py'}},
            {'metadata': {'file_type': 'js'}},
        ]
        result = detect_primary_language(chunks)
        assert result == "python"

    def test_empty_chunks(self):
        """Empty chunks should return unknown"""
        result = detect_primary_language([])
        assert result == "unknown"


class TestGetLanguageSpecificTerms:
    """Tests for language-specific term expansion"""

    def test_python_api_terms(self):
        """Python API query should get Flask/FastAPI terms"""
        result = get_language_specific_terms("api endpoint", "python")
        assert "flask" in result.lower() or "fastapi" in result.lower()

    def test_javascript_async_terms(self):
        """JavaScript async query should get promise terms"""
        result = get_language_specific_terms("async function", "javascript")
        assert "promise" in result.lower() or "await" in result.lower()

    def test_rust_search_terms(self):
        """Rust search query should get walk terms"""
        result = get_language_specific_terms("recursive search", "rust")
        assert "walk" in result.lower()


class TestIntegrationScenarios:
    """Integration tests simulating real user queries"""

    def test_original_bug_scenario_heuristic(self):
        """
        Original bug: User asked for frontend endpoints in Python codebase.
        System added Python terms (flask, fastapi) which hurt JS retrieval.
        """
        query = "give me complete set of rest endpoints used in frontend react hooks"
        codebase_lang = "python"

        # Heuristic fallback should detect "react"
        effective_lang = detect_query_intent_language(query, codebase_lang)
        assert effective_lang == "javascript", \
            "Bug scenario: Frontend query in Python codebase should use JavaScript"

    def test_backend_query_in_fullstack_repo(self):
        """
        User asks about backend in a fullstack repo detected as JavaScript.
        System should use Python terms for backend query.
        """
        query = "how does the Flask backend handle user sessions"
        codebase_lang = "javascript"

        effective_lang = detect_query_intent_language(query, codebase_lang)
        assert effective_lang == "python", \
            "Flask query should use Python even in JS codebase"

    def test_generic_query_uses_codebase(self):
        """
        Generic query without technology keywords uses codebase language.
        """
        query = "explain the authentication flow"
        codebase_lang = "rust"

        effective_lang = detect_query_intent_language(query, codebase_lang)
        assert effective_lang == "rust", \
            "Generic query should use codebase language (Rust)"


class TestLLMPromptQuality:
    """Tests to verify LLM prompt produces good results"""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Create a mock Anthropic client"""
        client = MagicMock()
        return client

    def test_prompt_includes_codebase_distribution(self, mock_anthropic_client):
        """LLM prompt should include codebase language distribution"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="python")]
        mock_anthropic_client.messages.create.return_value = mock_response

        _QUERY_INTENT_CACHE.clear()

        asyncio.run(detect_query_intent_language_llm(
            query="test query",
            codebase_languages={"python": 100, "javascript": 50, "rust": 10},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        # Verify the prompt includes language distribution
        call_args = mock_anthropic_client.messages.create.call_args
        prompt = call_args.kwargs['messages'][0]['content']

        assert "python" in prompt.lower()
        assert "javascript" in prompt.lower()
        assert "100" in prompt or "files" in prompt

    def test_prompt_specifies_primary_language(self, mock_anthropic_client):
        """LLM prompt should tell it what the primary language is"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="python")]
        mock_anthropic_client.messages.create.return_value = mock_response

        _QUERY_INTENT_CACHE.clear()

        asyncio.run(detect_query_intent_language_llm(
            query="generic query",
            codebase_languages={"rust": 200, "python": 10},
            anthropic_client=mock_anthropic_client,
            use_cache=False
        ))

        call_args = mock_anthropic_client.messages.create.call_args
        prompt = call_args.kwargs['messages'][0]['content']

        # Rust should be mentioned as primary (200 > 10)
        assert "rust" in prompt.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
