#!/usr/bin/env python3
"""Deterministic, default-deny public adapter for any configured literature atlas.

ATLAS_PRIVATE_DIR contains snapshot subdirectories. Pass --private a snapshot
folder for offline rebuilds. No network, generation, or raw archive reads occur.
"""

import argparse
import csv
import hashlib
import io
import ipaddress
import html
import json
import os
import random
import re
import shutil
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_KEYS = {"quote", "passage", "evidence_quote", "support_span", "abstract", "text_excerpt"}


def load(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def write(path, value, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        )
        + "\n"
    )


def contains_ipv4(value):
    if not isinstance(value, str):
        return False
    for candidate in re.findall(
        r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9]|\.[0-9])", value
    ):
        try:
            ipaddress.IPv4Address(candidate)
        except ipaddress.AddressValueError:
            continue
        return True
    return False


def assert_public_no_ipv4(folder):
    folder = Path(folder)
    unsafe = [
        str(p.relative_to(folder))
        for p in sorted(folder.rglob("*"))
        if p.is_file() and contains_ipv4(p.read_text())
    ]
    if unsafe:
        raise ValueError("Public IPv4 privacy gate failed in: " + ", ".join(unsafe))


def permission_filter(value, allowed=False):
    """Permission is per evidence object, never inferred from open access."""
    if isinstance(value, list):
        return [permission_filter(v, allowed) for v in value]
    if not isinstance(value, dict):
        return value
    permitted = (
        value.get("display_allowed") is True or value.get("abstract_display_allowed") is True
    )
    result = {}
    privacy_keys = []
    for key, child in value.items():
        if key in TEXT_KEYS:
            permit = (
                value.get("abstract_display_allowed") is True if key == "abstract" else permitted
            )
            blocked = contains_ipv4(child)
            result[key] = child if permit and not blocked else None
            if child and (not permit or blocked):
                result[key + "_withheld"] = True
            if blocked:
                result[key + "_withheld_reason"] = "privacy_ipv4_address"
                privacy_keys.append(key)
        elif key not in {
            "raw",
            "raw_response",
            "prompt",
            "private_text",
            "full_text",
            "embedding",
            "vector",
            "raw_path",
            "cache_path",
        }:
            result[key] = permission_filter(child)
    if "abstract" in privacy_keys:
        result["abstract_display_allowed"] = False
    if any(key != "abstract" for key in privacy_keys):
        result["display_allowed"] = False
    return result


# Diagnostics are metadata only. Unknown strings are withheld rather than
# trusting the license state of research caches or arbitrary provider payloads.
DIAGNOSTIC_STRINGS = {
    "id",
    "paper_id",
    "final_id",
    "canonical_id",
    "original_id",
    "parent_id",
    "seed_id",
    "final_ids",
    "canonical_ids",
    "parent_ids",
    "original_ids",
    "left",
    "right",
    "source",
    "target",
    "title",
    "provider",
    "endpoint",
    "query",
    "method",
    "kind",
    "search_fields",
    "status",
    "final_status",
    "prior_status",
    "decision",
    "final_reason",
    "reason",
    "tier",
    "final_tier",
    "parent_tier",
    "model",
    "requested_model",
    "precision_estimate",
    "scope",
    "snapshot",
    "parents",
    "parent_request_hash",
    "request_hash",
    "response_sha256",
    "retrieved_at",
    "source_only_definition_sha256",
    "input_sha256",
    "input_hash",
    "source_id",
    "license",
    "abstract_license",
    "license_source",
    "prior_label",
    "final_label",
    "parent_label",
    "resolution",
    "version",
    "parent_snapshot",
    "final_snapshot",
    "hash",
    "sha256",
    "label",
    "metric",
}
DIAGNOSTIC_DROP = {
    "raw",
    "body",
    "response",
    "raw_response",
    "data",
    "source_records",
    "abstract",
    "text",
    "source_text",
    "source_spans",
    "full_text",
    "prompt",
    "messages",
    "question",
    "answer",
    "quote",
    "evidence_quote",
    "tier_evidence_quote",
    "contexts",
    "candidate_events",
    "private_text",
    "cache_path",
    "raw_path",
    "parameters",
}


def diagnostic_public(value, key=""):
    if key in DIAGNOSTIC_DROP:
        return None
    if isinstance(value, dict):
        result = {}
        for name, child in value.items():
            if name in DIAGNOSTIC_DROP:
                if child:
                    result[name + "_withheld"] = True
                continue
            cleaned = diagnostic_public(child, name)
            if isinstance(child, str) and cleaned is None:
                result[name + "_withheld"] = True
            else:
                result[name] = cleaned
        return result
    if isinstance(value, list):
        return [diagnostic_public(v, key) for v in value]
    if isinstance(value, str):
        return (
            value
            if key in DIAGNOSTIC_STRINGS or key.endswith(("_hash", "_sha256", "_at"))
            else None
        )
    return value


def public_parentage(value):
    if not isinstance(value, dict):
        return {}
    public = {
        "snapshot": value.get("snapshot"),
        "parents": value.get("parents", []),
        "parent_files_sha256": {},
        "private_parent_inventories": {},
    }
    for key, inventory in value.get("parent_files_sha256", {}).items():
        if not isinstance(inventory, dict):
            continue
        if key.endswith("/public"):
            public["parent_files_sha256"][key] = inventory
        else:
            public["private_parent_inventories"][key] = {
                "files": len(inventory),
                "inventory_sha256": hashlib.sha256(
                    json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
    return public


def export_archives(out, snapshot, route):
    """Create readable metadata views; never mutate or blindly copy ancestors."""
    archives = []
    for parent in snapshot.get("parents", []):
        parent_id = parent.get("id") if isinstance(parent, dict) else parent
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", str(parent_id)):
            continue
        directory = ROOT / "data" / ("snapshot-" + str(parent_id))
        if not directory.exists():
            continue
        rows = load(directory / "papers-index.json")
        if rows is None:
            rows = load(directory / "papers.json")
        if rows is None:
            seeds = load(directory / "seeds.json", {}).get("seeds", [])
            rows = []
            for seed in seeds:
                canonical = seed.get("openalex_id") or seed.get("s2_paper_id") or seed["seed_id"]
                rows.append(
                    {
                        "id": canonical,
                        "title": seed.get("title") or seed.get("input", ""),
                        "year": seed.get("year"),
                        "venue": seed.get("venue"),
                        "seed_ids": [seed["seed_id"]],
                        "seed_groups": [seed.get("group")] if seed.get("group") else [],
                        "dois": [seed["doi"]] if seed.get("doi") else [],
                        "arxiv_ids": [seed["arxiv_id"]] if seed.get("arxiv_id") else [],
                        "source_ids": {
                            "openalex": [seed["openalex_id"]] if seed.get("openalex_id") else [],
                            "s2": [seed["s2_paper_id"]] if seed.get("s2_paper_id") else [],
                        },
                    }
                )
        rows = [metadata(p) for p in rows]
        folder = out / "archives" / str(parent_id)
        write(folder / "papers-index.json", rows)
        parent_manifest = {
            "id": parent_id,
            "records": len(rows),
            "frozen": True,
            "view": "metadata-only historical archive",
            "source_files_sha256": snapshot.get("parent_hashes", {}).get(str(parent_id), {}),
            "note": "Historical screening and cohort definitions differ from the final three-tier census. Missing historical tiers are not exclusions. Abstracts and source passages are withheld in this archive view.",
        }
        write(folder / "manifest.json", parent_manifest)
        entries = "".join(
            "<tr><td>"
            + html.escape(p["id"])
            + "</td><td>"
            + (
                '<a href="'
                + html.escape(p["link"], quote=True)
                + '">'
                + html.escape(p["title"])
                + "</a>"
                if p["link"] and p["link"].startswith(("https://", "http://"))
                else html.escape(p["title"])
            )
            + "</td><td>"
            + html.escape(str(p["year"] or ""))
            + "</td><td>"
            + html.escape(p["tier"] or "Historical tier unavailable")
            + "</td></tr>"
            for p in rows
        )
        page = (
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Historical snapshot '
            + html.escape(str(parent_id))
            + "</title><style>body{font:16px/1.6 system-ui;margin:3rem auto;padding:0 1.5rem;max-width:80rem;color:#223941;background:#fbfaf6}table{border-collapse:collapse;width:100%}th,td{padding:.6rem;text-align:left;border-bottom:1px solid #c9d4d4;vertical-align:top}a{color:#246777}td:first-child{overflow-wrap:anywhere;max-width:15rem}@media(max-width:600px){table{font-size:13px}th,td{padding:.4rem}}</style><h1>Historical snapshot "
            + html.escape(str(parent_id))
            + "</h1><p>"
            + html.escape(parent_manifest["note"])
            + "</p><p>"
            + str(len(rows))
            + ' metadata records. <a href="papers-index.json">Download metadata JSON</a> · <a href="manifest.json">Frozen source hashes</a> · <a href="'
            + html.escape(route, quote=True)
            + '">Return to current atlas</a></p><table><thead><tr><th>Identifier</th><th>Title / original source</th><th>Year</th><th>Historical tier</th></tr></thead><tbody>'
            + entries
            + "</tbody></table></html>"
        )
        (folder / "index.html").write_text(page)
        archives.append(
            {
                "id": parent_id,
                "label": "Read " + str(parent_id) + " metadata (" + str(len(rows)) + " records)",
                "url": route.rstrip("/") + "/data/archives/" + str(parent_id) + "/index.html",
            }
        )
    return archives


def publication_metadata(p):
    """Only retained type/version metadata; never infer type from title or IDs."""
    identity = str(p["id"])
    canonical = next(
        (
            v
            for v in p.get("publication_versions", [])
            if str(v.get("source_id", "")).rstrip("/")
            in {identity.rstrip("/"), identity.removeprefix("s2:").rstrip("/")}
        ),
        {},
    )
    candidates = []
    for owner in (p, canonical):
        for key in (
            "publication_type",
            "work_type",
            "openalex_type",
            "type",
            "publication_types",
            "publicationTypes",
        ):
            value = owner.get(key)
            candidates.extend(
                [value]
                if isinstance(value, str)
                else [v for v in value if isinstance(v, str)]
                if isinstance(value, list)
                else []
            )
    kinds = {
        "journal-article": "journal",
        "article-journal": "journal",
        "journalarticle": "journal",
        "proceedings-article": "conference",
        "conference-paper": "conference",
        "paper-conference": "conference",
        "conferencepaper": "conference",
        "book-chapter": "chapter",
        "bookchapter": "chapter",
        "chapter": "chapter",
        "book": "book",
        "monograph": "book",
        "dissertation": "thesis",
        "thesis": "thesis",
        "report": "report",
        "technical-report": "report",
        "dataset": "dataset",
    }
    observed = {
        kinds[v.lower().replace("_", "-")]
        for v in candidates
        if v.lower().replace("_", "-") in kinds
    }
    kind = next(iter(observed)) if len(observed) == 1 else "generic"
    year = (
        canonical.get("year")
        or p.get("venue_publication_year")
        or p.get("first_public_year")
        or p.get("year")
    )
    doi = (
        canonical.get("doi")
        or p.get("canonical_doi")
        or (p["dois"][0] if len(p.get("dois", [])) == 1 else None)
    )
    return {
        "publication_type": candidates[0] if candidates else None,
        "publication_type_observations": list(dict.fromkeys(candidates)),
        "publication_type_basis": "retained explicit metadata"
        if candidates
        else "not provided; generic export",
        "citation_kind": kind,
        "citation_year": year,
        "citation_doi": doi,
    }


def first_public_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T.*)?", value):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def metadata(p):
    authors = [
        {"id": a.get("id"), "name": a.get("name", "")}
        if isinstance(a, dict)
        else {"id": None, "name": str(a)}
        for a in p.get("authors", [])
    ]
    source_ids = p.get("source_ids", {})
    links = p.get("links") or p.get("original_links") or []
    link = p.get("link") or p.get("url")
    if not link:
        link = (
            "https://doi.org/" + p["dois"][0]
            if p.get("dois")
            else ("https://arxiv.org/abs/" + p["arxiv_ids"][0] if p.get("arxiv_ids") else None)
        )
    if not link and source_ids.get("openalex"):
        candidate = source_ids["openalex"][0]
        link = (
            candidate if candidate.startswith("https://") else "https://openalex.org/" + candidate
        )
    if not link and source_ids.get("s2"):
        link = "https://www.semanticscholar.org/paper/" + source_ids["s2"][0]
    if not link and isinstance(links, list):
        link = next(
            (
                x if isinstance(x, str) else x.get("url")
                for x in links
                if isinstance(x, str) or isinstance(x, dict)
            ),
            None,
        )
    return {
        **publication_metadata(p),
        "id": p["id"],
        "title": p.get("title", ""),
        "short_name": p.get("short_name") or p.get("display_short_name"),
        "year": p.get("first_public_year", p.get("year")),
        "first_public_date": first_public_day(p.get("first_public_date")),
        "first_public_date_precision": "day"
        if first_public_day(p.get("first_public_date"))
        else "unknown",
        "venue": p.get("venue"),
        "tier": p.get("tier"),
        "tier_reason": p.get("tier_reason"),
        "group": p.get("seed_groups", p.get("group", [])),
        "is_seed": bool(p.get("seed_ids") or p.get("is_seed")),
        "seed_ids": p.get("seed_ids", []),
        "cluster_id": p.get("cluster_id"),
        "cluster_label": p.get("cluster_label"),
        "evidence_level": p.get("evidence_level"),
        "abstract_available": bool(p.get("abstract") or p.get("abstract_available")),
        "abstract_display_allowed": p.get("abstract_display_allowed") is True
        and not contains_ipv4(p.get("abstract")),
        "open_access": p.get("open_access", True if p.get("open_access_urls") else None),
        "citations_total": p.get(
            "citations_total",
            max(
                [
                    v
                    for v in (p.get("citation_counts") or {}).values()
                    if isinstance(v, (int, float))
                ],
                default=None,
            ),
        ),
        "citations_in_corpus": p.get("citations_in_corpus"),
        "authors": authors,
        "link": link,
        "dois": p.get("dois", []),
        "arxiv_ids": p.get("arxiv_ids", []),
        "source_ids": source_ids,
    }


def citation_exports(p):
    key = "atlas" + hashlib.sha256(p["id"].encode()).hexdigest()[:12]
    names = [a["name"] for a in p["authors"]]

    def tex(value):
        return re.sub(r"([&%$#_{}])", r"\\\1", str(value or "")).replace("~", r"\textasciitilde{}")

    kind = p.get("citation_kind", "generic")
    year = p.get("citation_year") or p.get("year")
    doi = p.get("citation_doi")
    container = p.get("venue")
    entry, ris_type, csl_type = {
        "journal": ("article", "JOUR", "article-journal"),
        "conference": ("inproceedings", "CPAPER", "paper-conference"),
        "chapter": ("incollection", "CHAP", "chapter"),
        "book": ("book", "BOOK", "book"),
        "thesis": ("misc", "THES", "thesis"),
        "report": ("misc", "RPRT", "report"),
        "dataset": ("misc", "DATA", "dataset"),
    }.get(kind, ("misc", "GEN", "document"))
    fields = {
        "title": p["title"],
        "author": " and ".join(names),
        "year": year,
        "doi": doi,
        "url": ("https://doi.org/" + doi) if doi else p["link"],
    }
    if container:
        fields[
            "journal"
            if kind == "journal"
            else "booktitle"
            if kind in {"conference", "chapter"}
            else "howpublished"
        ] = container
    bib = (
        "@"
        + entry
        + "{"
        + key
        + ",\n"
        + ",\n".join(
            "  " + name + " = {" + tex(value) + "}"
            for name, value in fields.items()
            if value is not None and value != ""
        )
        + "\n}\n"
    )
    ris = ["TY  - " + ris_type, "ID  - " + p["id"], "TI  - " + p["title"]] + [
        "AU  - " + name for name in names
    ]
    ris += [
        name + "  - " + str(value)
        for name, value in [
            ("PY", year),
            ("JO" if kind == "journal" else "T2", container),
            ("DO", doi),
            ("UR", fields["url"]),
        ]
        if value
    ]
    csl = {
        "id": p["id"],
        "type": csl_type,
        "title": p["title"],
        "author": [{"literal": name} for name in names],
    }
    if year:
        csl["issued"] = {"date-parts": [[year]]}
    for name, value in [("container-title", container), ("DOI", doi), ("URL", fields["url"])]:
        if value:
            csl[name] = value
    if p.get("publication_type"):
        csl["genre"] = p["publication_type"]
    return bib, "\n".join(ris + ["ER  -", ""]), csl


def diff_snapshot(index, previous):
    old = {p["id"]: p for p in previous}
    new = {p["id"]: p for p in index}
    changed = []
    for pid in sorted(new.keys() & old.keys()):
        fields = {}
        for k in (
            "tier",
            "citations_total",
            "first_public_date",
            "year",
            "dois",
            "arxiv_ids",
            "source_ids",
        ):
            before = old[pid].get(k)
            after = new[pid].get(k)
            if before != after:
                fields[k] = {"before": before, "after": after}
        if fields:
            changed.append({"id": pid, "changes": fields})
    return {
        "additions": sorted(new.keys() - old.keys()),
        "removals": sorted(old.keys() - new.keys()),
        "changes": changed,
        "changelog": [
            "Generated from canonical metadata; removals reflect retained-cohort changes, not retractions."
        ],
    }


def validate_final_coverage(papers, analytics, matrix, benchmarks, config):
    """Reject an incomplete final Agent Memory cache; no model/network fallback."""
    atlas_id = (config.get("atlas") or {}).get("id") or config.get("atlas_id") or config.get("id")
    if atlas_id != "agent-memory":
        return
    retained = {p["id"]: p for p in papers if p["tier"] in {"CORE", "ADJACENT"}}
    core = {pid for pid, p in retained.items() if p["tier"] == "CORE"}
    nodes = analytics.get("nodes", [])
    if {n.get("id") for n in nodes} != set(retained) or len(nodes) != len(retained):
        raise ValueError("Final analytics must cover every retained canonical ID exactly once")
    columns = {c["id"] for c in config.get("capabilities", [])}
    if not columns or {c["id"] for c in matrix.get("columns", [])} != columns:
        raise ValueError("Final matrix columns do not match configured capabilities")
    rows = matrix.get("rows", {})
    if set(rows) != core:
        raise ValueError("Final matrix must cover every CORE paper exactly once")
    for pid, row in rows.items():
        cells = row.get("cells", {})
        if set(cells) != columns:
            raise ValueError("Incomplete final capability row: " + pid)
        for cell in cells.values():
            if cell.get("value") not in {"yes", "partial", "not stated"}:
                raise ValueError("Invalid final capability status: " + pid)
            quote = cell.get("quote")
            if cell["value"] in {"yes", "partial"} and (
                not quote or quote not in (retained[pid].get("abstract") or "")
            ):
                raise ValueError(
                    "Final capability evidence is not an exact acquired abstract span: " + pid
                )
    screened = benchmarks.get("papers", [])
    if {p.get("paper_id") for p in screened} != set(retained) or len(screened) != len(retained):
        raise ValueError("Final benchmark screening must cover CORE and ADJACENT exactly once")
    for row in screened:
        pid = row["paper_id"]
        abstract = retained[pid].get("abstract") or ""
        for benchmark in row.get("benchmarks", []):
            for field in benchmark.values():
                if not isinstance(field, dict):
                    raise ValueError("Invalid benchmark evidence object: " + pid)
                quote = field.get("quote")
                value = field.get("value")
                if (
                    not quote
                    or quote not in abstract
                    or not isinstance(value, str)
                    or value not in quote
                ):
                    raise ValueError(
                        "Final benchmark evidence is not an exact acquired abstract span: " + pid
                    )


def verify_determinism(private, config, previous=None):
    """Two independent public exports from frozen final files; no API/cache writes."""
    with tempfile.TemporaryDirectory(prefix="atlas-public-rebuild-") as tmp:
        first = Path(tmp) / "first"
        second = Path(tmp) / "second"
        build(private, first, config, previous)
        build(private, second, config, previous)
        left = {
            str(p.relative_to(first)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(first.rglob("*"))
            if p.is_file()
        }
        right = {
            str(p.relative_to(second)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(second.rglob("*"))
            if p.is_file()
        }
        if left != right:
            raise RuntimeError("Two cache-only final exports differ")
        return {
            "deterministic": True,
            "independent_builds": 2,
            "files_compared": len(left),
            "inventory_sha256": hashlib.sha256(
                json.dumps(left, sort_keys=True).encode()
            ).hexdigest(),
        }


def build(private, out, config, previous=None, site_data=None):
    private, out = Path(private).resolve(), Path(out).resolve()
    if private == ROOT or ROOT in private.parents:
        raise ValueError("Private data must be outside atlas-engine")
    if out.name in {"snapshot-2026-11-01-phase2", "snapshot-2026-11-01-checkpoint-1"}:
        raise ValueError("Old snapshots are immutable")
    papers = load(private / "papers.private.json")
    if isinstance(papers, dict):
        papers = papers.get("papers", [])
    if not isinstance(papers, list) or not papers:
        raise ValueError("Missing nonempty papers.private.json")
    if len({p["id"] for p in papers}) != len(papers):
        raise ValueError("Duplicate canonical IDs")
    if any(p.get("tier") not in {"CORE", "ADJACENT", "EXCLUDE"} for p in papers):
        raise ValueError("Every candidate needs a final tier")
    for name in ("analytics", "matrix", "benchmarks"):
        if not (private / (name + ".private.json")).exists():
            raise ValueError("Missing final " + name + " output")
    raw_analytics = load(private / "analytics.private.json", {})
    raw_matrix = load(private / "matrix.private.json", {})
    raw_benchmarks = load(private / "benchmarks.private.json", {})
    validate_final_coverage(papers, raw_analytics, raw_matrix, raw_benchmarks, config)
    out.mkdir(parents=True, exist_ok=True)
    (out / "citation-contexts-coverage.json").unlink(missing_ok=True)
    # Rebuild only generated directories so obsolete detail buckets cannot ship.
    for generated in ("details", "exports", "archives", "citation-contexts"):
        if (out / generated).exists():
            shutil.rmtree(out / generated)
    analytics = permission_filter(load(private / "analytics.private.json", {}))
    nodes = analytics.get("nodes", [])
    node_map = {n["id"]: n for n in nodes}
    incoming = Counter(
        e.get("target") for e in analytics.get("edges", []) if e.get("type") == "citation"
    )
    context_data = load(private / "citation_contexts.private.json", {})
    context_papers = context_data.get("papers", {}) if isinstance(context_data, dict) else {}
    context_files = {}
    retained = sorted(
        (p for p in papers if p["tier"] in {"CORE", "ADJACENT"}), key=lambda p: p["id"]
    )
    ids = {p["id"] for p in retained}
    buckets = {}
    index = []
    citations = []
    ris = []
    csl = []
    for paper in retained:
        row = metadata(paper)
        node = node_map.get(row["id"], {})
        for key in ("cluster_id", "cluster_label", "x", "y", "citations_in_corpus"):
            if node.get(key) is not None:
                row[key] = node[key]
        bucket = "details/" + hashlib.sha256(row["id"].encode()).hexdigest()[:2] + ".json"
        row["citations_in_corpus"] = incoming[row["id"]]
        if row["id"] in context_papers:
            context_file = (
                "citation-contexts/" + hashlib.sha256(row["id"].encode()).hexdigest()[:16] + ".json"
            )
            row["citation_context_file"] = context_file
            row["citation_context_count"] = len(context_papers[row["id"]].get("citations", []))
            context_files[row["id"]] = context_file
        row["detail_bucket"] = bucket
        index.append(row)
        bib, reference, citation = citation_exports(row)
        citations.append(bib)
        ris.append(reference)
        csl.append(citation)
        detail = dict(
            row,
            abstract=paper.get("abstract") if row["abstract_display_allowed"] else None,
            abstract_withheld=row["abstract_available"] and not row["abstract_display_allowed"],
            abstract_status="displayable"
            if row["abstract_display_allowed"] and paper.get("abstract")
            else (
                "withheld: privacy rule forbids address-bearing source text"
                if contains_ipv4(paper.get("abstract"))
                else (
                    "withheld: content license does not permit republication"
                    if row["abstract_available"]
                    else "unavailable from acquired sources"
                )
            ),
            bibtex=bib,
            ris=reference,
            csl=citation,
            original_links=permission_filter(paper.get("links", paper.get("original_links", []))),
            versions=permission_filter(
                paper.get("publication_versions", paper.get("versions", []))
            ),
            evidence_location="abstract",
            license=permission_filter(
                paper.get(
                    "content_license_observations",
                    paper.get("license_observations", paper.get("licenses", [])),
                )
            ),
            abstract_license=paper.get("abstract_license"),
            original_version_note=paper.get("original_version_note"),
            first_public_date_basis=paper.get("first_public_date_basis"),
            aliases=paper.get("aliases", []),
            metadata_years=paper.get("metadata_years", []),
        )
        if contains_ipv4(paper.get("abstract")):
            detail["abstract_withheld_reason"] = "privacy_ipv4_address"
        if paper.get("first_public_date") != row["first_public_date"]:
            detail["first_public_date_raw"] = paper.get("first_public_date")
        buckets.setdefault(bucket, {})[row["id"]] = detail
    edges = [
        e for e in analytics.get("edges", []) if e.get("source") in ids and e.get("target") in ids
    ]
    graph = {
        "nodes": [n for n in nodes if n.get("id") in ids],
        "edges": edges,
        "methods": analytics.get(
            "methods", analytics.get("method", analytics.get("parameters", {}))
        ),
        "method": analytics.get(
            "method", analytics.get("methods", analytics.get("parameters", {}))
        ),
        "clusters": analytics.get("clusters", []),
    }
    if not graph["nodes"]:
        graph["nodes"] = [
            {k: r.get(k) for k in ("id", "tier", "cluster_id", "x", "y")} for r in index
        ]
    limitations = permission_filter(
        config.get("limitations", config.get("atlas", {}).get("limitations", []))
    )
    counts = dict(Counter(p["tier"].lower() for p in papers))
    counts.update(
        seeds=sum(bool(p.get("seed_ids") or p.get("is_seed")) for p in retained),
        retained=len(retained),
        global_candidates=len(papers),
        edges=len(edges),
    )
    counts["limitations_count"] = len(limitations)
    counts["default_core_plus_seeds"] = sum(
        p["tier"] == "CORE" or bool(p.get("seed_ids") or p.get("is_seed")) for p in retained
    )
    counts["full_text_works"] = sum(p.get("evidence_level") == "fulltext" for p in retained)
    counts["full_text_stored"] = sum(p.get("full_text_stored") is True for p in retained)
    counts.update(
        abstract_papers=sum(r["abstract_available"] for r in index),
        metadata_papers=sum(
            p.get("evidence_level") in {"metadata", "title", "title_only"}
            or (
                p.get("evidence_level") is None
                and not p.get("abstract_available", bool(p.get("abstract")))
            )
            for p in retained
        ),
        fulltext_papers=sum(p.get("evidence_level") == "fulltext" for p in retained),
        analysis_papers=sum(p.get("evidence_level") == "analysis" for p in retained),
        citation_placeholders=sum(
            p.get("evidence_level") == "citation_placeholder" for p in retained
        ),
    )
    for tier in ("core", "adjacent", "exclude"):
        counts.setdefault(tier, 0)
    files = {
        key: key + ".json"
        for key in ("graph", "analytics", "matrix", "benchmarks", "quality", "diff", "counts")
    }
    files.update(
        index="papers-index.json",
        ownerSample="owner-label-sample.csv",
        spotChecks="spot-checks.json",
        details=sorted(buckets),
        exports={
            "bibtex": "exports/references.bib",
            "ris": "exports/references.ris",
            "csl": "exports/references.csl.json",
            "markdown": "exports/references.md",
            "latex": "exports/references.tex",
            "matrixMarkdown": "exports/matrix.md",
            "matrixLatex": "exports/matrix.tex",
        },
    )
    atlas = dict(config.get("atlas", config))
    atlas.setdefault("id", config.get("atlas_id", "agent-memory"))
    atlas.setdefault("route", "/agent-memory/")
    atlas.setdefault("title", "Agent Memory Literature Atlas")
    if (
        atlas.get("id") == "agent-memory"
        and not atlas.get("themes")
        and (ROOT / "config/themes.yaml").exists()
    ):
        raw_themes = (ROOT / "config/themes.yaml").read_text()
        try:
            theme_config = json.loads(raw_themes)
        except json.JSONDecodeError:
            import yaml

            theme_config = yaml.safe_load(raw_themes)
        atlas["themes"] = (
            theme_config.get("themes", theme_config)
            if isinstance(theme_config, dict)
            else theme_config
        )
    atlas.setdefault(
        "model",
        {
            "primary": "cx/gpt-6-luna[1m]",
            "fallback": "cx/gpt-6.1-sol",
            "label": "Grounded literature assistant",
        },
    )
    snapshot = config.get("snapshot", {})
    if isinstance(snapshot, str):
        snapshot = {"id": snapshot}
    snapshot = dict(snapshot)
    snapshot.setdefault("id", os.environ.get("ATLAS_SNAPSHOT_ID", "2026-11-01-final"))
    snapshot.setdefault("date", config.get("snapshot_cutoff", config.get("cutoff", "2026-11-01")))
    snapshot.setdefault("parents", config.get("parents", []))
    snapshot["previous_snapshot"] = config.get("previous_snapshot", config.get("parent_snapshot"))
    snapshot["acquisition_parent"] = config.get("parent_snapshot")
    parent_hashes = {}
    for parent in snapshot["parents"]:
        parent_id = parent.get("id") if isinstance(parent, dict) else parent
        parent_dir = ROOT / "data" / ("snapshot-" + str(parent_id))
        if parent_dir.exists():
            parent_hashes[str(parent_id)] = {
                str(p.relative_to(parent_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(parent_dir.rglob("*"))
                if p.is_file()
            }
    snapshot["parent_hashes"] = parent_hashes
    parentage = public_parentage(load(private / "parentage.json", {}))
    if parentage:
        snapshot["parentage"] = parentage
    snapshot["archives"] = export_archives(out, snapshot, atlas.get("route", "/agent-memory/"))
    # Never expose configuration secrets/server endpoints in the public manifest.
    if (ROOT / "config/project_abstract.txt").exists() and atlas["id"] == "agent-memory":
        atlas.setdefault(
            "projectAbstract",
            {
                "placeholder": False,
                "text": (ROOT / "config/project_abstract.txt").read_text().strip(),
            },
        )
    atlas.setdefault(
        "projectAbstract",
        {
            "placeholder": True,
            "text": "Scope-preserving revision of context-scoped LLM-agent memory: defaults and exceptions over a partial order of contexts, impact-region and latent-error evaluation with an exact symbolic oracle",
        },
    )
    atlas = {
        k: v
        for k, v in atlas.items()
        if k
        in {
            "id",
            "title",
            "headline",
            "description",
            "route",
            "seedGroups",
            "themes",
            "capabilities",
            "model",
            "projectAbstract",
            "language",
            "reference_route",
            "graphIntro",
            "defaultView",
            "scopeDescription",
        }
    }
    if context_files:
        files["citationContexts"] = context_files
    manifest = {
        "atlas": atlas,
        "snapshot": snapshot,
        "counts": counts,
        "limitations": limitations,
        "files": files,
    }
    quality = {
        "excluded": [metadata(p) for p in papers if p["tier"] == "EXCLUDE"],
        "abstract_missing": [
            p["id"] for p in retained if not p.get("abstract_available", bool(p.get("abstract")))
        ],
        "abstract_withheld": [
            r["id"] for r in index if r["abstract_available"] and not r["abstract_display_allowed"]
        ],
        "abstract_withheld_privacy": [
            p["id"] for p in retained if contains_ipv4(p.get("abstract"))
        ],
        "one_source": [
            p["id"] for p in retained if sum(bool(v) for v in p.get("source_ids", {}).values()) <= 1
        ],
        "retracted": [p["id"] for p in retained if p.get("retracted") or p.get("is_retracted")],
        "owner_label_status": "pending: precision cannot be estimated before owner labels",
        "coverage": {
            "retained": len(retained),
            "abstract_available": sum(r["abstract_available"] for r in index),
            "abstract_displayable": sum(
                r["abstract_available"] and r["abstract_display_allowed"] for r in index
            ),
            "abstract_privacy_withheld": sum(contains_ipv4(p.get("abstract")) for p in retained),
            "abstract_permission_withheld": sum(
                p.get("abstract_available", bool(p.get("abstract")))
                and not p.get("abstract_display_allowed")
                and not contains_ipv4(p.get("abstract"))
                for p in retained
            ),
        },
        "sampling": {
            "owner_seed": config.get("owner_sample_seed", 20261103),
            "spot_check_seed": config.get("spot_check_seed", 20261104),
            "requested_owner_counts": {"CORE": 40, "ADJACENT": 30, "EXCLUDE": 30},
            "requested_spot_counts": {"CORE": 30, "ADJACENT": 30},
        },
        "license_limits": "Withheld evidence is not absence of evidence.",
    }
    diagnostics = {}
    for name in (
        "acquisition_failures",
        "unresolved_pairs",
        "gap_retries",
        "duplicate_audit",
        "embedding_tier_agreement",
        "TIER-REPORT",
        "deferred_resolution",
        "DEDUPLICATION",
        "query_diagnosis",
        "query_diagnostics",
        "s2_query_diagnosis",
        "s2_fix_report",
        "citation_enrichment",
        "CITATION-CONTEXT-EDGES",
        "ABSTRACT-PERMISSIONS",
    ):
        value = load(private / (name + ".json"))
        if value is not None:
            diagnostics[name] = diagnostic_public(value)
            quality[name] = diagnostics[name]
    if parentage:
        quality["parentage"] = parentage
    public_method = analytics.setdefault("method", analytics.get("methods", {}))
    if not isinstance(public_method, dict):
        public_method = {"description": public_method}
        analytics["method"] = public_method
    public_method["screening"] = diagnostics.get("TIER-REPORT", {"status": "not available"})
    public_method["embedding_tier_agreement"] = diagnostics.get(
        "embedding_tier_agreement", {"status": "not available"}
    )
    public_method["acquisition_diagnostics"] = {
        k: v
        for k, v in diagnostics.items()
        if k
        in {
            "gap_retries",
            "DEDUPLICATION",
            "query_diagnosis",
            "query_diagnostics",
            "s2_query_diagnosis",
            "s2_fix_report",
            "citation_enrichment",
        }
    }
    public_method["counts_scope"] = (
        "Snapshot counts cover all retained CORE+ADJACENT; default view is CORE+seeds. Map counters describe current filters."
    )
    public_method["full_text_scope"] = (
        "Full-text evidence counts use recorded evidence_level only; open-access links do not imply text was read or stored."
    )
    public_method["privacy_withholding"] = {
        "rule": "Whole public abstract or evidence text fields containing an IPv4 address are withheld; private source text is unchanged. This is separate from permission withholding.",
        "abstracts_withheld": quality["coverage"]["abstract_privacy_withheld"],
    }
    prev = load(Path(previous) / "papers-index.json", None) if previous else None
    if prev is None and previous:
        prev = [metadata(p) for p in load(Path(previous) / "papers.json", [])]
    diff = diff_snapshot(index, prev or [])
    diff["parentage"] = snapshot["parents"]
    diff["baseline_available"] = bool(prev)
    matrix = permission_filter(load(private / "matrix.private.json", {}))
    benchmarks = permission_filter(load(private / "benchmarks.private.json", {}))
    for name, value in [
        ("manifest", manifest),
        ("counts", counts),
        ("papers-index", index),
        ("graph", graph),
        ("analytics", analytics),
        ("matrix", matrix),
        ("benchmarks", benchmarks),
        ("quality", quality),
        ("diff", diff),
    ]:
        write(out / (name + ".json"), value, compact=name in {"papers-index", "graph"})
    for name, value in buckets.items():
        write(out / name, value)
    for pid, filename in context_files.items():
        write(out / filename, permission_filter(context_papers[pid]), compact=True)
    if context_data:
        write(
            out / "citation-contexts-coverage.json",
            permission_filter(
                {
                    "coverage": context_data.get("coverage", {}),
                    "method": context_data.get("method", {}),
                }
            ),
        )
        files["citationContextsCoverage"] = "citation-contexts-coverage.json"
        write(out / "manifest.json", manifest)
    owner_seed = config.get("owner_sample_seed", 20261103)
    spot_seed = config.get("spot_check_seed", 20261104)
    rng = random.Random(owner_seed)
    spot_rng = random.Random(spot_seed)
    samples = []
    spots = {}
    for tier, n in [("CORE", 40), ("ADJACENT", 30), ("EXCLUDE", 30)]:
        pool = sorted([p for p in papers if p["tier"] == tier], key=lambda p: p["id"])
        selection = rng.sample(pool, min(n, len(pool)))
        samples.extend(
            {
                "id": p["id"],
                "title": p["title"],
                "tier": tier,
                "link": metadata(p)["link"] or "",
                "owner_label": "",
            }
            for p in selection
        )
        if tier != "EXCLUDE":
            spots[tier] = [
                {"id": p["id"], "title": p["title"], "link": metadata(p)["link"]}
                for p in spot_rng.sample(pool, min(30, len(pool)))
            ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=["id", "title", "tier", "link", "owner_label"], lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(samples)
    (out / "owner-label-sample.csv").write_text(stream.getvalue(), encoding="utf-8", newline="\n")
    write(
        out / "spot-checks.json",
        {
            "seed": spot_seed,
            "owner_sample_seed": owner_seed,
            "requested_per_tier": 30,
            "samples": spots,
            "available_counts": counts,
        },
    )
    exports = out / "exports"
    exports.mkdir(exist_ok=True)
    (exports / "references.bib").write_text("\n".join(citations))
    (exports / "references.ris").write_text("\n".join(ris))
    write(exports / "references.csl.json", csl)
    (exports / "references.md").write_text(
        "\n".join(
            f"- [{p['title']}]({p['link'] or ''}) ({p.get('citation_year') or p['year'] or 'n.d.'}); {p['tier']}"
            for p in index
        )
        + "\n"
    )
    (exports / "references.tex").write_text(
        "\\begin{itemize}\n"
        + "\n".join(
            "\\item "
            + re.sub(r"([&%$#_{}])", r"\\\1", p["title"])
            + " ("
            + str(p.get("citation_year") or p["year"] or "n.d.")
            + ")."
            for p in index
        )
        + "\n\\end{itemize}\n"
    )
    columns = matrix.get("columns", [])
    rows = matrix.get("rows", {})
    if isinstance(rows, list):
        rows = {r.get("id", r.get("paper_id")): r for r in rows}
    labels = [c.get("label", c.get("id", "")) for c in columns]
    keys = [c.get("id", "") for c in columns]
    md = ["| Paper | " + " | ".join(labels) + " |", "|---|" + "---|" * len(keys)]
    latex = [
        "\\begin{tabular}{l" + "l" * len(keys) + "}",
        "\\toprule",
        "Paper" + (" & " + " & ".join(labels) if labels else "") + r" \\",
        "\\midrule",
    ]
    for pid, row in sorted(rows.items()):
        vals = [str((row.get("cells", row).get(k) or {}).get("value", "not stated")) for k in keys]
        title = next((p["title"] for p in index if p["id"] == pid), pid)
        md.append("| " + title.replace("|", "\\|") + " | " + " | ".join(vals) + " |")
        latex.append(re.sub(r"([&%$#_{}])", r"\\\1", title) + " & " + " & ".join(vals) + r" \\")
    (exports / "matrix.md").write_text("\n".join(md) + "\n")
    (exports / "matrix.tex").write_text(
        "\n".join(latex + ["\\bottomrule", "\\end{tabular}"]) + "\n"
    )
    hashes = {
        str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "FILES.sha256.json"
    }
    write(out / "FILES.sha256.json", hashes)
    assert_public_no_ipv4(out)
    if site_data:
        destination = Path(site_data).resolve()
        if destination == out or out in destination.parents:
            raise ValueError("Static copy destination overlaps snapshot")
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "citation-contexts-coverage.json").unlink(missing_ok=True)
        for generated in ("details", "exports", "archives", "citation-contexts"):
            if (destination / generated).exists():
                shutil.rmtree(destination / generated)
        for item in out.iterdir():
            target = destination / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private")
    parser.add_argument("--config", default=str(ROOT / "config/final.yaml"))
    parser.add_argument("--out")
    parser.add_argument("--previous")
    parser.add_argument("--site-data", default=str(ROOT / "site/public/data"))
    parser.add_argument(
        "--verify-determinism",
        action="store_true",
        help="Compare two independent frozen-input exports before copying final assets",
    )
    args = parser.parse_args()
    raw = Path(args.config).read_text()
    if args.config.endswith(".json"):
        config = json.loads(raw)
    else:
        import yaml

        config = yaml.safe_load(raw)
    selected = os.environ.get("ATLAS_SNAPSHOT_ID") or (
        config.get("snapshot", {}).get("id")
        if isinstance(config.get("snapshot"), dict)
        else config.get("snapshot")
    )
    if selected:
        if isinstance(config.get("snapshot"), dict):
            config["snapshot"]["id"] = selected
        else:
            config["snapshot"] = selected
    cutoff = os.environ.get("ATLAS_SNAPSHOT_CUTOFF")
    if cutoff:
        from datetime import date

        date.fromisoformat(cutoff)
        config["cutoff"] = cutoff
        config["snapshot_cutoff"] = cutoff
    previous_id = (
        os.environ.get("ATLAS_PREVIOUS_SNAPSHOT")
        or config.get("previous_snapshot")
        or config.get("parent_snapshot")
    )
    if previous_id:
        config["parents"] = list(dict.fromkeys([*config.get("parents", []), previous_id]))
        config["previous_snapshot"] = previous_id
    args.out = args.out or str(ROOT / "data" / ("snapshot-" + selected))
    args.previous = args.previous or (
        str(ROOT / "data" / ("snapshot-" + previous_id)) if previous_id else None
    )
    folder = args.private or str(Path(os.environ["ATLAS_PRIVATE_DIR"]) / selected)
    verification = (
        verify_determinism(folder, config, args.previous) if args.verify_determinism else None
    )
    manifest = build(folder, args.out, config, args.previous, args.site_data)
    print(json.dumps({"counts": manifest["counts"], "verification": verification}, sort_keys=True))


if __name__ == "__main__":
    main()
