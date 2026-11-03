"""Add source-resolved citation-context links without changing corpus membership."""


def merge(edges,papers,contexts):
    retained={p['id'] for p in papers if p.get('tier') in ('CORE','ADJACENT')}
    result={tuple(e) for e in edges}
    pairs={tuple(e) for e in contexts.get('resolved_citation_edges',[])}
    assert all(len(e)==2 and e[0] in retained and e[1] in retained and e[0]!=e[1] for e in pairs),'Invalid context citation identity'
    result.update(pairs)
    return sorted(result),{'context_pairs_in_corpus':len(pairs),'total_resolved_citation_edges':len(result)}


if __name__=='__main__':
    from final_common import folder,read_json,write_json
    f=folder();path=f/'citation_contexts.private.json'
    if not path.exists():raise SystemExit('Citation context acquisition is not complete')
    edges,receipt=merge(read_json(f/'resolved_edges.json'),read_json(f/'papers.private.json'),read_json(path))
    write_json(f/'resolved_edges.json',edges);write_json(f/'CITATION-CONTEXT-EDGES.json',receipt)
    import json
    print(json.dumps(receipt,sort_keys=True))
