from datetime import date
from pydantic import BaseModel


class JournalCreate(BaseModel):
    title: str
    body: str | None = None
    asset_id: int | None = None
    entry_date: date | None = None


class JournalUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    asset_id: int | None = None
    entry_date: date | None = None
