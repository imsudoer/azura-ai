"""Agent core: tool-using reply loop driven by the reply model."""
from __future__ import annotations

import orjson
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from azura.llm.client import chat
from azura.llm.prompts import render
from azura.llm.router import model_for
from azura.memory.service import MemoryService
from azura.mind.household_context import short_one_liner
from azura.mind.mood import MoodView
from azura.personality.schema import Persona
from azura.utils.log import get_logger

log = get_logger("mind.agent")

ToolFn = Callable[[dict], Awaitable[Any]]


@dataclass
class ToolSpec:
    """OpenAI tool schema bound to an async Python implementation."""
    name: str
    description: str
    parameters: dict
    fn: ToolFn


@dataclass
class AgentResult:
    """One agent run output."""
    messages: list[str]
    actions: list[dict]
    tool_calls: int


class Agent:
    """Tool-calling loop. Each step: model picks tools or emits a final list of messages."""

    def __init__(self, persona: Persona, memory: MemoryService) -> None:
        self.p = persona
        self.m = memory

    def _to_openai_tools(self, tools: list[ToolSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _system(self, *, mood: MoodView, situation: dict) -> str:
        return render(
            "system_human.j2",
            persona=self.p.model_dump(by_alias=True),
            mood=mood.__dict__,
            household=short_one_liner(self.p),
            situation=situation,
        )

    async def run(
        self,
        *,
        mood: MoodView,
        situation: dict,
        user_prompt: str,
        tools: list[ToolSpec],
        max_steps: int = 6,
    ) -> AgentResult:
        """Run the tool loop until the model emits a final message list."""
        sys_msg = self._system(mood=mood, situation=situation)
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_prompt},
        ]
        by_name: dict[str, ToolSpec] = {t.name: t for t in tools}
        tool_calls = 0
        actions: list[dict] = []
        for step in range(max_steps):
            r = await chat(
                model=model_for("reply"),
                messages=msgs,
                temperature=0.85,
                tools=self._to_openai_tools(tools) if tools else None,
                tool_choice="auto" if tools else None,
            )
            choice = r.choices[0].message
            calls = getattr(choice, "tool_calls", None) or []
            if calls:
                msgs.append({
                    "role": "assistant",
                    "content": choice.content or "",
                    "tool_calls": [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                        for c in calls
                    ],
                })
                for c in calls:
                    name = c.function.name
                    try:
                        args = orjson.loads(c.function.arguments or "{}")
                    except Exception:
                        args = {}
                    spec = by_name.get(name)
                    if spec is None:
                        result = {"error": f"unknown tool {name}"}
                    else:
                        try:
                            result = await spec.fn(args)
                        except Exception as e:
                            log.exception("tool {} failed", name)
                            result = {"error": f"{type(e).__name__}: {e}"}
                    actions.append({"tool": name, "args": args, "result": result})
                    tool_calls += 1
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": c.id,
                        "name": name,
                        "content": orjson.dumps(result, default=str).decode(),
                    })
                continue
            text = (choice.content or "").strip()
            if not text:
                return AgentResult(messages=[], actions=actions, tool_calls=tool_calls)
            messages = _split_final(text)
            return AgentResult(messages=messages, actions=actions, tool_calls=tool_calls)
        return AgentResult(messages=[], actions=actions, tool_calls=tool_calls)


def _split_final(text: str) -> list[str]:
    """Final output may be a JSON list of strings or a plain string with \\n splits."""
    s = text.strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            out = orjson.loads(s)
            if isinstance(out, list):
                return [str(x).strip() for x in out if str(x).strip()]
        except Exception:
            pass
    parts = [p.strip() for p in s.split("\n\n") if p.strip()]
    return parts or [s]
