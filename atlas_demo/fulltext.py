"""Adapt the fictional page fixture to the existing PDF-page FTS pipeline."""

import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.build_fulltext_rag import build
from server.fulltext import FulltextIndex


def retrieve_pages(papers: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Build a temporary index from invented page records, then retrieve scoped passages."""
    with TemporaryDirectory(prefix="atlas-synthetic-") as temporary:
        base = Path(temporary)
        source, private, index = base / "source", base / "private", base / "index"
        (source / "records").mkdir(parents=True)
        (source / "pages").mkdir()
        private.mkdir()
        (private / "papers.private.json").write_text(
            json.dumps([{"id": p["id"], "title": p["title"], "tier": "CORE"} for p in papers])
        )
        for paper in papers:
            sha = hashlib.sha256(paper["id"].encode()).hexdigest()
            record = {
                "paper_id": paper["id"],
                "pdf_sha256": sha,
                "identity_status": "title_match",
                "status": "extracted",
            }
            (source / "records" / (sha + ".json")).write_text(json.dumps(record))
            with gzip.open(source / "pages" / (sha + ".json.gz"), "wt", encoding="utf8") as handle:
                json.dump({"pdf_sha256": sha, "pages": paper["pages"]}, handle)
        config = {
            "id": "synthetic-fts-v1",
            "accepted_identity_statuses": ["title_match"],
            "expected_papers": len(papers),
            "expected_excluded_files": 0,
            "chunk_characters": 2800,
            "chunk_overlap_characters": 300,
            "minimum_chunk_characters": 1,
            "global_lexical_candidates": 80,
            "semantic_paper_candidates": 24,
            "semantic_paper_passages": 3,
            "rerank_candidates": 60,
            "evidence_passages": 12,
            "max_passages_per_paper": 3,
            "rrf_constant": 60,
        }
        config_path = base / "config.json"
        config_path.write_text(json.dumps(config))
        build(source, private, index, config_path)
        results, _ = FulltextIndex(index).retrieve(query, {p["id"] for p in papers})
        return [{"paper_id": r["paper_id"], "page": r["page"], "text": r["span"]} for r in results]
