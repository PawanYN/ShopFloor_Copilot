"""Build the search index from the SOP documents.

    python -m app.knowledge.index

Run this when a document is added or revised. The service runs it by itself only when no index exists.
"""

import logging

from app import config
from app.knowledge.documents import load_passages
from app.knowledge.embeddings import embed
from app.knowledge.store import ChromaPassageStore, PassageStore

log = logging.getLogger(__name__)


def build_index(store: PassageStore, embedding_model: str, directory: str = config.SOP_DIR) -> int:
    passages = load_passages(directory)
    embeddings = embed([passage.text for passage in passages], embedding_model, "document")
    store.replace_all(passages, embeddings)
    revisions = sorted({f"{p.metadata['document']} rev {p.metadata['revision']}" for p in passages})
    log.info("indexed %d passages with %s: %s", len(passages), embedding_model, ", ".join(revisions))
    return len(passages)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    store = ChromaPassageStore(config.CHROMA_PATH, config.EMBEDDING_MODEL)
    build_index(store, config.EMBEDDING_MODEL)


if __name__ == "__main__":
    main()
