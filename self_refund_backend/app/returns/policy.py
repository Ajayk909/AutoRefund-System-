"""
Return policy.

Phase 1: one policy for the whole installation, read from configuration
(.env). The service always asks ``policy_for(...)`` so a later phase can
load a per-retailer, versioned policy from the database without touching
the return rules.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReturnPolicy:
    window_days: int
    retry_limit_after_rejection: int
    require_photo_for_auto_approval: bool
    capture_max_age_seconds: int


def policy_for(config, retailer_id=None):  # noqa: ARG001 - retailer used later
    return ReturnPolicy(
        window_days=config["RETURN_WINDOW_DAYS"],
        retry_limit_after_rejection=config["RETURN_RETRY_LIMIT_AFTER_REJECTION"],
        require_photo_for_auto_approval=config["REQUIRE_PHOTO_FOR_AUTO_APPROVAL"],
        capture_max_age_seconds=config["CAPTURE_MAX_AGE_SECONDS"],
    )
