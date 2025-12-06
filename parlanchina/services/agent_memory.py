"""Memory layer abstractions for Agent Mode."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .agent_protocol import ContextChunk, HistoryEntry


class MemoryLayer:
    """Abstract memory facade.

    Implementations can pull associative context, record episodic history, or
    integrate with MCP-backed knowledge bases. The default implementation keeps
    everything in memory for a single request/response cycle.
    """

    async def initial_associative_context(self, goal: str) -> List[ContextChunk]:  # pragma: no cover - interface
        raise NotImplementedError

    async def note_history(self, entries: List[HistoryEntry]):  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class InMemoryMemoryLayer(MemoryLayer):
    context: List[ContextChunk] = field(default_factory=list)

    async def initial_associative_context(self, goal: str) -> List[ContextChunk]:
        return list(self.context)

    async def note_history(self, entries: List[HistoryEntry]):
        # No-op for now; hook for future persistence or MCP integration
        self.context.extend(
            [
                ContextChunk(id=f"h-{idx}", content=e.content, source=e.role)
                for idx, e in enumerate(entries)
            ]
        )
