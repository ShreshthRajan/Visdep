# backend/api/reranker.py

"""
Cross-Encoder Reranking and Context Assembly for Step 3

Based on research:
- Cross-encoders: 10-15% improvement over bi-encoders (2025 papers)
- Context sufficiency: 6K tokens of relevant > 128K tokens of noise (Google Research)
- Citations: Enable verification and trust
"""

import logging
import os
from typing import List, Dict, Any, Tuple
from sentence_transformers import CrossEncoder
import re
import tiktoken


class CodeReranker:
    """
    Cross-encoder based reranking for code chunks

    2025 Update: Upgraded to code-optimized reranker
    """

    def __init__(self, model_name: str = None):
        """
        Initialize cross-encoder reranker

        Args:
            model_name: HuggingFace model name for cross-encoder
                       Default: mixedbread-ai/mxbai-rerank-base-v1 (2025, code-optimized)
                       Fallback: cross-encoder/ms-marco-MiniLM-L-6-v2 (2023, fast)
                       Alternative: jinaai/jina-reranker-v2-base-multilingual
        """
        # Use env var or default to 2025 code-optimized model
        if model_name is None:
            model_name = os.getenv('RERANKER_MODEL', 'mixedbread-ai/mxbai-rerank-base-v1')

        try:
            self.model = CrossEncoder(model_name)
            logging.info(f"✅ CodeReranker initialized with model: {model_name}")
        except Exception as e:
            # Fallback to reliable ms-marco if new model fails
            logging.warning(f"⚠️ Failed to load {model_name}: {e}")
            logging.warning(f"⚠️ Falling back to cross-encoder/ms-marco-MiniLM-L-6-v2")
            self.model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
            logging.info(f"✅ CodeReranker initialized with fallback model")

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Rerank chunks using cross-encoder

        Args:
            query: User query
            chunks: List of chunks to rerank
            top_k: Number of top chunks to return

        Returns:
            Reranked list of chunks with scores
        """
        if not chunks:
            return []

        logging.info(f"🔄 RERANKER DEBUG: Reranking {len(chunks)} chunks for query: '{query}'")

        # Log input chunks before reranking
        logging.info(f"   Input chunks before reranking:")
        for i, chunk in enumerate(chunks[:5], 1):
            logging.info(f"     {i}. {chunk['name']} in {chunk['file_path']}:{chunk.get('start_line', '?')}")

        # Create (query, chunk) pairs for cross-encoder
        pairs = []
        for chunk in chunks:
            # Combine chunk metadata for better reranking
            chunk_text = f"{chunk['name']} in {chunk['file_path']}\n{chunk['code']}"
            pairs.append([query, chunk_text])

        # Score all pairs
        scores = self.model.predict(pairs)

        # Combine chunks with scores
        scored_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_copy = chunk.copy()
            chunk_copy['rerank_score'] = float(scores[i])
            scored_chunks.append(chunk_copy)

        # Sort by rerank score (descending)
        scored_chunks.sort(key=lambda x: x['rerank_score'], reverse=True)

        # Return top-k
        top_chunks = scored_chunks[:top_k]

        logging.info(f"✅ Reranked {len(chunks)} chunks to top {len(top_chunks)}")

        # Log reranked results
        logging.info(f"   Top 3 after reranking:")
        for i, chunk in enumerate(top_chunks[:3], 1):
            score = chunk.get('rerank_score', 0)
            logging.info(f"     {i}. {chunk['name']} (score: {score:.3f}) in {chunk['file_path']}:{chunk.get('start_line', '?')}")

        return top_chunks


class ContextAssembler:
    """
    Smart context assembly with token budget management
    """

    def __init__(self, max_tokens: int = 6000):
        """
        Initialize context assembler

        Args:
            max_tokens: Maximum tokens for LLM context (default 6000)
        """
        self.max_tokens = max_tokens
        # Initialize tiktoken encoder for accurate token counting
        try:
            self.encoder = tiktoken.encoding_for_model("gpt-4")
            logging.info(f"ContextAssembler initialized with tiktoken encoder")
        except Exception as e:
            logging.warning(f"Tiktoken init failed: {e}, falling back to word-based estimation")
            self.encoder = None
        logging.info(f"ContextAssembler initialized with max_tokens={max_tokens}")

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using tiktoken (accurate) or word-based fallback

        Args:
            text: Text to estimate

        Returns:
            Accurate token count
        """
        # Use tiktoken for accurate counting (33% more accurate than word-based)
        if self.encoder:
            try:
                return len(self.encoder.encode(text))
            except Exception as e:
                logging.debug(f"Tiktoken encoding failed: {e}, using fallback")

        # Fallback: word-based estimation (conservative)
        words = len(text.split())
        return int(words / 0.6)

    def assemble_context(
        self,
        chunks: List[Dict[str, Any]],
        include_full_code_top_n: int = 5
    ) -> Dict[str, Any]:
        """
        Assemble context with token budget

        Args:
            chunks: Reranked chunks (ordered by relevance)
            include_full_code_top_n: Number of top chunks to include full code

        Returns:
            {
                'context_parts': List of formatted context parts,
                'citations': List of (file, line_range) tuples,
                'graph_highlights': List of chunk IDs to highlight,
                'total_tokens': Token count
            }
        """
        context_parts = []
        citations = []
        graph_highlights = []
        total_tokens = 0

        for i, chunk in enumerate(chunks):
            # Top N: include full code
            if i < include_full_code_top_n:
                content = self._format_full_chunk(chunk)
                citation = (chunk['file_path'], chunk['start_line'], chunk['end_line'])

            # Rest: include summary only
            else:
                content = self._format_summary(chunk)
                citation = (chunk['file_path'], chunk['start_line'], chunk['end_line'])

            # Check token budget
            content_tokens = self.estimate_tokens(content)

            if total_tokens + content_tokens > self.max_tokens:
                logging.info(f"Token budget reached at chunk {i}/{len(chunks)}")
                break

            context_parts.append(content)
            citations.append(citation)
            graph_highlights.append(chunk['chunk_id'])
            total_tokens += content_tokens

        result = {
            'context_parts': context_parts,
            'citations': citations,
            'graph_highlights': graph_highlights,
            'total_tokens': total_tokens,
            'chunks_included': len(context_parts)
        }

        logging.info(f"Assembled context: {len(context_parts)} chunks, {total_tokens} tokens")
        return result

    def _format_full_chunk(self, chunk: Dict[str, Any]) -> str:
        """Format chunk with full code"""
        file_ref = f"{chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']}"

        content = f"## {file_ref} - {chunk['name']}\n"
        content += f"**Type:** {chunk['type']}\n\n"
        content += f"```{chunk['metadata'].get('file_type', 'python')}\n"
        content += f"{chunk['code']}\n"
        content += f"```\n\n"

        return content

    def _format_summary(self, chunk: Dict[str, Any]) -> str:
        """Format chunk as summary with signature + first body line"""
        file_ref = f"{chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']}"

        # Extract signature and first body line for context
        lines = chunk['code'].split('\n')
        signature = lines[0].strip() if lines else ""

        # Get first non-empty, non-comment body line
        first_body_line = ""
        for line in lines[1:3]:  # Check next 2 lines
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and not stripped.startswith('"""'):
                first_body_line = stripped
                break

        content = f"- **{chunk['name']}** ({chunk['type']}) in {file_ref}\n"
        content += f"  `{signature[:80]}...`\n"
        if first_body_line:
            content += f"  `{first_body_line[:80]}...`\n"

        return content


def extract_citations_from_response(response: str, node_context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Extract file:line citations from LLM response

    Supports two formats:
    1. Absolute: file.py:42-68 (for generic queries)
    2. Relative: (lines 25-35) or (line 19) (for per-node queries with fallback)

    Args:
        response: LLM response text
        node_context: Optional node context for per-node queries (provides filename for relative citations)

    Returns:
        List of citation dictionaries
    """
    citations = []

    # Pattern 1: Absolute citations (file.py:42-68)
    absolute_pattern = r'([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]+):(\d+)(?:-(\d+))?'

    for match in re.finditer(absolute_pattern, response):
        file_path = match.group(1)
        start_line = int(match.group(2))
        end_line = int(match.group(3)) if match.group(3) else start_line

        citations.append({
            'file': file_path,
            'start_line': start_line,
            'end_line': end_line,
            'text': match.group(0)
        })

    # Pattern 2: Relative citations (fallback for per-node queries)
    # Only use if: (1) no absolute citations found AND (2) node_context provided
    if len(citations) == 0 and node_context and node_context.get('chunk_id'):
        filename = node_context['chunk_id']

        # Relative patterns: (line 19), (lines 25-35), line 42, lines 25-35
        relative_patterns = [
            (r'\(lines?\s+(\d+)-(\d+)\)', True),   # (lines 25-35) or (line 25-35)
            (r'\(line\s+(\d+)\)', False),          # (line 19)
            (r'(?:^|\s)lines?\s+(\d+)-(\d+)', True),  # lines 25-35 (not in parens)
            (r'(?:^|\s)line\s+(\d+)(?:\s|$)', False)  # line 42 (not in parens)
        ]

        # Collect all matches with their positions (for sorting)
        matches_with_positions = []

        for pattern, is_range in relative_patterns:
            for match in re.finditer(pattern, response, re.IGNORECASE):
                if is_range:
                    start_line = int(match.group(1))
                    end_line = int(match.group(2))
                else:
                    start_line = int(match.group(1))
                    end_line = start_line

                matches_with_positions.append({
                    'file': filename,
                    'start_line': start_line,
                    'end_line': end_line,
                    'text': match.group(0).strip(),
                    'position': match.start()  # Position in response text
                })

        # Sort by position in response (maintain text order)
        matches_with_positions.sort(key=lambda x: x['position'])

        # Remove position field and add to citations
        for match_data in matches_with_positions:
            citations.append({
                'file': match_data['file'],
                'start_line': match_data['start_line'],
                'end_line': match_data['end_line'],
                'text': match_data['text']
            })

    return citations
