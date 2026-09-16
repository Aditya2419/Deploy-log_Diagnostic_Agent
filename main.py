"""
Deployment Log Root-Cause Agent — minimal FastAPI backend.

Accepts a raw deployment/build log, sends it to an LLM with a
structured diagnostic prompt, and returns JSON with:
  failure_summary, root_cause, confidence, suggested_fix,
  fix_command, category

Run:
    pip install -r requirements.txt
    export OPENAI_API_KEY="sk-..."      # or swap provider, see call_llm()
    uvicorn main:app --reload

Test:
    curl -X POST http://127.0.0.1:8000/diagnose \
         -H "Content-Type: application/json" \
         -d '{"log": "Error: AccessDenied when calling PutObject on S3 bucket..."}'
"""

import json
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag import reference_store
from log_source import detect_source
from feedback import new_diagnosis_id, record_feedback
from notify import notify

load_dotenv()  # reads .env in the project root and loads it into os.environ

app = FastAPI(title="Deployment Log Root-Cause Agent")

# Allow a local/static frontend to call this during the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """You are a DevOps incident-analysis assistant. You will be given a raw
deployment or build log (from GitHub Actions, Kubernetes, Terraform,
or similar). Your job is to diagnose the failure and respond ONLY with
valid JSON in this exact structure — no markdown, no preamble:

{
  "failure_summary": "one sentence: what failed and where",
  "root_cause": "the most likely underlying cause, 2-3 sentences",
  "confidence": "high | medium | low",
  "suggested_fix": "concrete steps to resolve it, as a short numbered list",
  "fix_command": "a single CLI/Terraform/kubectl command if applicable, or null",
  "category": "one of: IAM/permissions, networking, resource-limits, configuration, dependency, state-management, other"
}

Rules:
- If the log doesn't contain enough information, set confidence to "low"
  and say what additional info would help in root_cause.
- Never invent specifics (resource names, regions) not present in the log.
- Keep suggested_fix actionable, not generic ("check your IAM policy" is
  too vague — name the specific permission/resource from the log).
"""


class DiagnoseRequest(BaseModel):
    log: str


class DiagnoseResponse(BaseModel):
    diagnosis_id: str
    failure_summary: str
    root_cause: str
    confidence: str
    suggested_fix: str
    fix_command: Optional[str] = None
    category: str
    detected_source: str
    matched_past_incident_id: Optional[str] = None
    matched_past_incident_similarity: Optional[float] = None


class FeedbackRequest(BaseModel):
    diagnosis_id: str
    log: str
    diagnosis: dict
    rating: str  # "up" or "down"


def call_llm(log_text: str, matched_incident: Optional[dict], detected_source: str) -> dict:
    """
    Sends the log to an LLM and returns the parsed JSON diagnosis.

    Default: Groq's free tier via its OpenAI-compatible endpoint — no
    card required, 1,000 requests/day. Uses the OpenAI SDK pointed at
    a different base_url, so swapping to real OpenAI, Together, or a
    hackathon sponsor's credits later is a one-line change (just drop
    the base_url override and use the right key/model).

    If a similar past incident was retrieved (see rag.py), it's added
    as grounding context so the model can reason from a real precedent
    instead of purely general knowledge. The detected source (see
    log_source.py) is passed as a hint so the model applies the right
    mental model (Terraform vs Kubernetes vs cloud CLI, etc.).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Missing GROQ_API_KEY environment variable. Get a free "
                   "key at https://console.groq.com (no card required).",
        )

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    user_content = f"Detected log source: {detected_source}\n\n"
    user_content += f"Here is the deployment log:\n\n---\n{log_text}\n---\n\n"

    if matched_incident:
        user_content += (
            "A similar past incident was found in the reference history "
            f"(similarity score: {matched_incident['similarity']}):\n"
            f"- Category: {matched_incident['category']}\n"
            f"- Root cause: {matched_incident['root_cause']}\n"
            f"- Fix: {matched_incident['fix']}\n\n"
            "Use this as context if relevant, but base your diagnosis on "
            "the actual log above — don't assume it's the same issue if "
            "the log doesn't support it.\n\n"
        )

    user_content += "Diagnose this failure."

    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",  # confirmed live on Groq free tier, supports json_mode
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail=f"Model did not return valid JSON: {raw[:300]}",
        )


@app.get("/")
def health():
    return {"status": "ok", "service": "deployment-log-root-cause-agent"}


@app.post("/diagnose", response_model=DiagnoseResponse)
def diagnose(request: DiagnoseRequest):
    if not request.log or not request.log.strip():
        raise HTTPException(status_code=400, detail="Log text is empty.")

    source = detect_source(request.log)
    matched_incident = reference_store.find_best_match(request.log)
    result = call_llm(request.log, matched_incident, source)

    # Fill in any missing keys defensively so the response model doesn't 500
    # if the model drops a field.
    defaults = {
        "failure_summary": "Unable to summarize.",
        "root_cause": "Unable to determine.",
        "confidence": "low",
        "suggested_fix": "Insufficient information.",
        "fix_command": None,
        "category": "other",
    }
    defaults.update(result)
    defaults["diagnosis_id"] = new_diagnosis_id()
    defaults["detected_source"] = source

    if matched_incident:
        defaults["matched_past_incident_id"] = matched_incident["id"]
        defaults["matched_past_incident_similarity"] = matched_incident["similarity"]

    notify(request.log, defaults)  # no-op if WEBHOOK_URL isn't configured

    return DiagnoseResponse(**defaults)


@app.post("/feedback")
def feedback(request: FeedbackRequest):
    if request.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'.")

    record_feedback(request.diagnosis_id, request.log, request.diagnosis, request.rating)
    return {"status": "recorded"}
