"""Inner monologue: cheap LLM call producing private thoughts before acting."""
from __future__ import annotations

import orjson

from azura.llm.prompts import render
from azura.llm.router import think_json
from azura.memory.service import MemoryService
from azura.mind.mood import MoodView
from azura.personality.schema import Persona


class InnerVoice:
    """Private LLM-driven reflection that never reaches the chat."""

    def __init__(self, persona: Persona, memory: MemoryService) -> None:
        self.p = persona
        self.m = memory

    async def reflect(
        self,
        *,
        chat_id: int,
        from_user_id: int | None,
        text: str,
        mood: MoodView,
    ) -> dict:
        """Produce a JSON dict with: feeling, want_to_reply, tone, draft_thought."""
        about_user = (
            await self.m.recall_about_user(from_user_id, query=text)
            if from_user_id is not None else {}
        )
        chat_ctx = await self.m.recall_chat(chat_id)
        sys = render(
            "inner_voice.j2",
            persona=self.p.model_dump(by_alias=True),
        )
        usr = orjson.dumps(
            {
                "message": text,
                "mood": mood.__dict__,
                "about_user": about_user,
                "chat": {"opinion": chat_ctx["opinion"], "feelings": chat_ctx["feelings"]},
            },
            option=orjson.OPT_INDENT_2,
        ).decode()
        try:
            out = await think_json(
                [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
                temperature=0.5,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
        except Exception:
            return {
                "feeling": "neutral", "want_to_reply": True, "tone": "casual",
                "draft_thought": "", "should_journal": False,
            }
        if out.get("should_journal"):
            await self.m.repos.journal.write(
                out.get("draft_thought", "")[:280], kind="inner_voice",
                chat_id=chat_id, user_id=from_user_id,
            )
        return out
