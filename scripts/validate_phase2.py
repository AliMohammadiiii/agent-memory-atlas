#!/usr/bin/env python3
"""Check the actual snapshot's identities, evidence provenance, counts and edges."""
import hashlib
import json
from collections import Counter, defaultdict

from resolve_seeds import ROOT, raw_root
from server_runtime import phase2_config, private_root


def main():
    config = phase2_config()
    folder = private_root()/config['snapshot']
    output = ROOT/'data'/('snapshot-'+config['snapshot'])
    read = lambda name: json.loads((folder/name).read_text())
    public = lambda name: json.loads((output/name).read_text())
    papers = read('papers.private.json'); records = public('papers.json')
    counts = public('counts.json'); decisions = read('screening_decisions.json')
    ids = {p['id'] for p in papers}; included = {p['id'] for p in records}
    assert len(ids) == len(papers) == counts['after_dedup']
    assert len(included) == len(records) == counts['included'] == counts['corpus_records']
    assert {r['id'] for r in decisions} == ids and len(decisions) == len(ids)
    assert Counter(r['label'] for r in decisions) == Counter({
        'include': counts['included'], 'exclude': counts['excluded'], 'uncertain': counts['deferred']})
    edges = public('edges.json')
    assert len(edges) == counts['resolved_links']
    assert len({tuple(e) for e in edges}) == len(edges)
    assert all(a in included and b in included and a != b for a,b in edges)
    assert dict(Counter(r['evidence_level'] for r in records)) == counts['evidence_levels']
    assert all('abstract' not in r and r['abstract_display_allowed'] is False for r in records)
    source_checks = defaultdict(set)
    for paper in papers:
        assert paper['publication_versions'], 'Record without stored API provenance'
        for version in paper['publication_versions']:
            provenance = version['provenance']
            assert provenance['status'] == 200 and provenance['retrieved_at']
            digest = provenance['response_sha256']
            source_checks[digest].add(str(version['source_id']))
        if paper['arxiv_ids'] and paper['first_public_date_basis'] == 'arxiv_v1':
            assert int(paper['first_public_date'][:4]) == paper['first_public_year']
    for digest, source_ids in source_checks.items():
        body = (raw_root()/'responses'/(digest+'.body')).read_bytes()
        assert hashlib.sha256(body).hexdigest() == digest
        assert all(identifier.encode() in body for identifier in source_ids), 'Source id absent from cited API response'
    by_id = {p['id']: p for p in papers}
    from phase2_screen import validate_manual_labels
    sample = read('screening_sample.private.json')
    validate_manual_labels(read('manual_labels.json'), sample)
    for judgment in read('sample_model_judgments.json'):
        paper = by_id[judgment['id']]
        text = (paper['title']+'\n\n'+(paper.get('abstract') or ''))[:config['relevance']['abstract_input_max_chars']]
        quote = judgment.get('evidence_quote') or ''
        assert quote in text and len(quote.split()) <= 25
        assert hashlib.sha256(text.encode()).hexdigest() == judgment['input_sha256']
    for name,digest in public('FILES.sha256.json').items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest() == digest
    print(json.dumps({'validated_candidate_ids': len(ids), 'api_response_bodies_verified': len(source_checks),
        'included_edge_endpoints_verified': len(edges), 'sample_evidence_verified': len(sample)}))


if __name__ == '__main__':
    main()
