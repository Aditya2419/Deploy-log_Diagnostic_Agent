"""
Lightweight log-source detection.

Keyword-based, not ML-based — deliberately simple. Good enough to tag
a log as coming from Terraform, Kubernetes, GitHub Actions, or a cloud
provider's CLI/SDK, which helps the LLM apply the right mental model
without needing a heavier classifier for a hackathon-scale project.
"""

SOURCE_SIGNATURES = {
    "terraform": ["terraform", "tfstate", "terraform apply", "terraform plan", ".tf ", "hashicorp"],
    "kubernetes": ["kubectl", "crashloopbackoff", "oomkilled", "pod ", "namespace", "kubelet", "k8s"],
    "github_actions": ["github actions", "##[error]", "workflow", "npm err", "actions/checkout", "runner"],
    "aws": ["arn:aws", "botocore", "lambda", "cloudwatch", "s3:", "ec2", "iam::"],
    "azure": ["azure", "arm template", "resource group", "azurerm"],
    "gcp": ["gcloud", "google cloud", "gcp", "cloud run", "cloud function"],
    "docker": ["docker build", "dockerfile", "docker-compose", "image not found"],
}


def detect_source(log_text: str) -> str:
    """
    Returns the best-guess source label, or "unknown" if nothing matches.
    Case-insensitive substring matching, scored by number of hits.
    """
    text = log_text.lower()
    scores = {}

    for source, keywords in SOURCE_SIGNATURES.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            scores[source] = hits

    if not scores:
        return "unknown"

    return max(scores, key=scores.get)
