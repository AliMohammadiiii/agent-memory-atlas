import json

import numpy as np
import pytest

from scripts.analytics_final import digest, query_embedding
from atlas_demo.migrate import migrate


def test_migrate_legacy_pair_without_modifying_source(tmp_path):
    config = {"embeddings": {"model": "example", "dimensions": 2}}
    text = "synthetic query"
    key = digest({"text": text, "parameters": config["embeddings"], "task": "retrieval.query"})
    source = tmp_path / "old"
    source.mkdir()
    np.save(source / (key + ".npy"), np.array([1.0, 0.0], dtype=np.float32))
    (source / (key + ".json")).write_text(json.dumps({"model": "example"}))
    original = (source / (key + ".json")).read_bytes()
    migrate(source, tmp_path / "new", config, text)
    assert (source / (key + ".json")).read_bytes() == original
    vector, meta = query_embedding(tmp_path / "new", config, text, lambda _: None, True)
    assert vector.tolist() == [1.0, 0.0]
    assert meta["model"] == "example"


def test_migration_rejects_bad_provenance(tmp_path):
    config = {"embeddings": {"model": "example", "dimensions": 2}}
    key = digest({"text": "q", "parameters": config["embeddings"], "task": "retrieval.query"})
    np.save(tmp_path / (key + ".npy"), np.array([1.0, 0.0]))
    (tmp_path / (key + ".json")).write_text('{"model":"other"}')
    with pytest.raises(ValueError, match="provenance"):
        migrate(tmp_path, tmp_path / "new", config, "q")
