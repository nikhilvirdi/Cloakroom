"""Hybrid retrieval for tool discovery using BM25."""

from __future__ import annotations

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from cloakroom.discovery.catalog import Catalog, ToolEntry

# Domain-specific synonym expansion
SYNONYMS = {
    "bill": ["invoice", "receipt", "statement"],
    "invoice": ["bill", "receipt", "statement"],
    "mail": ["email", "message"],
    "email": ["mail", "message"],
    "bank": ["transaction", "account", "payment"],
    "transaction": ["bank", "payment"],
    "note": ["memo", "document"],
    "search": ["find", "query", "lookup"],
    "find": ["search", "query", "lookup"],
}


def _expand_query(query: str) -> str:
    """Expand query with domain synonyms.

    Args:
        query: Original search query

    Returns:
        Expanded query with synonyms
    """
    words = query.lower().split()
    expanded_words = []

    for word in words:
        expanded_words.append(word)
        # Add synonyms if found
        if word in SYNONYMS:
            expanded_words.extend(SYNONYMS[word])

    return " ".join(expanded_words)


class BM25Retriever:
    """BM25-based retrieval for tool discovery."""

    def __init__(self, catalog: Catalog) -> None:
        """Initialize BM25 retriever with catalog.

        Args:
            catalog: Tool catalog to index
        """
        self.catalog = catalog
        self._tools = catalog.list_all_tools()

        # Create corpus from tool descriptions
        self._corpus = [tool.description.lower().split() for tool in self._tools]

        # Initialize BM25
        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
        else:
            self._bm25 = None

    def search(self, query: str, max_tools: int = 6) -> list[ToolEntry]:
        """Search for tools using BM25 ranking.

        Args:
            query: Search query
            max_tools: Maximum number of tools to return

        Returns:
            List of ranked tool entries
        """
        if not self._bm25 or not self._tools:
            return []

        # Expand query with synonyms
        expanded_query = _expand_query(query)
        query_tokens = expanded_query.lower().split()

        # Get BM25 scores
        scores = self._bm25.get_scores(query_tokens)

        # Get top-k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:max_tools]

        # Return ranked tools
        return [self._tools[i] for i in top_indices if scores[i] > 0]
