from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Classification:
    intent: str
    confidence: float
