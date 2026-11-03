"""Validated synthetic input, recoverable cache, and existing Atlas analytics."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from importlib.resources import files
from typing import Any

import numpy as np
from scripts.analytics_final import project_ranking, relationship_edges
from .fulltext import retrieve_pages


def load_corpus(path: Path | None) -> dict[str, Any]:
    """Load an explicit file, or the packaged synthetic fixture."""
    try:
        data = path.read_text() if path else files("atlas_demo").joinpath("corpus.json").read_text()
        value = json.loads(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read corpus configuration: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Corpus must be a JSON object")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _vector(value: Any, dimensions: int | None = None) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid vector") from exc
    if (
        vector.ndim != 1
        or not vector.size
        or (dimensions is not None and vector.size != dimensions)
        or not np.isfinite(vector).all()
        or not math.isfinite(float(np.linalg.norm(vector)))
        or np.linalg.norm(vector) == 0
    ):
        raise ValueError("Invalid vector: dimensions, finite values and nonzero norm required")
    return vector / np.linalg.norm(vector)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(_canonical(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def run_demo(corpus: dict[str, Any], output: Path) -> dict[str, Any]:
    """Rank fixed vectors and export citation edges; per-record cache is atomic."""
    if (
        corpus.get("schema_version") != 1
        or not isinstance(corpus.get("snapshot"), str)
        or not isinstance(corpus.get("provenance"), str)
    ):
        raise ValueError("Expected schema_version 1, snapshot and provenance")
    papers = corpus.get("papers")
    query = corpus.get("query")
    if (
        not isinstance(papers, list)
        or not papers
        or not isinstance(query, dict)
        or not isinstance(query.get("text"), str)
    ):
        raise ValueError("Expected nonempty papers and query text")
    q = _vector(query.get("vector"))
    ids: list[str] = []
    vectors = []
    pages = {}
    pairs: list[tuple[str, str]] = []
    hits = misses = 0
    for paper in papers:
        if (
            not isinstance(paper, dict)
            or not isinstance(paper.get("id"), str)
            or not paper["id"]
            or not isinstance(paper.get("title"), str)
        ):
            raise ValueError("Each paper needs an id and title")
        pid = paper["id"]
        if pid in ids:
            raise ValueError(f"duplicate paper id: {pid}")
        ids.append(pid)
        vector = _vector(paper.get("vector"), len(q))
        paper_pages = paper.get("pages")
        citations = paper.get("cites")
        if (
            not isinstance(paper_pages, list)
            or not paper_pages
            or not all(
                isinstance(p, dict)
                and isinstance(p.get("page"), int)
                and p["page"] > 0
                and isinstance(p.get("text"), str)
                and p["text"].strip()
                for p in paper_pages
            )
        ):
            raise ValueError(f"Invalid page records for {pid}")
        if not isinstance(citations, list) or not all(isinstance(c, str) for c in citations):
            raise ValueError(f"Invalid citations for {pid}")
        identity = {
            "version": 1,
            "snapshot": corpus["snapshot"],
            "provenance": corpus["provenance"],
            "paper": paper,
            "dimensions": len(q),
            "preprocessing": "l2-normalize-v1",
            "model": "fixed-synthetic",
            "task": "retrieval.document",
        }
        key = hashlib.sha256(_canonical(identity).encode()).hexdigest()
        path = output / "cache" / (key + ".json")
        expected = {"key": key, "identity": identity, "vector": vector.tolist()}
        try:
            cached = json.loads(path.read_text())
            if cached != expected:
                raise ValueError("cache mismatch")
            _vector(cached["vector"], len(q))
            hits += 1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            _atomic_json(path, expected)
            misses += 1
        vectors.append(vector)
        pages[pid] = paper_pages[0]
        pairs.extend((pid, target) for target in citations)
    if any(target not in ids for _, target in pairs):
        raise ValueError("Citation target must be a corpus ID")
    ranks = project_ranking(ids, np.array(vectors), q)
    edges, _ = relationship_edges(ids, pairs)
    results = [
        {**row, "page": pages[row["id"]]["page"], "text": pages[row["id"]]["text"]} for row in ranks
    ]
    result = {
        "label": "SYNTHETIC DATA",
        "schema_version": 1,
        "snapshot": corpus["snapshot"],
        "provenance": corpus["provenance"],
        "query": query["text"],
        "fts_results": retrieve_pages(papers, query["text"]),
        "results": results,
        "edges": edges,
        "cache": {"hits": hits, "misses": misses},
    }
    _atomic_json(output / "report.json", result)
    template = files("atlas_demo").joinpath("report.html").read_text()
    embedded = _canonical(result).replace("<", "\\u003c")
    (output / "index.html").write_text(template.replace("__REPORT__", embedded), encoding="utf-8")
    return result
