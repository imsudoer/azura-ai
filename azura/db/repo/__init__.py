"""Repositories: one module per entity, plus a Repos facade."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from azura.db.repo.archive import ArchiveRepo
from azura.db.repo.attention import AttentionRepo
from azura.db.repo.chats import ChatsRepo
from azura.db.repo.episodes import EpisodesRepo
from azura.db.repo.feelings import FeelingsRepo
from azura.db.repo.gifs import GifsRepo
from azura.db.repo.journal import JournalRepo
from azura.db.repo.kv import KVRepo
from azura.db.repo.memory import MemoryRepo
from azura.db.repo.messages import MessagesRepo
from azura.db.repo.mood import MoodRepo
from azura.db.repo.opinions import OpinionsRepo
from azura.db.repo.presence import PresenceRepo
from azura.db.repo.relationships import RelationshipsRepo
from azura.db.repo.stickers import StickersRepo
from azura.db.repo.users import UsersRepo


class Repos:
    """One-shot facade aggregating all repositories around a single session."""

    def __init__(self, s: AsyncSession) -> None:
        self.s = s
        self.chats = ChatsRepo(s)
        self.users = UsersRepo(s)
        self.messages = MessagesRepo(s)
        self.archive = ArchiveRepo(s)
        self.memory = MemoryRepo(s)
        self.episodes = EpisodesRepo(s)
        self.opinions = OpinionsRepo(s)
        self.feelings = FeelingsRepo(s)
        self.relationships = RelationshipsRepo(s)
        self.mood = MoodRepo(s)
        self.presence = PresenceRepo(s)
        self.stickers = StickersRepo(s)
        self.gifs = GifsRepo(s)
        self.journal = JournalRepo(s)
        self.kv = KVRepo(s)
        self.attention = AttentionRepo(s)


__all__ = ["Repos"]
