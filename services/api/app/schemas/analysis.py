"""Typed API input/output contracts."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MVP_SKILLS = {
    "appsec.secrets-detection",
    "engineering.test-inventory",
}


class AnalysisCreate(BaseModel):
    repository_url: str = Field(min_length=1, max_length=2048)
    ref: str | None = Field(default=None, min_length=1, max_length=255)
    profile: Literal["mvp-python"] = "mvp-python"
    skills: list[str] = Field(
        default_factory=lambda: ["appsec.secrets-detection", "engineering.test-inventory"],
        max_length=5,
    )

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("A lista de skills não pode conter duplicatas.")
        unknown = sorted(set(values) - MVP_SKILLS)
        if unknown:
            raise ValueError(f"Skills não habilitadas no MVP: {', '.join(unknown)}")
        return values


class AnalysisQueued(BaseModel):
    id: str
    repository_id: str
    status: str
    stage: str
    events_url: str
    analysis_url: str


FindingReviewStatus = Literal[
    "confirmed",
    "needs_review",
    "not_reproducible",
    "accepted_risk",
    "false_positive",
    "fixed_in_revision",
]


class FindingStatusUpdate(BaseModel):
    status: FindingReviewStatus


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class NodeFilter(BaseModel):
    node_type: str | None = None
    relation_type: str | None = None


class EvidenceLocation(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None
    commit_sha: str
    evidence_type: str
    redacted: bool = True


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    skill_id: str
    skill_version: str
    finding_key: str
    category: str
    severity: str
    status: str
    confidence_label: str
    title: str
    summary: str
    impact: str
    recommendation: str
    limitations: list[str]
    evidence: list[dict[str, object]]


class QuestionScope(BaseModel):
    node_ids: list[str] = Field(default_factory=list, max_length=20)
    paths: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("node_ids")
    @classmethod
    def validate_node_ids(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[a-f0-9]{32}", value) for value in values):
            raise ValueError("O escopo contém um identificador de nó inválido.")
        return list(dict.fromkeys(values))

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            path = value.strip()
            if (
                not path
                or len(path) > 1024
                or path.startswith("/")
                or "\\" in path
                or any(part in {".", ".."} for part in path.split("/"))
            ):
                raise ValueError("O escopo deve conter caminhos relativos válidos do repositório.")
            normalized.append(path)
        return list(dict.fromkeys(normalized))


class AnalysisQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=1500)
    scope: QuestionScope = Field(default_factory=QuestionScope)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("A pergunta precisa ter pelo menos 3 caracteres.")
        return normalized
