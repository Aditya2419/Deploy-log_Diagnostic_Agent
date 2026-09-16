"""
Optional Slack/Discord webhook notification.

If WEBHOOK_URL is set in the environment, posts a formatted summary of
each diagnosis. Both Slack incoming webhooks and Discord webhooks
accept a simple {"content": "..."} or {"text": "..."} JSON body, so
one function covers both — just paste whichever webhook URL you have.

If WEBHOOK_URL isn't set, this silently does nothing — the feature is
fully optional and never blocks a diagnosis from returning.
"""

import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()  # defensive: ensures .env is read even if this module is
                # imported before main.py calls load_dotenv() itself


def _truncate_at_word(text: str, limit: int) -> str:
    """Truncates to `limit` chars without cutting a word in half."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "..."


def _format_fix_steps(fix_text: str) -> str:
    """
    The LLM sometimes returns suggested_fix as a single run-on string
    ("1. Do X. 2. Do Y. 3. Do Z.") with no real line breaks, which
    renders as one paragraph in Discord/Slack. This splits it into
    one numbered line per step regardless of whether the model
    included newlines or not.
    """
    parts = re.split(r'(?=\d+\.\s)', fix_text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    return "\n".join(parts)


def notify(log_excerpt: str, diagnosis: dict) -> None:
    webhook_url = os.environ.get("WEBHOOK_URL")  # read fresh, not cached at import time

    if not webhook_url:
        print("[webhook] WEBHOOK_URL not set — skipping notification.")
        return  # feature not configured — no-op

    fix_steps = _format_fix_steps(str(diagnosis.get('suggested_fix', '')))
    fix_command = diagnosis.get('fix_command')

    message = (
        f"*New deployment failure diagnosed*\n"
        f"**Category:** {diagnosis.get('category')}\n"
        f"**Confidence:** {diagnosis.get('confidence')}\n"
        f"**Summary:** {diagnosis.get('failure_summary')}\n"
        f"**Suggested fix:**\n{fix_steps}\n"
    )

    if fix_command:
        message += f"**Fix command:**\n```\n{fix_command}\n```\n"

    message += f"```\n{_truncate_at_word(log_excerpt, 500)}\n```"

    payload = {"content": message, "text": message}  # covers both Discord and Slack keys

    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        print(f"[webhook] POST to {webhook_url[:50]}... -> status {resp.status_code}")
        if resp.status_code >= 300:
            print(f"[webhook] response body: {resp.text[:300]}")
    except requests.RequestException as e:
        # Never let a webhook failure break the actual diagnosis response —
        # but log it so it's debuggable.
        print(f"[webhook] request failed: {e}")