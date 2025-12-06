"""AgentEngine orchestrates Agent Mode with a deterministic loop."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, List

from .agent_backend import LLMBackend
from .agent_memory import MemoryLayer
from .agent_protocol import (
    AgentMode,
    AgentProfile,
    AgentState,
    HistoryEntry,
    LLMInput,
    LLMOutput,
    ToolInvocation,
)
from .agent_tools import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


_ALLOWED_TRANSITIONS: dict[AgentMode, set[AgentMode]] = {
    "PLAN": {"ACT", "REVIEW", "DONE"},
    "ACT": {"PLAN", "REVIEW"},
    "REVIEW": {"ACT", "DONE"},
    "DONE": set(),
}


@dataclass
class AgentTurn:
    message: str = ""
    artifacts: List[dict] = field(default_factory=list)
    done: bool = False


class AgentEngine:
    def __init__(
        self,
        profile: AgentProfile,
        registry: ToolRegistry,
        memory: MemoryLayer,
        backend: LLMBackend,
    ):
        self.profile = profile
        self.registry = registry
        self.memory = memory
        self.backend = backend

    async def run(self, state: AgentState, user_message: str) -> AsyncIterator[AgentTurn]:
        context_chunks = await self.memory.initial_associative_context(state.goal)
        message_buffer: list[str] = []

        for _ in range(self.profile.limits.max_steps):
            llm_input = LLMInput(
                profile=self.profile,
                state=state,
                context_chunks=context_chunks,
                user_message=user_message,
                tool_schema=self.registry.describe(),
            )
            llm_output = await self.backend.generate(llm_input)
            state = self._apply_updates(state, llm_output)
            turn_artifacts: list[dict] = []

            if llm_output.tool_calls:
                tool_results = await self._execute_tools(llm_output.tool_calls)
                state.history.extend(
                    [HistoryEntry(role="assistant", content="Tool call issued")]  # placeholder for visibility
                )
                for result in tool_results:
                    state.history.append(
                        HistoryEntry(
                            role="tool",
                            content=result.content,
                            tool_call_id=result.invocation_id,
                        )
                    )
                    turn_artifacts.extend(result.artifacts)

            if llm_output.message_to_user:
                message_buffer.append(llm_output.message_to_user)
                yield AgentTurn(message=llm_output.message_to_user, artifacts=turn_artifacts, done=llm_output.done)
            elif turn_artifacts:
                yield AgentTurn(message="", artifacts=turn_artifacts, done=llm_output.done)

            if llm_output.done or state.mode == "DONE":
                break

        if message_buffer and not message_buffer[-1].strip():
            return

    def _apply_updates(self, state: AgentState, output: LLMOutput) -> AgentState:
        next_mode = output.mode or state.mode
        if not self._is_valid_transition(state.mode, next_mode):
            logger.debug("Invalid mode transition %s -> %s, staying in REVIEW", state.mode, next_mode)
            next_mode = "REVIEW" if state.mode != "DONE" else "DONE"
        state.mode = next_mode
        state.step += 1

        updates = output.updates or {}
        if updates.get("scratchpad"):
            state.scratchpad = updates["scratchpad"]
        if isinstance(updates.get("subgoals"), list):
            state.subgoals = [str(item) for item in updates["subgoals"]]
        if output.message_to_user:
            state.history.append(HistoryEntry(role="assistant", content=output.message_to_user))
        return state

    async def _execute_tools(self, tool_calls: List[ToolInvocation]) -> List[ToolResult]:
        results: list[ToolResult] = []
        for call in tool_calls:
            result = await self.registry.invoke(call)
            results.append(result)
        await self.memory.note_history(
            [HistoryEntry(role="tool", content=r.content, tool_call_id=r.invocation_id) for r in results]
        )
        return results

    @staticmethod
    def _is_valid_transition(current: AgentMode, proposed: AgentMode) -> bool:
        return proposed in _ALLOWED_TRANSITIONS.get(current, set())
