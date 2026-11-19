"""Backward-compatible aliases for request contracts moved to Application.

New code should import these boundary DTOs from
``coalition_travel.application.request_contracts``. This module remains for
existing callers that used the historical import path.
"""

from coalition_travel.application.request_contracts import (
    TravelerProfileDraft,
    TravelRequestDraft,
)

__all__ = ["TravelRequestDraft", "TravelerProfileDraft"]
