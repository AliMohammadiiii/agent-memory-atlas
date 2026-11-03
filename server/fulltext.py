"""Read-only private passage retrieval. Questions are never persisted."""

import json, re, sqlite3, zlib
from pathlib import Path

STOP = set(
    "a an the is are was were be been being of to in on at by for with and or as it its this that these those what which how why when where who does do did can could would should have has had from about into through between according describe explain compare please paper study work memory agent agents llm".split()
)


def terms(query):
    return list(
        dict.fromkeys(
            t.lower() for t in re.findall(r"[A-Za-z0-9_]{2,}", query) if t.lower() not in STOP
        )
    )[:30]


class FulltextIndex:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.manifest = json.loads((self.folder / "manifest.json").read_text())
        self.config = self.manifest["parameters"]
        self.paper_ids = set(self.manifest["paper_chunks"])
        with self.connect() as db:
            if db.execute("SELECT count(*) FROM papers").fetchone()[0] != self.manifest["papers"]:
                raise ValueError("Full-text paper count mismatch")
            if db.execute("SELECT count(*) FROM chunks").fetchone()[0] != self.manifest["passages"]:
                raise ValueError("Full-text passage count mismatch")

    def connect(self):
        return sqlite3.connect((self.folder / "index.sqlite").as_uri() + "?mode=ro", uri=True)

    def retrieve(self, query, selected, semantic_papers=(), rerank=None):
        allowed = set(selected) & self.paper_ids
        if not allowed:
            return [], {"mode": "fulltext_hybrid", "passages": 0, "reranker": "not_called"}
        tokens = terms(query)
        if not tokens:
            tokens = list(dict.fromkeys(re.findall(r"[A-Za-z0-9_]{2,}", query.lower())))[:20]
        if not tokens:
            return [], {"mode": "fulltext_hybrid", "passages": 0, "reranker": "not_called"}
        expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
        cfg = self.config
        scores = {}
        ranks = {pid: i + 1 for i, pid in enumerate(semantic_papers) if pid in allowed}
        k = cfg["rrf_constant"]
        with self.connect() as db:
            db.execute("CREATE TEMP TABLE allowed(paper_id TEXT PRIMARY KEY)")
            db.executemany("INSERT INTO allowed VALUES(?)", [(p,) for p in sorted(allowed)])
            sql = "SELECT c.chunk_id,c.paper_id,bm25(passages,2.0,1.0) AS rank FROM passages JOIN chunks c ON c.chunk_id=passages.rowid JOIN allowed a ON a.paper_id=c.paper_id WHERE passages MATCH ? ORDER BY rank,c.chunk_id LIMIT ?"
            for rank, (cid, pid, _) in enumerate(
                db.execute(sql, (expression, cfg["global_lexical_candidates"])), 1
            ):
                scores[cid] = 1 / (k + rank) + (0.5 / (k + ranks[pid]) if pid in ranks else 0)
            # Semantic paper recall is independent of global lexical rank; never widens the user's scope.
            for pid, rank in ranks.items():
                rows = db.execute(
                    "SELECT c.chunk_id FROM passages JOIN chunks c ON c.chunk_id=passages.rowid WHERE passages MATCH ? AND c.paper_id=? ORDER BY bm25(passages,2.0,1.0),c.chunk_id LIMIT ?",
                    (expression, pid, cfg["semantic_paper_passages"]),
                ).fetchall()
                if not rows:
                    rows = db.execute(
                        "SELECT chunk_id FROM chunks WHERE paper_id=? ORDER BY page,chunk_id LIMIT 1",
                        (pid,),
                    ).fetchall()
                for local, (cid,) in enumerate(rows, 1):
                    scores[cid] = scores.get(cid, 0) + 1 / (k + rank) + 0.5 / (k + local)
            ids = sorted(scores, key=lambda cid: (-scores[cid], cid))[: cfg["rerank_candidates"]]
            candidates = []
            for cid in ids:
                row = db.execute(
                    "SELECT c.chunk_id,c.paper_id,c.page,c.start_offset,c.end_offset,c.body,c.span_sha256,p.title,p.pdf_sha256 FROM chunks c JOIN papers p USING(paper_id) WHERE c.chunk_id=?",
                    (cid,),
                ).fetchone()
                candidates.append(
                    {
                        "chunk_id": row[0],
                        "paper_id": row[1],
                        "page": row[2],
                        "start_offset": row[3],
                        "end_offset": row[4],
                        "span": zlib.decompress(row[5]).decode(),
                        "span_sha256": row[6],
                        "title": row[7],
                        "pdf_sha256": row[8],
                        "score": scores[cid],
                        "location": "PDF p. " + str(row[2]),
                        "display_allowed": False,
                        "evidence_level": "fulltext",
                    }
                )
        reranker = "unavailable"
        model = None
        if candidates and rerank:
            try:
                ranked = rerank(
                    query,
                    [c["title"] + "\n" + c["location"] + "\n" + c["span"] for c in candidates],
                )
                indices = [r["index"] for r in ranked["results"]]
                if len(indices) != len(set(indices)) or any(
                    type(i) is not int or not 0 <= i < len(candidates) for i in indices
                ):
                    raise ValueError("Invalid reranker index")
                # Require a complete permutation; partial/malformed provider responses cannot silently drop candidates.
                if set(indices) != set(range(len(candidates))):
                    raise ValueError("Incomplete rerank")
                candidates = [
                    dict(candidates[r["index"]], rerank_score=r["relevance_score"])
                    for r in ranked["results"]
                ]
                reranker = "ready"
                model = ranked.get("model")
            except Exception:
                reranker = "unavailable"
        result = []
        used = {}
        maximum = cfg["max_passages_per_paper"] if len(allowed) > 1 else cfg["evidence_passages"]
        for c in candidates:
            pid = c["paper_id"]
            if used.get(pid, 0) >= maximum:
                continue
            # Avoid spending the evidence budget on overlapping spans on the same page.
            if any(
                e["paper_id"] == pid
                and e["page"] == c["page"]
                and max(e["start_offset"], c["start_offset"])
                < min(e["end_offset"], c["end_offset"])
                for e in result
            ):
                continue
            result.append(c)
            used[pid] = used.get(pid, 0) + 1
            if len(result) >= cfg["evidence_passages"]:
                break
        return result, {
            "mode": "fulltext_hybrid",
            "passages": len(result),
            "candidate_passages": len(candidates),
            "reranker": reranker,
            "reranker_model": model,
            "semantic_representation": "title and abstract embeddings; full-text BM25 passages",
        }
