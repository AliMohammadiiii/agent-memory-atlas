import numpy as np
import pytest

from scripts.analytics_final import project_ranking, semantic_edges


def test_semantic_cutoff_ties_choose_smallest_id():
    ids = ["a", "b", "c", "d"]
    vectors = np.array([[1.0, 0.0], [0.8, 0.6], [0.8, 0.6], [0.8, 0.6]])
    edges, _ = semantic_edges(ids, vectors, 1)
    assert any(e["source"] == "a" and e["target"] == "b" for e in edges)
    assert not any(e["source"] == "a" and e["target"] in ("c", "d") for e in edges)


@pytest.mark.parametrize(
    "ids,vectors",
    [
        (["a", "a"], np.ones((2, 2))),
        (["a", "b"], np.array([[1.0, 0.0], [0.0, 0.0]])),
        (["a", "b"], np.array([[1.0, 0.0], [float("nan"), 1.0]])),
        (["a"], np.ones((2, 2))),
    ],
)
def test_graph_rejects_invalid_identity_or_vectors(ids, vectors):
    with pytest.raises(ValueError):
        semantic_edges(ids, vectors, 1)
    with pytest.raises(ValueError):
        project_ranking(ids, vectors, [1.0, 0.0])
