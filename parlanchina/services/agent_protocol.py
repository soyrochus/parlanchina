"""Agent protocol types and diagrams.

These dataclasses define the language-agnostic envelopes used by the agent
engine. They are intentionally explicit to simplify future ports to other
languages.

```mermaid
graph TD
  User[User] -->|Task request| AgentEngine

  subgraph AgentEngine
    AE[AgentEngine<br/>main loop]
    PROF[AgentProfile]
    STATE[AgentState]
    REG[ToolRegistry]
    MEM[MemoryLayer]
    LLM[LLMBackend]
  end

  AE --> PROF
  AE --> STATE
  AE --> REG
  AE --> MEM
  AE --> LLM

  REG -->|invoke| Tool1[Tool: fs]
  REG -->|invoke| Tool2[Tool: mcp-kb]
  REG -->|invoke| Tool3[Tool: http]

  MEM -->|uses| Tool2
  MEM -->|uses| Tool3

  LLM -->|LLM Protocol| AE

  AE -->|Final answer| User
```
```
stateDiagram-v2
  [*] --> PLAN

  PLAN --> ACT: plan created
  PLAN --> REVIEW: small tasks resolved directly
  PLAN --> DONE: trivial goal satisfied

  ACT --> REVIEW: actions completed
  ACT --> PLAN: replanning needed

  REVIEW --> ACT: more work required
  REVIEW --> DONE: goal achieved

  DONE --> [*]
```
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional

AgentMode = Literal["PLAN", "ACT", "REVIEW", "DONE"]


@dataclass
class AgentLimits:
    max_steps: int
    max_tokens_per_call: int
    allow_destructive_tools: bool = False


@dataclass
class AgentProfile:
    id: str
    name: str
    system_prompt: str
    tool_ids: List[str]
    limits: AgentLimits
    memory_packs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HistoryEntry:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_call_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ContextChunk:
    id: str
    content: str
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentState:
    goal: str
    subgoals: List[str]
    mode: AgentMode
    step: int
    history: List[HistoryEntry]
    scratchpad: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["history"] = [entry.to_dict() for entry in self.history]
        return data


@dataclass
class ToolDescriptor:
    id: str
    name: str
    description: str
    parameters: Dict[str, Any]
    destructive: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolInvocation:
    id: str
    tool_id: str
    args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolResult:
    invocation_id: str
    tool_id: str
    content: str
    success: bool = True
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LLMInput:
    profile: AgentProfile
    state: AgentState
    context_chunks: List[ContextChunk] = field(default_factory=list)
    user_message: str = ""
    tool_schema: List[ToolDescriptor] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.to_dict(),
            "state": self.state.to_dict(),
            "context_chunks": [c.to_dict() for c in self.context_chunks],
            "user_message": self.user_message,
            "tool_schema": [t.to_dict() for t in self.tool_schema],
        }


@dataclass
class LLMOutput:
    mode: AgentMode
    message_to_user: str | None
    tool_calls: List[ToolInvocation]
    updates: Dict[str, Any] = field(default_factory=dict)
    done: bool = False

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "LLMOutput":
        tool_calls = [
            ToolInvocation(
                id=call.get("id") or f"call-{idx}",
                tool_id=call.get("tool_id") or call.get("tool") or "",
                args=call.get("args") or {},
            )
            for idx, call in enumerate(payload.get("tool_calls") or [])
        ]
        return cls(
            mode=(payload.get("mode") or "ACT"),
            message_to_user=payload.get("message") or payload.get("message_to_user"),
            tool_calls=tool_calls,
            updates=payload.get("updates") or {},
            done=bool(payload.get("done")),
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "message_to_user": self.message_to_user,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "updates": self.updates,
            "done": self.done,
        }
