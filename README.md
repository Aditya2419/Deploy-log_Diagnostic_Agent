# Deployment Log Root-Cause Agent — Backend

Minimal FastAPI service. Takes a raw deployment/build log, sends it to
an LLM with a structured diagnostic prompt, and returns a JSON diagnosis.

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."      # or whatever key your hackathon sponsor gives you
uvicorn main:app --reload
```

Server runs at `http://127.0.0.1:8000`.

## Test it

```bash
curl -X POST http://127.0.0.1:8000/diagnose \
     -H "Content-Type: application/json" \
     -d '{"log": "Error: User: arn:aws:iam::123456789012:user/deploy-bot is not authorized to perform: s3:PutObject on resource: arn:aws:s3:::my-app-bucket/config.json"}'
```

Expected response shape:

```json
{
  "failure_summary": "...",
  "root_cause": "...",
  "confidence": "high | medium | low",
  "suggested_fix": "...",
  "fix_command": "... or null",
  "category": "IAM/permissions | networking | resource-limits | configuration | dependency | state-management | other"
}
```

## Swapping the LLM provider

If your hackathon sponsor gives you Gemini, Anthropic, Groq, or
another provider instead of OpenAI credits, you only need to edit the
`call_llm()` function in `main.py` — everything else (the FastAPI
routes, the response model, the prompt) stays the same.

## Good test logs to use in your demo

Real failure logs are far more convincing than made-up ones. Good
categories to have on hand for the demo:
- An IAM/permissions denial (e.g. AccessDenied on a cloud API call)
- A Terraform state lock or state-mismatch error
- A Kubernetes pod stuck in `CrashLoopBackOff` with an OOMKilled reason
- A GitHub Actions step failing on a missing secret/env var

Having one log from each category ready to paste in during your demo
shows the agent generalizes across failure types, not just one.
