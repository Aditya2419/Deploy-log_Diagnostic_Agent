"""
Lightweight retrieval over past reference incidents.

Uses TF-IDF + cosine similarity (scikit-learn) instead of a vector DB
or embeddings API — fast, free, and plenty accurate for a small
reference set (a handful to a few dozen examples). Good enough to
show "this agent recognizes patterns it's seen before" in a demo
without adding infra or API cost.

If you later want real semantic matching (e.g. examples with very
different wording but the same meaning), swap this for an embeddings
call — the interface (find_best_match) stays the same either way.
"""

import json
import os
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

REFERENCE_PATH = os.path.join(os.path.dirname(__file__), "reference_examples.json")
SIMILARITY_THRESHOLD = 0.5  # genuine matches score ~0.85-0.95; false positives score ~0.2-0.35


class ReferenceStore:
    def __init__(self, path: str = REFERENCE_PATH):
        with open(path, "r") as f:
            self.examples = json.load(f)

        corpus = [ex["log_excerpt"] for ex in self.examples]
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform(corpus)

    def find_best_match(self, log_text: str) -> Optional[dict]:
        """
        Returns the closest matching reference example plus its
        similarity score, or None if nothing clears the threshold.
        """
        if not self.examples:
            return None

        query_vec = self.vectorizer.transform([log_text])
        scores = cosine_similarity(query_vec, self.matrix)[0]

        best_idx = scores.argmax()
        best_score = float(scores[best_idx])

        if best_score < SIMILARITY_THRESHOLD:
            return None

        match = dict(self.examples[best_idx])
        match["similarity"] = round(best_score, 3)
        return match


# Loaded once at import time; reused across requests.
reference_store = ReferenceStore()