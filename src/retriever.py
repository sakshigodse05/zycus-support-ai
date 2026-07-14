"""Knowledge-base retrieval (the 'R' in RAG).

The corpus is small (~9 markdown docs, ~700 lines). A TF-IDF + cosine-similarity
search is therefore faster, cheaper, fully offline and deterministic compared to
an embedding model + vector DB, with no measurable quality loss at this scale.
Swapping in embeddings later means changing only `_vectorise` and `search`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import KB_DIR


@dataclass
class Chunk:
    """One retrievable slice of the knowledge base."""
    doc_path: str      # e.g. "products/databridge-pro.md"
    heading: str       # nearest markdown heading, kept as retrieval metadata
    text: str

    def as_context(self) -> str:
        return f"[Source: {self.doc_path} — {self.heading}]\n{self.text}"


def _split_into_chunks(markdown: str, doc_path: str) -> List[Chunk]:
    """Split on '---' horizontal rules (major section boundaries), per DATA_SCHEMA.md."""
    chunks: List[Chunk] = []
    for section in re.split(r"\n---+\n", markdown):
        section = section.strip()
        if len(section) < 40:          # skip empty / trivial fragments
            continue
        headings = re.findall(r"^#{1,4}\s+(.*)$", section, flags=re.MULTILINE)
        heading = headings[0].strip() if headings else "Overview"
        chunks.append(Chunk(doc_path=doc_path, heading=heading, text=section))
    return chunks


@lru_cache(maxsize=1)
def _load_index():
    """Read every .md file, chunk it, and build the TF-IDF matrix once."""
    chunks: List[Chunk] = []
    for path in sorted(KB_DIR.rglob("*.md")):
        rel = path.relative_to(KB_DIR).as_posix()
        chunks.extend(_split_into_chunks(path.read_text(encoding="utf-8"), rel))

    if not chunks:
        raise FileNotFoundError(f"No markdown files found under {KB_DIR}")

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),      # capture phrases like "connection timeout"
        sublinear_tf=True,
        min_df=1,
    )
    matrix = vectorizer.fit_transform([f"{c.heading}\n{c.text}" for c in chunks])
    return chunks, vectorizer, matrix


def search(query: str, top_k: int = 3, min_score: float = 0.05) -> List[dict]:
    """Return the top_k most relevant KB chunks for a query.

    Results below `min_score` are dropped so that an irrelevant ticket returns
    an empty list rather than a confidently wrong document.
    """
    if not query or not query.strip():
        return []

    chunks, vectorizer, matrix = _load_index()
    scores = cosine_similarity(vectorizer.transform([query]), matrix)[0]

    ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)[:top_k]
    return [
        {
            "doc_path": chunks[i].doc_path,
            "heading": chunks[i].heading,
            "score": round(float(score), 4),
            "text": chunks[i].text,
        }
        for i, score in ranked
        if score >= min_score
    ]


def build_context(query: str, top_k: int = 3) -> str:
    """Format the top KB hits into a single string ready to paste into a prompt."""
    hits = search(query, top_k=top_k)
    if not hits:
        return "No relevant knowledge-base articles found."
    return "\n\n".join(
        f"[Source: {h['doc_path']} — {h['heading']}]\n{h['text']}" for h in hits
    )