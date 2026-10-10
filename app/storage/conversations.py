"""Where conversations are kept: one document per conversation, holding its messages."""

from datetime import datetime, timezone
from typing import Any, Protocol

EMPTY = {"messages": [], "image": None, "image_filename": None, "vision": None, "work_order_id": None}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore(Protocol):
    def get(self, conversation_id: str) -> dict[str, Any]: ...

    def update(self, conversation_id: str, messages: list[dict[str, Any]], fields: dict[str, Any]) -> None: ...


class MongoConversationStore:
    def __init__(self, url: str, database: str = "shopfloor") -> None:
        from pymongo import MongoClient

        self._conversations = MongoClient(url, serverSelectionTimeoutMS=5000)[database]["conversations"]

    def get(self, conversation_id: str) -> dict[str, Any]:
        found = self._conversations.find_one({"_id": conversation_id}) or {}
        return {**EMPTY, **{key: value for key, value in found.items() if key != "_id"}}

    def update(self, conversation_id: str, messages: list[dict[str, Any]], fields: dict[str, Any]) -> None:
        stamped = [{**message, "at": _now()} for message in messages]
        change = {"$push": {"messages": {"$each": stamped}}, "$setOnInsert": {"created_at": _now()}}
        if fields:
            change["$set"] = fields
        self._conversations.update_one({"_id": conversation_id}, change, upsert=True)


class MemoryConversationStore:
    """Keeps conversations in memory. Used by the tests."""

    def __init__(self) -> None:
        self._conversations: dict[str, dict[str, Any]] = {}

    def get(self, conversation_id: str) -> dict[str, Any]:
        return {**EMPTY, **self._conversations.get(conversation_id, {})}

    def update(self, conversation_id: str, messages: list[dict[str, Any]], fields: dict[str, Any]) -> None:
        current = self._conversations.setdefault(conversation_id, {"messages": []})
        current["messages"] = current["messages"] + [{**message, "at": _now()} for message in messages]
        current.update(fields)
