# backend/api/hybrid_retrieval.py

"""
Hybrid Retrieval System for Code Chunks
Combines BM25 keyword search + dense vector search + graph expansion

Based on research:
- BM25 + Dense fusion: 15-30% improvement (2025 papers)
- Graph expansion: 35.57 point improvement (CodeRAG paper)
- RRF: proven fusion algorithm
"""

import logging
from typing import List, Dict, Any, Tuple
from rank_bm25 import BM25Okapi
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


class HybridRetriever:
    """
    Hybrid retrieval combining BM25, vector search, and graph expansion
    """

    def __init__(self, chunks: List[Dict[str, Any]], vector_store, chunk_graph: nx.DiGraph):
        """
        Initialize hybrid retriever

        Args:
            chunks: List of all chunks
            vector_store: FAISS vector store
            chunk_graph: NetworkX graph of chunk dependencies
        """
        self.chunks = chunks
        self.vector_store = vector_store
        self.chunk_graph = chunk_graph

        # Build lookup index
        self.chunk_index = {chunk['chunk_id']: chunk for chunk in chunks}

        # Build BM25 index
        self._build_bm25_index()

        # Precompute PageRank
        self._compute_pagerank()

        logging.info(f"HybridRetriever initialized with {len(chunks)} chunks")

    def _build_bm25_index(self):
        """
        Build BM25 index with optimized tokenization for code search.

        Enhancements:
        - Name boosting: Repeat chunk name for higher BM25 scores
        - Keyword expansion: Include parent class, method name separately
        - Smart tokenization: Strip punctuation, handle camelCase
        """
        corpus = []
        self.chunk_ids = []

        for chunk in self.chunks:
            # Extract keywords for better matching
            keywords = [chunk['name']]  # Full name: 'Session.request'

            # Add parent class if it's a method
            if chunk.get('metadata', {}).get('parent_class'):
                parent = chunk['metadata']['parent_class']
                keywords.append(parent)  # 'Session'

                # Add method name without class
                if '.' in chunk['name']:
                    method_only = chunk['name'].split('.')[-1]
                    keywords.append(method_only)  # 'request'

            # Add type for semantic search
            keywords.append(chunk['type'])  # 'method', 'function', etc.

            # Name boosting: Repeat name 5x for higher BM25 score
            # This ensures name matches rank higher than code content matches
            name_boosted = (chunk['name'] + " ") * 5

            # Combine: boosted name + keywords + file path + code
            text = f"{name_boosted}{' '.join(keywords)} {chunk['file_path']} {chunk['code']}"
            corpus.append(text)
            self.chunk_ids.append(chunk['chunk_id'])

        # Tokenize corpus with smart tokenization
        tokenized_corpus = [self._tokenize_for_bm25(doc) for doc in corpus]

        # Build BM25 index
        self.bm25 = BM25Okapi(tokenized_corpus)

        logging.info(f"BM25 index built with {len(corpus)} documents")

    def _tokenize_for_bm25(self, text: str) -> List[str]:
        """
        Smart tokenization for BM25 that handles code-specific patterns.

        - Strips punctuation: 'Session.request()' → 'session' 'request'
        - Handles camelCase: 'HTTPAdapter' → 'http' 'adapter'
        - Preserves dotted names: Also keeps 'session.request' as full token
        """
        import re

        # Lowercase
        text = text.lower()

        # Extract dotted names as full tokens (preserve 'session.request')
        dotted_pattern = r'\b\w+\.\w+\b'
        dotted_names = re.findall(dotted_pattern, text)

        # Standard word tokenization (splits on punctuation and whitespace)
        # This breaks 'Session.request()' → 'session', 'request'
        word_pattern = r'\b[a-z_][a-z0-9_]*\b'
        words = re.findall(word_pattern, text)

        # Combine: dotted names (full) + individual words
        # This gives us BOTH 'session.request' AND 'session', 'request'
        tokens = dotted_names + words

        return tokens

    def _compute_pagerank(self):
        """Precompute PageRank centrality scores"""
        if self.chunk_graph and len(self.chunk_graph.nodes()) > 0:
            self.pagerank_scores = nx.pagerank(self.chunk_graph)
            logging.info(f"PageRank computed for {len(self.pagerank_scores)} nodes")
        else:
            self.pagerank_scores = {}
            logging.warning("No chunk graph available, PageRank disabled")

    def bm25_search(self, query: str, top_k: int = 100) -> List[Tuple[str, float]]:
        """
        BM25 keyword search with smart query tokenization.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of (chunk_id, score) tuples
        """
        # Use same smart tokenization as indexing
        tokenized_query = self._tokenize_for_bm25(query)

        scores = self.bm25.get_scores(tokenized_query)

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = [(self.chunk_ids[i], scores[i]) for i in top_indices if scores[i] > 0]

        logging.debug(f"BM25 search returned {len(results)} results")
        return results

    def vector_search(self, query: str, top_k: int = 100) -> List[Tuple[str, float]]:
        """
        Dense vector similarity search

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of (chunk_id, score) tuples
        """
        # Use FAISS vector store
        docs_and_scores = self.vector_store.similarity_search_with_score(query, k=top_k)

        results = []
        for doc, score in docs_and_scores:
            chunk_id = doc.metadata.get('chunk_id')
            if chunk_id:
                # FAISS returns distance (lower is better), convert to similarity
                similarity = 1 / (1 + score)
                results.append((chunk_id, similarity))

        logging.debug(f"Vector search returned {len(results)} results")
        return results

    def reciprocal_rank_fusion(
        self,
        bm25_results: List[Tuple[str, float]],
        vector_results: List[Tuple[str, float]],
        k: int = 60
    ) -> List[Tuple[str, float]]:
        """
        Reciprocal Rank Fusion algorithm

        Args:
            bm25_results: BM25 ranked results
            vector_results: Vector ranked results
            k: RRF parameter (default 60)

        Returns:
            Fused ranked list
        """
        scores = {}

        # Add BM25 scores
        for rank, (chunk_id, _) in enumerate(bm25_results):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank + 1)

        # Add vector scores
        for rank, (chunk_id, _) in enumerate(vector_results):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank + 1)

        # Sort by fused score
        fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        logging.debug(f"RRF fusion produced {len(fused)} results")
        return fused

    def expand_with_graph(
        self,
        chunk_ids: List[str],
        max_expand: int = 30,
        expand_depth: int = 1
    ) -> List[str]:
        """
        Expand chunk IDs using dependency graph

        Args:
            chunk_ids: Initial chunk IDs
            max_expand: Maximum chunks to add
            expand_depth: How many hops to traverse

        Returns:
            Expanded list of chunk IDs
        """
        if not self.chunk_graph or len(self.chunk_graph.nodes()) == 0:
            logging.warning("No chunk graph, skipping expansion")
            return chunk_ids

        # Preserve RRF ranking order by using list instead of set
        # Original chunk_ids are in RRF order (best first)
        # Expanded chunks are added to END (lower priority)
        expanded_list = list(chunk_ids)  # Preserve order
        expanded_set = set(chunk_ids)  # For fast membership check
        to_explore = list(chunk_ids)

        for depth in range(expand_depth):
            new_to_explore = []

            for chunk_id in to_explore:
                if chunk_id not in self.chunk_graph:
                    continue

                # Add successors (this chunk imports/calls these)
                for successor in self.chunk_graph.successors(chunk_id):
                    if successor not in expanded_set and len(expanded_set) < len(chunk_ids) + max_expand:
                        expanded_set.add(successor)
                        expanded_list.append(successor)  # Append to END (preserves RRF order at top)
                        new_to_explore.append(successor)

                # Add predecessors (these chunks import/call this one)
                for predecessor in self.chunk_graph.predecessors(chunk_id):
                    if predecessor not in expanded_set and len(expanded_set) < len(chunk_ids) + max_expand:
                        expanded_set.add(predecessor)
                        expanded_list.append(predecessor)  # Append to END
                        new_to_explore.append(predecessor)

            to_explore = new_to_explore

            if len(expanded_set) >= len(chunk_ids) + max_expand:
                break

        added = len(expanded_list) - len(chunk_ids)
        logging.debug(f"Graph expansion added {added} chunks (depth={expand_depth})")

        return expanded_list

    def multi_factor_ranking(
        self,
        chunk_ids: List[str],
        query: str,
        query_embedding: np.ndarray = None,
        weights: Dict[str, float] = None,
        similarity_cache: Dict[str, float] = None
    ) -> List[Tuple[str, float]]:
        """
        Rank chunks by multiple factors

        Args:
            chunk_ids: Chunks to rank
            query: Original query
            query_embedding: Query embedding vector (optional, deprecated)
            weights: Factor weights (similarity, centrality, type_priority)
            similarity_cache: Pre-computed similarity scores {chunk_id: score}
                             Avoids re-embedding chunks (saves 60-80 API calls!)

        Returns:
            Ranked list of (chunk_id, score) tuples
        """
        if weights is None:
            weights = {
                'similarity': 0.5,
                'centrality': 0.3,
                'type_priority': 0.2
            }

        # Type priority mapping
        type_weights = {
            'function': 1.0,
            'class': 0.9,
            'method': 0.8,
            'file': 0.5
        }

        ranked = []

        for chunk_id in chunk_ids:
            if chunk_id not in self.chunk_index:
                continue

            chunk = self.chunk_index[chunk_id]
            score = 0.0

            # Factor 1: Semantic similarity
            # Use cached similarity from vector_search() to avoid re-embedding
            # This eliminates 60-80 redundant OpenAI API calls (8s latency savings!)
            if similarity_cache and chunk_id in similarity_cache:
                similarity = similarity_cache[chunk_id]
                score += weights['similarity'] * similarity
            else:
                # Fallback: default score if not in cache (expanded nodes)
                score += weights['similarity'] * 0.5
                logging.debug(f"Using default similarity for {chunk_id} (not in cache)")

            # Factor 2: PageRank centrality
            centrality = self.pagerank_scores.get(chunk_id, 0.0)
            score += weights['centrality'] * centrality

            # Factor 3: Type priority
            chunk_type = chunk.get('type', 'file')
            type_priority = type_weights.get(chunk_type, 0.3)
            score += weights['type_priority'] * type_priority

            # Factor 4: Entry point boost
            # Entry points (main, CLI) are critical for understanding execution flow
            # but often have low semantic similarity (just parameter signatures)
            if is_entry_point(chunk):
                score += 0.3  # Significant boost to get into top results
                logging.debug(f"Entry point boost: {chunk_id}")

            # Factor 5: Configuration variable boost
            # Config dictionaries (STEPS, CONFIG) are critical for understanding architecture
            # but have low semantic similarity (just data structures)
            if chunk.get('type') == 'module_variable':
                var_name = chunk.get('name', '').upper()
                if any(keyword in var_name for keyword in ['STEPS', 'CONFIG', 'SETTINGS', 'OPTIONS']):
                    score += 0.4  # Strong boost for config dictionaries
                    logging.debug(f"Config variable boost: {chunk_id}")

            ranked.append((chunk_id, score))

        # Sort by score
        ranked = sorted(ranked, key=lambda x: x[1], reverse=True)

        logging.debug(f"Multi-factor ranking scored {len(ranked)} chunks")
        return ranked

    def hybrid_search(
        self,
        query: str,
        top_k: int = 20,
        bm25_k: int = 100,
        vector_k: int = 100,
        expand: bool = True,
        expand_max: int = 75,  # Increased to 75 for deeper call chains (build → compile → execute)
        expand_depth: int = 3  # Increased to 3 for complete execution paths (HopRAG 2025: 2-3 optimal)
    ) -> List[Dict[str, Any]]:
        """
        Main hybrid search pipeline

        Args:
            query: User query
            top_k: Final number of chunks to return
            bm25_k: Number of BM25 results
            vector_k: Number of vector results
            expand: Whether to use graph expansion
            expand_max: Max chunks to add via graph (75 for 3-hop traversal)
            expand_depth: Graph traversal depth (3 hops for complete execution chains)

        Returns:
            List of ranked chunks with scores

        Research-backed defaults (Nov 2025):
        - expand_depth=3: Finds complete execution paths (filter → build → compile → execute)
        - expand_max=75: Allows 3-hop expansion without excessive noise
        - Based on: HopRAG, CodeRAG papers showing 3 hops needed for execution queries
        - Example: QuerySet.filter() → build_filter() → as_sql() → execute_sql()
        """
        logging.info(f"🔍 HYBRID SEARCH DEBUG: Query = '{query}'")

        # Step 1: BM25 search
        bm25_results = self.bm25_search(query, top_k=bm25_k)
        logging.info(f"📊 BM25: Retrieved {len(bm25_results)} results")
        if bm25_results:
            top_3_bm25 = [(self.chunk_index[cid]['name'], self.chunk_index[cid]['file_path'], score)
                          for cid, score in bm25_results[:3] if cid in self.chunk_index]
            logging.info(f"   Top 3 BM25: {top_3_bm25}")

        # Step 2: Vector search
        vector_results = self.vector_search(query, top_k=vector_k)
        logging.info(f"📊 Vector: Retrieved {len(vector_results)} results")
        if vector_results:
            top_3_vector = [(self.chunk_index[cid]['name'], self.chunk_index[cid]['file_path'], score)
                            for cid, score in vector_results[:3] if cid in self.chunk_index]
            logging.info(f"   Top 3 Vector: {top_3_vector}")

        # Step 3: Reciprocal Rank Fusion
        fused_results = self.reciprocal_rank_fusion(bm25_results, vector_results)
        logging.info(f"📊 RRF Fusion: {len(fused_results)} unique results")

        # Take top 50 from fusion
        top_fused = [chunk_id for chunk_id, _ in fused_results[:50]]
        if top_fused:
            top_3_fused = [(self.chunk_index[cid]['name'], self.chunk_index[cid]['file_path'])
                           for cid in top_fused[:3] if cid in self.chunk_index]
            logging.info(f"   Top 3 Fused: {top_3_fused}")

        # Step 4: Graph expansion (optional)
        # Research: 3-hop traversal finds complete execution paths (HopRAG 2025, CodeRAG 2025)
        # Example: filter() → build_filter() → as_sql() → execute_sql()
        if expand:
            expanded_ids = self.expand_with_graph(top_fused, max_expand=expand_max, expand_depth=expand_depth)
            added = len(expanded_ids) - len(top_fused)
            logging.info(f"📊 Graph Expansion: Added {added} chunks ({len(top_fused)} → {len(expanded_ids)}) at depth={expand_depth}")
        else:
            expanded_ids = top_fused

        # Step 5: Use RRF ranking directly (skip multi-factor ranking)
        # RRF already optimally combines BM25 + Vector + Graph signals
        # Multi-factor ranking was found to destroy good ranking because:
        # - Expanded chunks not in vector top-100 get default similarity
        # - All chunks end up with similar scores (~0.45)
        # - BM25 ranking signal is lost
        # Result: Session.request drops from #1 to out of top-20
        #
        # By using RRF directly: BM25 + Vector ranking is preserved
        final_chunk_ids = expanded_ids[:top_k]

        logging.info(f"📊 Using RRF fusion ranking directly (multi-factor ranking disabled)")
        if final_chunk_ids:
            top_3_final = [(self.chunk_index[cid]['name'], self.chunk_index[cid]['file_path'])
                          for cid in final_chunk_ids[:3] if cid in self.chunk_index]
            logging.info(f"   Top 3 Final: {top_3_final}")

        # Step 6: Return full chunk objects
        results = []
        for i, chunk_id in enumerate(final_chunk_ids):
            if chunk_id in self.chunk_index:
                chunk = self.chunk_index[chunk_id].copy()
                chunk['relevance_score'] = 1.0 / (i + 1)  # Rank-based score
                results.append(chunk)

        logging.info(f"✅ Hybrid search returned {len(results)} chunks")

        # DEBUG: Log full details of top 3 results
        for i, chunk in enumerate(results[:3], 1):
            logging.info(f"   Result {i}: {chunk['name']} ({chunk['type']}) in {chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']}")

        return results


def build_chunk_graph(chunks: List[Dict[str, Any]]) -> nx.DiGraph:
    """
    Build dependency graph at chunk level

    Args:
        chunks: List of all chunks

    Returns:
        NetworkX directed graph
    """
    G = nx.DiGraph()

    # Index chunks by file for efficient lookup
    chunks_by_file = {}
    for chunk in chunks:
        file_path = chunk['file_path']
        if file_path not in chunks_by_file:
            chunks_by_file[file_path] = []
        chunks_by_file[file_path].append(chunk)

    # Add all chunks as nodes
    for chunk in chunks:
        G.add_node(
            chunk['chunk_id'],
            type=chunk['type'],
            name=chunk['name'],
            file=chunk['file_path']
        )

    # Add edges based on imports and relationships
    for chunk in chunks:
        chunk_id = chunk['chunk_id']
        imports = chunk['metadata'].get('imports', [])

        # Find chunks that define imported symbols
        for imp in imports:
            # Simple heuristic: if import name matches chunk name
            for other_chunk in chunks:
                if other_chunk['name'] == imp or imp.endswith(other_chunk['name']):
                    if other_chunk['chunk_id'] != chunk_id:
                        G.add_edge(other_chunk['chunk_id'], chunk_id, relation='imports')

        # Add file-level relationships (chunks in same file are related)
        file_path = chunk['file_path']
        for sibling in chunks_by_file.get(file_path, []):
            if sibling['chunk_id'] != chunk_id:
                # Weak edge: same file
                if not G.has_edge(chunk_id, sibling['chunk_id']):
                    G.add_edge(chunk_id, sibling['chunk_id'], relation='same_file', weight=0.3)

    logging.info(f"Chunk graph built: {len(G.nodes())} nodes, {len(G.edges())} edges")
    return G


def is_entry_point(chunk: Dict[str, Any]) -> bool:
    """
    Detect if chunk is a CLI entry point or main orchestrator

    Entry points are critical for understanding execution flow but often
    rank low in semantic similarity (just parameter lists).
    This function identifies them for ranking boost.
    """
    name = chunk.get('name', '').lower()
    file_path = chunk.get('file_path', '').lower()

    # Check for main function (but exclude test/benchmark scripts)
    if name == 'main':
        if 'test' not in file_path and 'benchmark' not in file_path and 'scripts' not in file_path:
            return True

    # Check for __main__ module
    if name == '__main__' or '__main__' in file_path:
        return True

    # Check for CLI/cli in path (entry point modules)
    if '/cli/' in file_path or file_path.endswith('cli.py'):
        return True

    return False


def get_type_priority(chunk_type: str) -> float:
    """Get priority weight for chunk type"""
    priorities = {
        'function': 1.0,
        'class': 0.9,
        'method': 0.8,
        'file': 0.5
    }
    return priorities.get(chunk_type, 0.3)
