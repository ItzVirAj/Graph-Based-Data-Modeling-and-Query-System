from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

ENTITY_PATTERNS = {
    "Order": re.compile(r"\b74\d{4}\b"),
    "Delivery": re.compile(r"\b80\d{6}\b"),
    "Invoice": re.compile(r"\b(?:90|91)\d{6}\b"),
    "Payment": re.compile(r"\b94\d{8}\b"),
    "JournalEntry": re.compile(r"\b94\d{7,8}\b"),
    "Customer": re.compile(r"\b32\d{7}\b"),
    "Plant": re.compile(r"\b(?:\d{4}|[A-Z]{2}\d{2})\b"),
}


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: str
    query_generated: dict[str, Any] | None = None


@dataclass
class ConversationMemory:
    max_turns: int = 10
    turns: deque[ConversationTurn] = field(default_factory=deque)

    def add_turn(self, role: str, content: str, query: dict[str, Any] | None = None) -> None:
        self.turns.append(ConversationTurn(role=role, content=content, timestamp=datetime.now(timezone.utc).isoformat(), query_generated=query))
        while len(self.turns) > self.max_turns:
            self.turns.popleft()

    def get_context(self) -> str:
        if not self.turns:
            return "No prior conversation."
        lines: list[str] = []
        for turn in self.turns:
            lines.append(f"{turn.role.capitalize()}: {turn.content}")
            if turn.query_generated:
                lines.append(f"Generated Query: {turn.query_generated}")
        return "\n".join(lines)

    def get_last_entities(self) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for turn in reversed(self.turns):
            for entity_type, pattern in ENTITY_PATTERNS.items():
                for match in pattern.findall(turn.content):
                    key = (entity_type, match)
                    if key not in seen:
                        seen.add(key)
                        found.append({"entity_type": entity_type, "entity_id": match})
        return found

    def clear(self) -> None:
        self.turns.clear()

    def to_dict(self) -> dict[str, Any]:
        return {"max_turns": self.max_turns, "turn_count": len(self.turns), "turns": [{"role": turn.role, "content": turn.content, "timestamp": turn.timestamp, "query_generated": turn.query_generated} for turn in self.turns], "last_entities": self.get_last_entities()}


sessions: dict[str, ConversationMemory] = {}


def get_session_memory(session_id: str, max_turns: int = 10) -> ConversationMemory:
    memory = sessions.get(session_id)
    if memory is None:
        memory = ConversationMemory(max_turns=max_turns)
        sessions[session_id] = memory
    return memory


def clear_session_memory(session_id: str) -> None:
    memory = sessions.pop(session_id, None)
    if memory is not None:
        memory.clear()
