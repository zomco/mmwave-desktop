"""Structured validation errors safe to return through product APIs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    path: str
    code: str
    message: str


class TimelineValidationError(ValueError):
    """Raised when a timeline document violates the timeline.v1 contract."""

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(f"{item.path}: {item.message}" for item in issues[:5])
        if len(issues) > 5:
            summary += f"; and {len(issues) - 5} more issue(s)"
        super().__init__(summary or "Invalid timeline document")

