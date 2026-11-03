from pathlib import Path

import numpy as np
import pytest

from scripts.analytics_final import query_embedding


def test_partial_query_cache_fails_closed_in_cache_only(tmp_path: Path):
    config = {"embeddings": {"model": "test"}}

    def embed(_):
        return np.array([1.0, 0.0]), {"model": "test"}

    query_embedding(tmp_path, config, "query", embed)
    next((tmp_path / "project-query-cache").glob("*.npy")).write_bytes(b"broken")
    with pytest.raises(RuntimeError, match="cache"):
        query_embedding(tmp_path, config, "query", embed, True)


def test_missing_manifest_and_changed_parameters_fail_closed(tmp_path: Path):
    config = {"embeddings": {"model": "test", "dimensions": 2}}

    def embed(_):
        return np.array([1.0, 0.0]), {"model": "test"}

    query_embedding(tmp_path, config, "query", embed)
    next((tmp_path / "project-query-cache").glob("*.json")).unlink()
    with pytest.raises(RuntimeError, match="cache"):
        query_embedding(tmp_path, config, "query", embed, True)
    with pytest.raises(RuntimeError, match="cache"):
        query_embedding(
            tmp_path, {"embeddings": {"model": "other", "dimensions": 2}}, "query", embed, True
        )
