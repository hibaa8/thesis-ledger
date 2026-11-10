from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class ResearchRequest(BaseModel):
    ticker: str = Field(default="NVDA", pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")
    as_of: date = Field(default_factory=date.today)
    horizon: int = Field(default=5, ge=1, le=20)
    mode: Literal["demo", "live"] = "demo"
    forecast: Literal["bootstrap", "kronos"] = "bootstrap"
    question: str = Field(
        default="What supports or challenges the investment thesis?", max_length=1200
    )
    rounds: int = Field(default=1, ge=1, le=2)
    use_memory: bool = True

    @field_validator("as_of")
    @classmethod
    def no_future(cls, value):
        if value > date.today():
            raise ValueError("Analysis date cannot be in the future")
        return value


class AgentReport(BaseModel):
    role: str
    stance: Literal["bullish", "bearish", "neutral", "abstain"]
    summary: str = Field(min_length=1, max_length=2200)
    evidence_ids: list[str] = Field(max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=8)
    invalidation: str = Field(max_length=600)


class ReviewRequest(BaseModel):
    memory_id: str
    feedback: str = Field(min_length=10, max_length=1500)
    # Narrowing scope is a deliberate source-grounded alternative to freeform rewriting.
    scope: Literal["source_snapshot_only", "retire"] = "source_snapshot_only"
