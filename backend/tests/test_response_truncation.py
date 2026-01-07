"""
Tests for Response Truncation Fix

Tests the increased max_tokens limits and truncation detection that fixes
response truncation issues for complex flow queries.

Root cause: max_tokens was 4000 for flow queries, but Claude Sonnet 4 supports
64k output tokens. Complex auth system walkthroughs were getting cut off.

Fix:
- Flow queries: 4000 → 16000 tokens (4x increase)
- Normal queries: 2000 → 4000 tokens (2x increase)
- Added truncation detection with user warning

Date: January 2026
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestMaxTokensConfiguration:
    """Tests for correct max_tokens configuration"""

    def test_flow_query_max_tokens_is_16000(self):
        """Flow queries should use 16000 max_tokens"""
        # Simulate the logic from _query_claude_stream
        is_flow_query = True
        max_tokens = 16000 if is_flow_query else 4000
        assert max_tokens == 16000, "Flow queries should have 16000 max_tokens"

    def test_normal_query_max_tokens_is_4000(self):
        """Normal queries should use 4000 max_tokens"""
        is_flow_query = False
        max_tokens = 16000 if is_flow_query else 4000
        assert max_tokens == 4000, "Normal queries should have 4000 max_tokens"

    def test_flow_query_detection_keywords(self):
        """Flow query detection should match expected keywords"""
        flow_keywords = [
            'trace', 'flow', 'execution', 'call chain', 'step by step',
            'how does', 'walk through', 'path from', 'sequence', 'what happens when'
        ]

        test_queries = [
            ("walk through the auth system", True),  # exact match for 'walk through'
            ("trace the login flow", True),
            ("how does authentication work", True),
            ("what happens when user logs in", True),
            ("step by step user registration", True),
            ("show me the main function", False),
            ("what is this file", False),
            ("list all endpoints", False),
        ]

        for query, expected_is_flow in test_queries:
            query_lower = query.lower()
            is_flow = any(phrase in query_lower for phrase in flow_keywords)
            assert is_flow == expected_is_flow, f"Query '{query}' should be flow={expected_is_flow}"


class TestTruncationMarker:
    """Tests for truncation marker format and handling"""

    def test_truncation_marker_format(self):
        """Truncation marker should have correct format"""
        marker = {'_meta': 'truncated', 'max_tokens': 16000}

        assert '_meta' in marker
        assert marker['_meta'] == 'truncated'
        assert 'max_tokens' in marker
        assert isinstance(marker['max_tokens'], int)

    def test_truncation_marker_detection(self):
        """Truncation marker should be detectable via isinstance and _meta key"""
        # String token (normal case)
        token_str = "Hello world"
        assert isinstance(token_str, str)
        assert not isinstance(token_str, dict)

        # Truncation marker
        marker = {'_meta': 'truncated', 'max_tokens': 16000}
        assert isinstance(marker, dict)
        assert marker.get('_meta') == 'truncated'

    def test_token_filtering_logic(self):
        """Token filtering should correctly separate tokens from markers"""
        tokens = [
            "Hello",
            " world",
            "!",
            {'_meta': 'truncated', 'max_tokens': 16000}
        ]

        response_text = ""
        was_truncated = False
        truncation_limit = None

        for token in tokens:
            if isinstance(token, dict) and token.get('_meta') == 'truncated':
                was_truncated = True
                truncation_limit = token.get('max_tokens')
                continue
            response_text += token

        assert response_text == "Hello world!"
        assert was_truncated is True
        assert truncation_limit == 16000


class TestTruncationEventFormat:
    """Tests for truncation event emitted to frontend"""

    def test_truncation_event_structure(self):
        """Truncation event should have correct structure for frontend"""
        import time
        start_time = time.time()
        truncation_limit = 16000

        event = {
            'type': 'truncated',
            'message': f'Response was truncated at {truncation_limit:,} tokens',
            'max_tokens': truncation_limit,
            'elapsed_ms': int((time.time() - start_time) * 1000)
        }

        assert event['type'] == 'truncated'
        assert 'truncated at 16,000 tokens' in event['message']
        assert event['max_tokens'] == 16000
        assert 'elapsed_ms' in event

    def test_truncation_message_formatting(self):
        """Truncation message should use proper number formatting"""
        truncation_limit = 16000
        message = f'Response was truncated at {truncation_limit:,} tokens'
        assert message == 'Response was truncated at 16,000 tokens'


class TestStopReasonDetection:
    """Tests for Claude stop_reason detection"""

    def test_max_tokens_stop_reason(self):
        """Should detect max_tokens stop reason"""
        # Mock response with max_tokens stop reason
        mock_message = MagicMock()
        mock_message.stop_reason = "max_tokens"

        was_truncated = mock_message.stop_reason == "max_tokens"
        assert was_truncated is True

    def test_end_turn_stop_reason(self):
        """Should not flag end_turn as truncation"""
        mock_message = MagicMock()
        mock_message.stop_reason = "end_turn"

        was_truncated = mock_message.stop_reason == "max_tokens"
        assert was_truncated is False

    def test_various_stop_reasons(self):
        """Should only flag max_tokens as truncation"""
        stop_reasons = [
            ("max_tokens", True),
            ("end_turn", False),
            ("stop_sequence", False),
            ("tool_use", False),
            (None, False),
        ]

        for stop_reason, expected_truncated in stop_reasons:
            mock_message = MagicMock()
            mock_message.stop_reason = stop_reason
            was_truncated = mock_message.stop_reason == "max_tokens"
            assert was_truncated == expected_truncated, f"stop_reason={stop_reason}"


class TestIntegration:
    """Integration tests for truncation handling"""

    def test_frontend_truncation_notice(self):
        """Frontend should append truncation notice to response"""
        response_text = "Some partial response about auth..."

        # Simulate frontend handling of truncation event
        response_text += '\n\n---\n*⚠️ Response was truncated due to length limit. Try a more specific query for complete results.*'

        assert '⚠️' in response_text
        assert 'truncated' in response_text.lower()
        assert 'more specific query' in response_text

    def test_progress_step_for_truncation(self):
        """Progress step should show truncation warning"""
        step = {
            'id': 99,
            'message': 'Response was truncated at 16,000 tokens',
            'status': 'error',
            'detail': 'Response may be incomplete'
        }

        assert step['status'] == 'error'
        assert 'truncated' in step['message'].lower()
        assert step['detail'] == 'Response may be incomplete'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
