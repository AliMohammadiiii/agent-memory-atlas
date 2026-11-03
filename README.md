# Agent Memory Atlas

Agent Memory Atlas is a research software pipeline for exploring agent-memory literature through embeddings, citation relationships and page-linked retrieval.

[Live atlas](https://alimohamadi.me/agent-memory/) · [Offline synthetic demonstration](docs/REVIEWER-DEMO.md) · [Source provenance](docs/SOURCE-PROVENANCE.md)

This public repository is a curated source snapshot derived from a preserved private archive. It includes a fictional corpus for the offline demonstration; the live corpus, private full texts, credentials and provider-generated datasets are not included. The Git history of the archive and its old tags are not part of this repository.

## Run the demonstration

With Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
uv run --python 3.12 --no-project --with-requirements requirements-test.txt \
  python -m atlas_demo --output /tmp/atlas-demo
```

Run the command again to see cached work reused, then open `/tmp/atlas-demo/index.html`. The [demonstration guide](docs/REVIEWER-DEMO.md) also explains how to build a synthetic snapshot for the existing React frontend. All papers, vectors, pages and citations in the example are fictional.

## Code and contributions

Ali Mohammadi built the Atlas pipeline and interface, including vector and graph analytics, evidence retrieval and presentation. NumPy, SciPy, scikit-learn, SQLite, React and other dependencies provide numerical, retrieval and interface infrastructure. The [source terms](LICENSE) reserve rights in the project source; third-party components retain their own licenses.

- [Vector and graph analytics](scripts/analytics_final.py) and [embedding generation](scripts/vectors_final.py)
- [Page index construction](scripts/build_fulltext_rag.py) and [retrieval](server/fulltext.py)
- [Gateway](server/gateway.py) and [interactive graph](site/src/GraphView.jsx)

Cosine ranking, citation graphs and SQLite FTS serve different purposes. The recorded benchmark covers only small synthetic inputs; it does not establish large-scale performance.

## Offline checks

With Python 3.12 and Node 24:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:scripts:server \
  uv run --python 3.12 --no-project --with-requirements requirements-test.txt \
  python -m pytest -p no:cacheprovider scripts server tests -q
cd site
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
```

The source snapshot passed 179 Python and 36 Node tests and a frontend build in local checks. These checks use no provider keys. A real browser walkthrough remains pending; the synthetic demo does not validate provider-backed operation or reproduce the live dataset.

The original production dependency files remain separate from the offline test requirements. The [server notes](server/README.md) describe the runtime boundary.
