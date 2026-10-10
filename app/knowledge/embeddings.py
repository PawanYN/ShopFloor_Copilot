"""Turn text into vectors with an embedding model served by Ollama."""

import httpx

from app import config

# Some models are trained with a short instruction in front of the text.
# Leaving it out lowers their retrieval quality, so each model gets its own.
PREFIXES = {
    "nomic-embed-text": {"document": "search_document: ", "query": "search_query: "},
    "mxbai-embed-large": {"document": "", "query": "Represent this sentence for searching relevant passages: "},
}


def embed(texts: list[str], model: str, kind: str) -> list[list[float]]:
    """kind is "document" for passages being indexed, "query" for a question."""
    prefix = PREFIXES.get(model, {}).get(kind, "")
    response = httpx.post(
        f"{config.OLLAMA_URL}/api/embed",
        json={"model": model, "input": [prefix + text for text in texts]},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["embeddings"]
