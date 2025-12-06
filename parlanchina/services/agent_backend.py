"""LLM backend abstraction for Agent Mode."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import OpenAIError

from parlanchina.services.openai_client import get_async_client

from .agent_protocol import LLMInput, LLMOutput

logger = logging.getLogger(__name__)


class LLMBackend:
    async def generate(self, llm_input: LLMInput) -> LLMOutput:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class OpenAILLMBackend(LLMBackend):
    model: str

    async def generate(self, llm_input: LLMInput) -> LLMOutput:
        """Ask the LLM to produce a structured JSON agent action."""

        client = get_async_client()
        payload = {
            "mode": llm_input.state.mode,
            "state": llm_input.state.to_dict(),
            "context": [c.to_dict() for c in llm_input.context_chunks],
            "tool_schema": [t.to_dict() for t in llm_input.tool_schema],
            "goal": llm_input.state.goal,
            "user_message": llm_input.user_message,
        }
        system_prompt = (
            llm_input.profile.system_prompt
            + "\nYou MUST respond with a single JSON object matching this schema: "
            + json.dumps(
                {
                    "mode": "PLAN|ACT|REVIEW|DONE",
                    "message": "assistant text for the user (optional)",
                    "tool_calls": [
                        {"id": "string", "tool_id": "<one of tool_schema ids>", "args": {} }
                    ],
                    "updates": {"scratchpad": "text", "subgoals": ["str", "str"]},
                    "done": False,
                },
                indent=2,
            )
            + "\nState machine legal transitions: PLAN->ACT/REVIEW/DONE, ACT->REVIEW/PLAN, REVIEW->ACT/DONE."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Agent envelope:" + json.dumps(payload, indent=2),
            },
        ]
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            choice = (response.choices or [None])[0]
            message = getattr(choice, "message", None)
            raw_content = getattr(message, "content", "") if message else ""
            parsed = json.loads(raw_content or "{}")
            return LLMOutput.from_payload(parsed)
        except OpenAIError as exc:
            logger.exception("LLM backend error: %s", exc)
            return LLMOutput(
                mode="REVIEW",
                message_to_user="Model call failed while planning tools.",
                tool_calls=[],
                updates={},
                done=True,
            )
        except Exception as exc:  # pragma: no cover - safety
            logger.exception("Unexpected LLM backend error: %s", exc)
            return LLMOutput(
                mode="REVIEW",
                message_to_user="Unexpected error while coordinating tools.",
                tool_calls=[],
                updates={},
                done=True,
            )
