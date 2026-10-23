"""Data models for ComposeWhy.

Strict invariant: NO SECRET VALUES are ever stored on these models.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass(frozen=True)
class SourceRef:
    kind: str  # service_environment | service_env_file | project_env | shell | image_env
    path: Optional[str]
    line: Optional[int]
    key: str

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
        }
        return d


@dataclass(frozen=True)
class Candidate:
    source: SourceRef
    outcome: str  # winner | overridden | unused | unknown
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = self.source.to_dict()
        d["outcome"] = self.outcome
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class ExplainResult:
    service: str
    variable: str
    status: str  # explained | unknown | error
    effective_presence: str  # present | absent | unknown
    winner: Optional[SourceRef] = None
    interpolation_source: Optional[str] = None
    candidates: List[Candidate] = field(default_factory=list)
    reason_code: str = ""
    explanation: str = ""
    warnings: List[str] = field(default_factory=list)
    exit_code: int = 0

    def to_dict(self, product_version: str = "0.1.0") -> Dict[str, Any]:
        winner_dict = None
        if self.winner:
            winner_dict = self.winner.to_dict()
            if self.interpolation_source:
                winner_dict["interpolation_source"] = self.interpolation_source

        return {
            "schema_version": 1,
            "product_version": product_version,
            "service": self.service,
            "variable": self.variable,
            "status": self.status,
            "effective_presence": self.effective_presence,
            "winner": winner_dict,
            "candidates": [c.to_dict() for c in self.candidates],
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "warnings": list(self.warnings),
        }
