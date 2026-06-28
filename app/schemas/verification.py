from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VerificationResult:
    confidence: float
    escalated: bool
    needs_human_reason: str | None
