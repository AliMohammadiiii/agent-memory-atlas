#!/usr/bin/env python3
"""Verify that every accepted metadata identity is backed by an archived response."""
import argparse
import hashlib
import json
from pathlib import Path

from resolve_seeds import candidate_summary, raw_root

ROOT = Path(__file__).resolve().parents[1]


def response_records(data):
    if isinstance(data, list):
        for row in data:
            yield from response_records(row)
    elif isinstance(data, dict):
        yield data
        for field in ('data', 'results'):
            if isinstance(data.get(field), list):
                yield from response_records(data[field])


def validate(snapshot):
    folder = ROOT / 'data' / ('snapshot-' + snapshot)
    payload = json.loads((folder / 'seeds.json').read_text())
    counts = json.loads((folder / 'counts.json').read_text())
    assert hashlib.sha256((ROOT / 'config/seeds.tsv').read_bytes()).hexdigest() == payload['input_sha256']
    assert len(payload['seeds']) == counts['input_seeds'] == sum(counts['by_status'].values())
    assert len({r['seed_id'] for r in payload['seeds']}) == len(payload['seeds'])
    identities = 0
    bodies = {}
    for seed in payload['seeds']:
        for provider, summary in seed['source_records'].items():
            found = False
            for provenance in seed['provenance']:
                if provenance['provider'] != provider or provenance['status'] != 200:
                    continue
                digest = provenance['response_sha256']
                if digest not in bodies:
                    body = (raw_root() / 'responses' / (digest + '.body')).read_bytes()
                    assert hashlib.sha256(body).hexdigest() == digest
                    bodies[digest] = json.loads(body)
                assert provenance['retrieved_at'] and provenance['request_hash']
                for record in response_records(bodies[digest]):
                    identifier = record.get('paperId') if provider == 's2' else record.get('id')
                    if identifier == summary['id']:
                        assert candidate_summary(record, provider) == summary, seed['seed_id']
                        found = True
            assert found, (seed['seed_id'], provider)
            identities += 1
        sources = seed['source_records']
        canonical = sources.get('openalex') or sources.get('s2')
        if canonical:
            for field in ('title', 'year', 'venue', 'doi'):
                assert seed[field] == canonical[field], (seed['seed_id'], field)
            assert seed['arxiv_id'] in {r['arxiv_id'] for r in sources.values()}, seed['seed_id']
        else:
            assert all(seed[k] is None for k in ('title', 'year', 'venue', 'doi', 'arxiv_id'))
    print(json.dumps({'accepted_identities_verified': identities, 'unique_response_bodies_verified': len(bodies),
                      'seeds_checked': len(payload['seeds']), 'accepted_metadata_matches_archived_responses': True}, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    validate(parser.parse_args().snapshot)
