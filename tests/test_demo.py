import copy
import json

import pytest

from atlas_demo.core import load_corpus, run_demo


def test_demo_reuses_and_invalidates_only_changed_record(tmp_path):
    corpus = load_corpus(None)
    first = run_demo(corpus, tmp_path)
    second = run_demo(corpus, tmp_path)
    assert first["cache"] == {"hits": 0, "misses": 3}
    assert second["cache"] == {"hits": 3, "misses": 0}
    assert first["results"][0]["page"] == 2
    assert first["edges"][0]["type"] == "citation"
    changed = copy.deepcopy(corpus)
    changed["papers"][0]["pages"][0]["text"] += " Changed."
    assert run_demo(changed, tmp_path)["cache"] == {"hits": 2, "misses": 1}


def test_rejects_invalid_vector_and_duplicate_id(tmp_path):
    corpus = load_corpus(None)
    corpus["papers"][0]["vector"] = [0, 0, 0]
    with pytest.raises(ValueError, match="vector"):
        run_demo(corpus, tmp_path)
    corpus = load_corpus(None)
    corpus["papers"][1]["id"] = corpus["papers"][0]["id"]
    with pytest.raises(ValueError, match="duplicate"):
        run_demo(corpus, tmp_path)


def test_corrupt_cache_is_rebuilt(tmp_path):
    corpus = load_corpus(None)
    run_demo(corpus, tmp_path)
    next((tmp_path / "cache").glob("*.json")).write_text("{")
    assert run_demo(corpus, tmp_path)["cache"] == {"hits": 2, "misses": 1}


def test_demo_writes_standalone_interactive_review_page(tmp_path):
    run_demo(load_corpus(None), tmp_path)
    html = (tmp_path / "index.html").read_text()
    assert "SYNTHETIC DATA" in html
    assert 'id="search"' in html
    assert 'id="graph"' in html
    assert 'id="evidence"' in html
    assert 'id="export"' in html
    assert "SYN-001" in html


def test_demo_reports_existing_fts_retrieval_with_page(tmp_path):
    report = run_demo(load_corpus(None), tmp_path)
    assert report["fts_results"][0]["paper_id"] == "SYN-001"
    assert report["fts_results"][0]["page"] == 2
    assert "Episodic retrieval" in report["fts_results"][0]["text"]


def test_react_snapshot_uses_existing_exporter_and_synthetic_page_evidence(tmp_path):
    from atlas_demo.react import export_react_snapshot

    corpus = load_corpus(None)
    output = tmp_path / "react-data"
    export_react_snapshot(corpus, output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert "SYNTHETIC" in manifest["atlas"]["title"]
    index = json.loads((output / manifest["files"]["index"]).read_text())
    rows = index["papers"] if isinstance(index, dict) else index
    assert {row["id"] for row in rows} == {"SYN-001", "SYN-002", "SYN-003"}
    graph = json.loads((output / manifest["files"]["analytics"]).read_text())
    assert any(e["source"] == "SYN-001" and e["target"] == "SYN-002" for e in graph["edges"])
    matrix = json.loads((output / manifest["files"]["matrix"]).read_text())
    assert matrix["rows"]["SYN-001"]["cells"]["synthetic"]["location"] == "PDF p. 2"
    assert "Episodic retrieval" in matrix["rows"]["SYN-001"]["cells"]["synthetic"]["quote"]
    assert (output / "exports").is_dir()


def test_react_snapshot_refuses_nonempty_destination(tmp_path):
    from atlas_demo.react import export_react_snapshot

    (tmp_path / "keep.txt").write_text("original")
    with pytest.raises(ValueError, match="empty"):
        export_react_snapshot(load_corpus(None), tmp_path)
    assert (tmp_path / "keep.txt").read_text() == "original"


def test_committed_react_fixture_matches_exporter(tmp_path):
    from pathlib import Path
    from atlas_demo.react import export_react_snapshot

    output = tmp_path / "snapshot"
    export_react_snapshot(load_corpus(None), output)
    fixture = Path(__file__).resolve().parents[1] / "site" / "fixtures" / "synthetic-react"
    generated = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    committed = {p.relative_to(fixture): p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
    assert b"\r" not in generated[Path("owner-label-sample.csv")]
    assert generated == committed
