"""
Minimal feedback storage — appends to a local JSON Lines file.

No database needed for a hackathon-scale project. Each diagnosis gets
a UUID; feedback references that UUID. Good enough to demo "the system
learns from usage" without standing up real infrastructure.
"""

import json
import os
import uuid
from datetime import datetime, timezone

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "feedback_log.jsonl")


def new_diagnosis_id() -> str:
    return str(uuid.uuid4())


def record_feedback(diagnosis_id: str, log_text: str, diagnosis: dict, rating: str) -> None:
    """
    rating: "up" or "down"
    Appends one JSON line per feedback event — never overwrites history.
    """
    entry = {
        "diagnosis_id": diagnosis_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rating": rating,
        "log_excerpt": log_text[:300],
        "diagnosis": diagnosis,
    }
    with open(FEEDBACK_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
