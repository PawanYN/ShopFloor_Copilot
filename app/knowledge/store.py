import re
from dataclasses import dataclass
from typing import Protocol

import chromadb
from chromadb.config import Settings

from app.knowledge.documents import Passage


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict
    distance: float


class PassageStore(Protocol):
    """What the rest of the app may ask of the vector store."""

    def count(self) -> int: ...

    def replace_all(self, passages: list[Passage], embeddings: list[list[float]]) -> None: ...

    def search(self, embedding: list[float], top_k: int, plant: str) -> list[Hit]: ...


class ChromaPassageStore:
    """One collection per embedding model, because vectors from different models cannot be mixed."""

    def __init__(self, path: str, embedding_model: str) -> None:
        self._client = chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))
        self._name = "sops-" + re.sub(r"[^a-zA-Z0-9]+", "-", embedding_model).strip("-")
        self._collection = self._open()

    def _open(self):
        return self._client.get_or_create_collection(self._name, metadata={"hnsw:space": "cosine"})

    def count(self) -> int:
        return self._collection.count()

    def replace_all(self, passages: list[Passage], embeddings: list[list[float]]) -> None:
        self._client.delete_collection(self._name)
        self._collection = self._open()
        self._collection.add(
            ids=[passage.id for passage in passages],
            documents=[passage.text for passage in passages],
            metadatas=[passage.metadata for passage in passages],
            embeddings=embeddings,
        )

    def search(self, embedding: list[float], top_k: int, plant: str) -> list[Hit]:
        # A worker must never be given another plant's rule, so plant is a hard filter.
        result = self._collection.query(query_embeddings=[embedding], n_results=top_k, where={"plant": plant})
        return [
            Hit(id=id_, text=text, metadata=metadata, distance=distance)
            for id_, text, metadata, distance in zip(
                result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]
