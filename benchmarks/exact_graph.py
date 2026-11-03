"""Run each exact graph size in a fresh process to measure peak RSS."""

import json
import os
import platform
import resource
import subprocess
import sys
import time

import numpy as np
from scripts.analytics_final import semantic_edges


def measure(n):
    rng = np.random.default_rng(20261103)
    vectors = rng.normal(size=(n, 32)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    ids = [f"SYN-{i:06d}" for i in range(n)]
    start = time.perf_counter()
    edges, _ = semantic_edges(ids, vectors, 10)
    elapsed = time.perf_counter() - start
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "n": n,
        "dimensions": 32,
        "edges": len(edges),
        "seconds": round(elapsed, 4),
        "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(measure(int(sys.argv[1]))))
    else:
        env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        rows = [
            json.loads(
                subprocess.check_output([sys.executable, __file__, str(n)], env=env, text=True)
            )
            for n in (128, 512, 1024)
        ]
        print(
            json.dumps(
                {
                    "generator": "numpy default_rng seed 20261103, normal, L2 normalized",
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "rows": rows,
                },
                indent=2,
            )
        )
