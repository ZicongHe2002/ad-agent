"""Persistence repositories.

Repositories deliberately contain no policy decisions.  Services own transaction
boundaries and use these helpers to keep SQLAlchemy statements consistent.
"""

from .base import BaseRepository

__all__ = ["BaseRepository"]
