# Offline synthetic reviewer path

This demo uses invented papers and page passages, fixed vectors, and invented citations. It does not use the private corpus, a model, provider credentials, or the network after installation. It exercises the existing `project_ranking` and `relationship_edges` analytics, and builds the existing SQLite FTS index over fictional page records before retrieving matching passages. It produces a standalone page evidence viewer and can also export a synthetic snapshot for the existing React UI. SQLite must support FTS5.

With Python 3.12 and uv, from this repository:

```sh
uv run --python 3.12 --no-project --with-requirements requirements-test.txt \
  python -m atlas_demo --output /tmp/atlas-demo
uv run --python 3.12 --no-project --with-requirements requirements-test.txt \
  python -m atlas_demo --output /tmp/atlas-demo
open /tmp/atlas-demo/index.html
```

Alternatively `python -m pip install .` installs `atlas-demo`; `atlas-demo --output /tmp/atlas-demo` works outside the checkout. Node 24 is needed only for the existing frontend. The production analytics and methods requirements remain recorded in their original files; the demo pins only NumPy and SciPy. Analytics/test dependencies remain separate. A custom JSON file is accepted via `--config PATH`; missing or invalid config fails with an actionable message.

The first run reports three misses; the second reports three hits. Each result has a fictional page, source passage, paper ID and score. Citations are directed from source to target. The JSON report and browser export use the same data. Scores are rounded to eight decimal places; compare floating-point results to 1e-7 across platforms. The snapshot and examples are reproducible, but cache counts naturally differ between first and later runs. Modify one paper in a copied corpus and pass it through `--config`: its key changes and the other two are reused.

## Architecture and contracts

`atlas_demo/core.py` validates schema version, snapshot and provenance, unique stable IDs, citations, positive page numbers, vector dimensions, finite values and nonzero norms. It L2-normalizes fixed vectors before calling the existing ranking and graph functions. Records are ranked by descending cosine and then ID. Citation edges are directed and deduplicated; self and out-of-corpus edges are excluded by the existing graph function (the demo rejects outside IDs at its boundary). Bibliographic coupling counts shared outgoing references; cocitation counts shared incoming citers. These edges are undirected and use deterministic top-k incident union, weights then canonical IDs. Isolates remain in the paper list.

The synthetic cache key contains the whole paper including its text, vector and references, snapshot, provenance, model/task label, dimensions and preprocessing version. A single JSON record holds identity and normalized vector, written using a same-directory temporary file and atomic replacement. A hit must match the expected identity and vector; corrupt or interrupted records are rebuilt without a provider. No raw private data enters this fixture.

The production query embedding cache uses a hash manifest committed after the vector. It verifies the key, vector hash, shape, finite values and dimension when configured. An interrupted pair is rejected; cache-only mode fails closed. Older pairs lack a manifest and cannot be authenticated. `atlas-migrate-query-cache --source OLD/project-query-cache --output NEW --config CONFIG.json --text-file QUERY.txt` checks their derived filename, model provenance, vector dimensions, finite values and unit norm, then copies the pair into a new cache with a hash manifest; the originals remain untouched. The text file must contain the exact original query, including whitespace, and the JSON config must contain its original `embeddings` settings. A legacy pair has no original vector digest: migration cannot independently prove its historical origin, so use only trusted local pairs. Online regeneration is an alternative. This changes cache compatibility and should be planned before deploying; no existing snapshots were changed here. See `tests/test_cache_integrity.py` and existing `scripts/test_analytics_final.py`.

## Exact graph measurement and decision

Run `PYTHONPATH=. python benchmarks/exact_graph.py` in the test environment. The stored `benchmarks/exact-graph-result.json` captures a seed, platform, Python/NumPy versions, 32 dimensions, top-k 10, edge counts, wall time and per-process peak RSS for 128, 512 and 1,024 records. The wall time covers graph construction only; peak RSS includes the Python process and imported libraries; it is a small local measurement, not a production throughput claim. The exact algorithm is retained for this measured range. No ANN index has been justified by this small workload; recall, update cost and alternative-index comparisons are therefore not claimed. Larger workloads require profiling against their actual latency and memory budgets first. The semantic neighbor routine uses brute-force cosine and an undirected positive-score top-k union; it sorts all candidates by similarity and then ID, including ties at the cutoff.

## Validation and remaining boundaries

CI exercises the reviewer command twice, checks its artifacts, runs scoped Ruff formatting/lint and mypy on the demo, builds and runs a wheel outside the checkout, and runs the existing Python and Node tests/build. Provider-backed operations are not part of the offline workflow. The standalone HTML uses native controls and an empty-filter state; a real browser walkthrough including narrow view, keyboard, export, console/network and screenshots is still needed. The existing React frontend can load the exported synthetic schema as described below. Gateway diagnostics log bounded stage, category, generated request ID and a restricted snapshot identifier, without exception messages, prompts, source text or credentials. Generation attempts the primary and fallback routes at most once each, each with a 100-second HTTP timeout; cancellation is not caught. Deterministic tests exercise timeout failover and cancellation, with no live provider calls. Other full-service failure and network behavior still needs deployment-specific validation.

## Existing React frontend with synthetic data

The optional `--react-data` argument writes an exporter-compatible snapshot to a **new or empty** directory. It uses `scripts/build_site.py` with permission-explicit fictional text and citations. It refuses to overwrite a nonempty directory. To keep generated files away from the checkout and real data, stage a separate site:

```sh
mkdir -p /tmp/atlas-react-site
tar -C site --exclude=node_modules --exclude=dist -cf - . | tar -C /tmp/atlas-react-site -xf -
uv run --python 3.12 --no-project --with-requirements requirements-test.txt \
  python -m atlas_demo --output /tmp/atlas-react-report \
  --react-data /tmp/atlas-react-site/public/data
cd /tmp/atlas-react-site
npm ci --ignore-scripts --no-audit --no-fund
npm run dev
```

Open the local Vite address printed by the server (normally `http://localhost:5173/agent-memory/`). The interface, graph, matrix and reference exports use the same fictional IDs and pages. Search `episodic`; select SYN-001, inspect the synthetic page 2 matrix evidence and citation to SYN-002. The committed `site/fixtures/synthetic-react` is regenerated and compared byte-for-byte in the Python tests; a Node contract test exercises graph selection, evidence and exported reference IDs. The service-backed Ask feature is not provided by this offline snapshot. A real browser walkthrough and visual checks remain outstanding because local browser use was disabled in this environment.
