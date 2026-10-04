"""Canonical, validated VideoBrief domain models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videobrief import SCHEMA_VERSION


class TranscriptRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    time: str
    seconds: int = Field(ge=0)
    end_seconds: int = Field(default=0, ge=0)
    text: str = Field(min_length=1)
    source: str = "transcript"


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    evidence_id: str = Field(min_length=1)
    time: str
    seconds: int = Field(ge=0)
    end_seconds: int = Field(default=0, ge=0)
    quote: str = Field(min_length=1)
    source: str = "transcript"


class Insight(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    claim_type: Literal["video_explicit", "context_summary", "system_inference"] = "context_summary"
    audit_status: Literal["supported", "partial", "local"] = "local"
    confidence: Literal["high", "medium", "low"] = "medium"
    time: str = ""
    seconds: int = Field(default=0, ge=0)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class DecisionBrief(BaseModel):
    model_config = ConfigDict(extra="allow")

    question: str = ""
    answer: str = ""
    takeaways: list[Insight] = Field(default_factory=list, max_length=3)
    value: str = ""
    watch_verdict: Literal[
        "required", "recommended", "not_required",
        "直接阅读即可", "只需回看关键片段", "建议观看原视频",
    ]
    watch_reason: str = ""
    watch_seconds: int = Field(default=0, ge=0)
    limitation: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class Brief(BaseModel):
    """Current normalized aggregate.

    Raw history rows must pass through the compatibility projector before this
    model is used.  Extra fields are retained during the strangler migration so
    legacy API consumers keep their current JSON shape.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = SCHEMA_VERSION
    title: str = Field(min_length=1)
    summary: str = ""
    source: str
    url: str = ""
    content_type: str = "lecture"
    evidence_store: list[Evidence] = Field(default_factory=list)
    key_insights: list[Insight] = Field(default_factory=list)
    decision_brief: DecisionBrief
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    content_model: dict[str, Any] = Field(default_factory=dict)
    must_watch_segments: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    agent: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_evidence_references(self) -> "Brief":
        available = {item.evidence_id for item in self.evidence_store}
        referenced: set[str] = set()
        for insight in self.key_insights:
            referenced.update(insight.evidence_ids)
        for insight in self.decision_brief.takeaways:
            referenced.update(insight.evidence_ids)
        referenced.update(self.decision_brief.evidence_ids)
        for item in self.content_model.get("items", []):
            if isinstance(item, dict):
                referenced.update(str(value) for value in item.get("evidence_ids", []) if value)
        unknown = sorted(referenced - available)
        if unknown:
            raise ValueError(f"存在未知 Evidence ID：{', '.join(unknown)}")
        return self
