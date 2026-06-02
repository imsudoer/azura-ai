"""MemoryService: single entry point aggregating every tier and helper."""
from __future__ import annotations

from azura.db.repo import Repos
from azura.memory.daily import DailyMemory
from azura.memory.embeds import EmbedCache
from azura.memory.episodic import Episodic
from azura.memory.feelings import Feelings
from azura.memory.forgetting import Forgetting
from azura.memory.global_mem import GlobalMemory
from azura.memory.long_term import LongTerm
from azura.memory.opinions import Opinions
from azura.memory.relationships import Relationships
from azura.memory.short_term import ShortTerm


class MemoryService:
    """One-stop memory facade exposed to mind/, tools/, telegram/."""

    def __init__(self, repos: Repos) -> None:
        self.repos = repos
        self.embeds = EmbedCache()
        self.short = ShortTerm(repos)
        self.long = LongTerm(repos)
        self.daily = DailyMemory(repos)
        self.global_ = GlobalMemory(repos)
        self.episodic = Episodic(repos)
        self.opinions = Opinions(repos)
        self.feelings = Feelings(repos)
        self.relationships = Relationships(repos)
        self.forgetting = Forgetting(repos)

    async def recall_about_user(self, user_id: int, *, query: str | None = None, limit: int = 6) -> dict:
        """Bundle everything the persona 'knows' about a user for prompt injection."""
        u = await self.repos.users.get(user_id)
        opinion = u.opinion if u else 0
        feelings = await self.feelings.toward_user(user_id)
        prox = await self.opinions.proximity(user_id)
        episodes = await self.episodic.with_user(user_id, limit=limit)
        text_facts: list[str] = []
        if query:
            text_facts = await self.long.search(query, limit=limit)
        else:
            text_facts = await self.long.search(f"user:{user_id}", limit=limit)
        return {
            "user_id": user_id,
            "name": (u.first_name if u else None) or (u.username if u else None),
            "opinion": opinion,
            "proximity": prox.value,
            "feelings": feelings,
            "episodes": episodes,
            "facts": text_facts,
        }

    async def recall_chat(self, chat_id: int, *, limit_short: int = 30, limit_long: int = 10) -> dict:
        """Bundle chat context for prompts."""
        short = await self.short.recent(chat_id, limit=limit_short)
        long_ = await self.long.for_chat(chat_id, limit=limit_long)
        chat_op = await self.opinions.chat(chat_id)
        feelings = await self.feelings.toward_chat(chat_id)
        return {"chat_id": chat_id, "opinion": chat_op, "feelings": feelings, "short": short, "long": long_}
