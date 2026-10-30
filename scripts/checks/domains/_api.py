"""Stable API for domain artifact quality plugins."""
from dataclasses import dataclass, field


@dataclass
class Result:
    check: str
    state: str
    reasons: list = field(default_factory=list)


@dataclass
class Context:
    repo: str
    registry: dict
    artifact_path: str
    artifacts: dict
    tools: object
