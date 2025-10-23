# backend/api/reranker.py

"""
Cross-Encoder Reranking and Context Assembly for Step 3

Based on research:
- Cross-encoders: 10-15% improvement over bi-encoders (2025 papers)
- Context sufficiency: 6K tokens of relevant > 128K tokens of noise (Google Research)
- Citations: Enable verification and trust
"""

import logging
from typing import List, Dict, Any, Tuple
from sentence_transformers import CrossEncoder
import re


class CodeReranker:
    """
    Cross-encoder based reranking for code chunks
    """

    def __init__(self, model_name: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2'):
        """
        Initialize cross-encoder reranker

        Args:
            model_name: HuggingFace model name for cross-encoder
                       Default: ms-marco-MiniLM-L-6-v2 (fast, good quality)
                       Alternative: jinaai/jina-reranker-v2-base-multilingual
        """
        self.model = CrossEncoder(model_name)
        logging.info(f"CodeReranker initialized with model: {model_name}")

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

        logging.info(f"Reranked {len(chunks)} chunks to top {len(top_chunks)}")
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
        logging.info(f"ContextAssembler initialized with max_tokens={max_tokens}")

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count (rough approximation)

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Rough estimate: 1 token ≈ 0.75 words
        # For code: more conservative, 1 token ≈ 0.6 words
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
        """Format chunk as summary (no full code)"""
        file_ref = f"{chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']}"

        # Extract first line of code (signature) or docstring
        first_line = chunk['code'].split('\n')[0].strip()

        content = f"- **{chunk['name']}** ({chunk['type']}) in {file_ref}\n"

        if first_line:
            content += f"  `{first_line[:100]}...`\n"

        return content


def extract_citations_from_response(response: str) -> List[Dict[str, Any]]:
    """
    Extract file:line citations from LLM response

    Args:
        response: LLM response text

    Returns:
        List of citation dictionaries
    """
    # Pattern: file.py:42-68 or file.py:42
    pattern = r'([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]+):(\d+)(?:-(\d+))?'

    citations = []
    for match in re.finditer(pattern, response):
        file_path = match.group(1)
        start_line = int(match.group(2))
        end_line = int(match.group(3)) if match.group(3) else start_line

        citations.append({
            'file': file_path,
            'start_line': start_line,
            'end_line': end_line,
            'text': match.group(0)
        })

    return citations
