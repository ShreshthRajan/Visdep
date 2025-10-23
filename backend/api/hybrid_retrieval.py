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
        """Build BM25 index over chunk code + names"""
        corpus = []
        self.chunk_ids = []

        for chunk in self.chunks:
            # Combine code, name, file path for indexing
            text = f"{chunk['name']} {chunk['file_path']} {chunk['code']}"
            corpus.append(text)
            self.chunk_ids.append(chunk['chunk_id'])

        # Tokenize corpus
        tokenized_corpus = [doc.lower().split() for doc in corpus]

        # Build BM25 index
        self.bm25 = BM25Okapi(tokenized_corpus)

        logging.info(f"BM25 index built with {len(corpus)} documents")

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
        BM25 keyword search

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of (chunk_id, score) tuples
        """
        tokenized_query = query.lower().split()
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

        expanded = set(chunk_ids)
        to_explore = list(chunk_ids)

        for depth in range(expand_depth):
            new_to_explore = []

            for chunk_id in to_explore:
                if chunk_id not in self.chunk_graph:
                    continue

                # Add successors (this chunk imports/calls these)
                for successor in self.chunk_graph.successors(chunk_id):
                    if successor not in expanded and len(expanded) < len(chunk_ids) + max_expand:
                        expanded.add(successor)
                        new_to_explore.append(successor)

                # Add predecessors (these chunks import/call this one)
                for predecessor in self.chunk_graph.predecessors(chunk_id):
                    if predecessor not in expanded and len(expanded) < len(chunk_ids) + max_expand:
                        expanded.add(predecessor)
                        new_to_explore.append(predecessor)

            to_explore = new_to_explore

            if len(expanded) >= len(chunk_ids) + max_expand:
                break

        added = len(expanded) - len(chunk_ids)
        logging.debug(f"Graph expansion added {added} chunks (depth={expand_depth})")

        return list(expanded)

    def multi_factor_ranking(
        self,
        chunk_ids: List[str],
        query: str,
        query_embedding: np.ndarray,
        weights: Dict[str, float] = None
    ) -> List[Tuple[str, float]]:
        """
        Rank chunks by multiple factors

        Args:
            chunk_ids: Chunks to rank
            query: Original query
            query_embedding: Query embedding vector
            weights: Factor weights (similarity, centrality, type_priority)

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
            try:
                # Get chunk from vector store
                chunk_docs = self.vector_store.similarity_search_with_score(
                    chunk['code'][:500],  # First 500 chars
                    k=1,
                    filter={"chunk_id": chunk_id}
                )
                if chunk_docs:
                    _, distance = chunk_docs[0]
                    similarity = 1 / (1 + distance)
                    score += weights['similarity'] * similarity
            except Exception as e:
                logging.debug(f"Similarity calculation failed for {chunk_id}: {e}")
                score += weights['similarity'] * 0.5  # Default middle score

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
        expand_max: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Main hybrid search pipeline

        Args:
            query: User query
            top_k: Final number of chunks to return
            bm25_k: Number of BM25 results
            vector_k: Number of vector results
            expand: Whether to use graph expansion
            expand_max: Max chunks to add via graph

        Returns:
            List of ranked chunks with scores
        """
        logging.info(f"Hybrid search for query: {query}")

        # Step 1: BM25 search
        bm25_results = self.bm25_search(query, top_k=bm25_k)

        # Step 2: Vector search
        vector_results = self.vector_search(query, top_k=vector_k)

        # Step 3: Reciprocal Rank Fusion
        fused_results = self.reciprocal_rank_fusion(bm25_results, vector_results)

        # Take top 50 from fusion
        top_fused = [chunk_id for chunk_id, _ in fused_results[:50]]

        # Step 4: Graph expansion (optional)
        if expand:
            expanded_ids = self.expand_with_graph(top_fused, max_expand=expand_max)
        else:
            expanded_ids = top_fused

        # Step 5: Multi-factor ranking
        query_embedding = None  # Will be computed in multi_factor_ranking if needed
        ranked = self.multi_factor_ranking(expanded_ids, query, query_embedding)

        # Step 6: Get top-k chunks
        final_chunk_ids = [chunk_id for chunk_id, _ in ranked[:top_k]]

        # Step 7: Return full chunk objects with scores
        results = []
        score_map = dict(ranked)

        for chunk_id in final_chunk_ids:
            if chunk_id in self.chunk_index:
                chunk = self.chunk_index[chunk_id].copy()
                chunk['relevance_score'] = score_map[chunk_id]
                results.append(chunk)

        logging.info(f"Hybrid search returned {len(results)} chunks")
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
