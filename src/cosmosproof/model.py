"""Findings and the evidence behind each one."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Reading = Literal["cost", "risk", "compliance"]
Confidence = Literal["high", "medium", "low"]
Kind = Literal["unused_table", "orphan_path", "unused_personal_data", "unused_producer"]


class Evidence(BaseModel):
    source: str = Field(description="Where the signal came from, e.g. system.access.table_lineage.")
    signal: str = Field(description="What was observed, in plain words.")
    observed_at: datetime | None = Field(None, description="Timestamp of the observation, if any.")


class Finding(BaseModel):
    id: str
    reading: Reading
    kind: Kind
    asset: str
    owner: str | None = None
    size_bytes: int = 0
    monthly_cost: float | None = None
    currency: str | None = None
    confidence: Confidence
    evidence: list[Evidence]
    coverage_notes: list[str] = []
    recommendation: str
    details: dict[str, Any] = {}
    window_days: int
    reference_date: date
    proof_hash: str = ""

    def seal(self) -> Finding:
        """Hashes everything that supports the verdict, so a later run can prove it is unchanged."""
        payload = self.model_dump(mode="json", exclude={"proof_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.proof_hash = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        return self


class Report(BaseModel):
    tool_version: str
    generated_at: datetime
    reference_date: date
    window_days: int
    findings: list[Finding]
    coverage_notes: list[str] = []

    def totals(self) -> dict[str, Any]:
        by_reading: dict[str, int] = {"cost": 0, "risk": 0, "compliance": 0}
        costs: dict[str, float] = {}
        size = 0
        for f in self.findings:
            by_reading[f.reading] += 1
            if f.reading == "cost":
                size += f.size_bytes
                if f.monthly_cost is not None and f.currency:
                    costs[f.currency] = costs.get(f.currency, 0.0) + f.monthly_cost
        return {
            "findings": len(self.findings),
            "by_reading": by_reading,
            "unused_bytes": size,
            # Storage uses the customer's rates and compute uses list prices, possibly in
            # different currencies: never add them together.
            "monthly_cost": {c: round(v, 2) for c, v in sorted(costs.items())},
        }


def finding_id(kind: str, asset: str) -> str:
    return hashlib.sha256(f"{kind}:{asset}".encode()).hexdigest()[:12]
