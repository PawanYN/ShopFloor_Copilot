import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI

from app import config
from app.api.routes import router
from app.knowledge.index import build_index
from app.knowledge.retrieval import search
from app.knowledge.store import ChromaPassageStore, Hit
from app.learning.bandit import Bandit
from app.llm import ModelClient, OllamaClient
from app.storage.conversations import ConversationStore, MongoConversationStore
from app.storage.sqlite import SqliteStore

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the search index only when none exists; later changes go through `python -m app.knowledge.index`.
    try:
        app.state.passages = ChromaPassageStore(config.CHROMA_PATH, config.EMBEDDING_MODEL)
        if app.state.passages.count() == 0:
            count = build_index(app.state.passages, config.EMBEDDING_MODEL)
            log.info("Built the search index: %d passages with %s", count, config.EMBEDDING_MODEL)
    except Exception:
        log.exception("Could not prepare the search index; knowledge search is unavailable")
    yield


def create_app(
    database_path: str | None = None,
    conversations: ConversationStore | None = None,
    model_client: ModelClient | None = None,
    retrieve: Callable[[str, int], list[Hit]] | None = None,
) -> FastAPI:
    app = FastAPI(title="ShopFloor Copilot", lifespan=lifespan)
    app.state.store = SqliteStore(database_path or config.DATABASE_PATH)
    app.state.conversations = conversations or MongoConversationStore(config.MONGO_URL)
    app.state.model_client = model_client or OllamaClient()
    app.state.answer_model = config.ANSWER_MODEL
    app.state.retrieve = retrieve or (
        lambda text, top_k: search(app.state.passages, text, top_k, config.EMBEDDING_MODEL)
    )
    app.state.bandit = Bandit(app.state.store, config.TOP_K_CHOICES, config.EXPLORE_RATE, config.LEARNING_STEP)
    app.include_router(router)
    return app
