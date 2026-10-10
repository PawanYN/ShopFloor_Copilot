from app import config
from app.knowledge.embeddings import embed
from app.knowledge.store import Hit, PassageStore


def search(store: PassageStore, question: str, top_k: int, embedding_model: str, plant: str = config.PLANT) -> list[Hit]:
    return store.search(embed([question], embedding_model, "query")[0], top_k, plant)
