"""Export the fictional corpus through the existing React snapshot adapter."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.build_site import build


def export_react_snapshot(corpus: dict[str, Any], output: Path) -> None:
    """Write a permission-explicit synthetic site snapshot to an empty directory."""
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("React snapshot destination must be an empty directory")
    papers = corpus["papers"]
    with TemporaryDirectory(prefix="atlas-react-synthetic-") as temporary:
        private = Path(temporary)
        rows = [
            {
                "id": paper["id"],
                "title": paper["title"],
                "tier": "CORE",
                "abstract": paper["pages"][0]["text"],
                "abstract_available": True,
                "abstract_display_allowed": True,
                "evidence_level": "fulltext",
            }
            for paper in papers
        ]
        nodes = [
            {"id": paper["id"], "tier": "CORE", "x": i, "y": i % 2}
            for i, paper in enumerate(papers)
        ]
        edges = [
            {"source": paper["id"], "target": target, "type": "citation", "weight": 1}
            for paper in papers
            for target in paper["cites"]
        ]
        matrix_rows = {}
        for paper in papers:
            page = paper["pages"][0]
            matrix_rows[paper["id"]] = {
                "cells": {
                    "synthetic": {
                        "value": "yes",
                        "quote": page["text"],
                        "display_allowed": True,
                        "location": "PDF p. " + str(page["page"]),
                        "model": "fixed synthetic fixture",
                    }
                }
            }
        datasets = {
            "papers": rows,
            "analytics": {"nodes": nodes, "edges": edges},
            "matrix": {
                "columns": [{"id": "synthetic", "label": "Synthetic page evidence"}],
                "rows": matrix_rows,
            },
            "benchmarks": {"papers": []},
        }
        for name, value in datasets.items():
            (private / (name + ".private.json")).write_text(json.dumps(value), encoding="utf8")
        config = {
            "atlas": {
                "id": "synthetic-atlas",
                "title": "SYNTHETIC DATA — Agent Memory Atlas",
                "description": "All papers, page passages, vectors and citations are fictional.",
                "defaultView": "citation",
                "projectAbstract": {
                    "placeholder": True,
                    "text": "Synthetic demonstration only; no real research evidence.",
                },
            },
            "snapshot": {"id": corpus["snapshot"]},
            "limitations": ["Synthetic fixture; no real papers, citations or research findings."],
        }
        build(private, output, config)
