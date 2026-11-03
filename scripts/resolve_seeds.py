#!/usr/bin/env python3
"""Resolve user-supplied leads, retaining API evidence and unresolved states.

No abstracts or full texts are requested at checkpoint 1. API credentials enter
only through environment variables; neither request URLs nor headers containing
credentials are persisted. A cache-only build never performs network requests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S2_FIELDS = 'paperId,title,year,venue,externalIds,authors,publicationDate,url,isOpenAccess,openAccessPdf'
OA_FIELDS = 'id,doi,title,publication_year,publication_date,primary_location,locations,ids,authorships,open_access,is_retracted'
PROVIDERS = {'openalex': 'https://api.openalex.org', 's2': 'https://api.semanticscholar.org/graph/v1',
             'arxiv': 'https://export.arxiv.org', 'jina': 'https://api.jina.ai',
             'openrouter': 'https://openrouter.ai/api/v1', 'crossref': 'https://api.crossref.org', '9router': 'http://localhost:20128'}


def raw_root():
    value = os.environ.get('ATLAS_RAW_DIR')
    if not value: raise RuntimeError('Set ATLAS_RAW_DIR to the private archive outside the repository')
    path = Path(value).resolve()
    if path == ROOT or ROOT in path.parents: raise RuntimeError('The private raw archive must be outside atlas-engine')
    return path


def now():
    return datetime.now(timezone.utc).isoformat()


def stable_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def normalized(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value or '') if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def title_query(seed):
    raw = seed['input']
    quoted = re.findall(r'"([^"]+)"', raw)
    if seed['group'] == 'F' and quoted:
        return quoted[0]
    if raw.startswith('MQuAKE '):
        return 'MQuAKE'
    return raw


def arxiv_from_record(record, provider):
    if provider == 's2':
        value = (record.get('externalIds') or {}).get('ArXiv')
        return re.sub(r'v\d+$', '', value) if value else None
    for location in record.get('locations') or []:
        for key in ('landing_page_url', 'pdf_url'):
            match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?', location.get(key) or '', re.I)
            if match:
                return match.group(1)
    match = re.search(r'10\.48550/arxiv\.(\d{4}\.\d{4,5})', record.get('doi') or '', re.I)
    return match.group(1) if match else None


def doi_from_record(record, provider):
    value = record.get('doi') if provider == 'openalex' else (record.get('externalIds') or {}).get('DOI')
    return re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value, flags=re.I).lower() if value else None


def candidate_summary(record, provider):
    venue = record.get('venue') if provider == 's2' else ((record.get('primary_location') or {}).get('source') or {}).get('display_name')
    return {'id': record.get('paperId') if provider == 's2' else record.get('id'),
            'title': record.get('title'), 'year': record.get('year') if provider == 's2' else record.get('publication_year'),
            'venue': venue, 'doi': doi_from_record(record, provider), 'arxiv_id': arxiv_from_record(record, provider)}


def select_candidate(candidates, seed, provider, linked_doi=None):
    """Only identifiers, exact titles or unambiguous title prefixes resolve a lead."""
    if linked_doi:
        linked = [r for r in candidates if doi_from_record(r, provider) == linked_doi]
        if len(linked) == 1:
            return linked[0], 'exact DOI shared with the independently resolved provider record'
    if seed.get('arxiv_id'):
        matches = [r for r in candidates if arxiv_from_record(r, provider) == seed['arxiv_id']]
        if not matches and linked_doi:
            matches = [r for r in candidates if doi_from_record(r, provider) == linked_doi]
        return (matches[0], 'exact external identifier') if len(matches) == 1 else (None, 'no unique external-identifier match')
    query = normalized(title_query(seed))
    # A title family can contain several papers; supplied authors/year are
    # identity constraints, not optional similarity hints.
    year = re.search(r'\b(19\d{2}|20\d{2})\b', seed['input'])
    author_hints = []
    if seed['group'] == 'F' and year:
        prefix = seed['input'].split(year.group(1))[0]
        author_hints = [normalized(re.sub(r'et al\.?', '', v)).strip() for v in re.split(r',| and ', prefix)]
    elif (author := re.search(r'\((\w+)\s+et al', seed['input'])):
        author_hints = [normalized(author.group(1))]
    if year or author_hints:
        eligible = []
        for record in candidates:
            actual_year = record.get('publication_year') if provider == 'openalex' else record.get('year')
            names = ' '.join(normalized((a.get('author') or {}).get('display_name')) for a in record.get('authorships', [])) if provider == 'openalex' else ' '.join(normalized(a.get('name')) for a in record.get('authors', []))
            if (not year or actual_year == int(year.group(1))) and all(v in names for v in author_hints if v):
                eligible.append(record)
        candidates = eligible
    matches = [r for r in candidates if normalized(r.get('title')) == query]
    if len(matches) == 1:
        return matches[0], 'exact normalized title'
    # Acronyms and deliberately shortened classic titles can extend into a subtitle.
    prefixes = [r for r in candidates if normalized(r.get('title')).startswith(query + ' ')]
    if len(prefixes) == 1 and not matches:
        return prefixes[0], 'unique title prefix; review full returned title'
    return None, 'no unique exact-title match; candidate titles require review'


class Cache:
    def __init__(self, root, offline=False, retry_errors=False):
        self.root, self.offline, self.retry_errors = root, offline, retry_errors
        self.namespace = os.environ.get('ATLAS_CACHE_NAMESPACE')
        self.last = {}; self.disabled = {}; self.network_calls = 0
        self.secrets = [v for k in ('S2_API_KEY', 'OPENALEX_API_KEY', 'JINA_API_KEY', 'OPENROUTER_API_KEY', 'ATLAS_NINEROUTER_API_KEY') if (v := os.environ.get(k))]
        for folder in ('requests', 'responses'):
            (root / folder).mkdir(parents=True, exist_ok=True)

    def request(self, provider, endpoint, params, *, body=None, force=False, attempts=5):
        public = {'provider': provider, 'endpoint': endpoint, 'params': params}
        if self.namespace:
            public['snapshot_scope'] = self.namespace
        if body is not None: public.update(method='POST', body=body)
        fingerprint = hashlib.sha256(stable_json(public)).hexdigest()
        path = self.root / 'requests' / (fingerprint + '.json')
        manifest = json.loads(path.read_text()) if path.exists() else {'request': public, 'attempts': []}
        if manifest['attempts']:
            previous = manifest['attempts'][-1]
            if self.offline or not force and not (self.retry_errors and previous['status'] in (0, 429, 500, 502, 503, 504)):
                return self.unpack(manifest, previous, fingerprint)
        if self.offline:
            return {'status': 0, 'data': None, 'error': 'cache_miss', 'request_hash': fingerprint, 'retrieved_at': None}
        if provider in self.disabled:
            return {'status': self.disabled[provider], 'data': None, 'error': 'provider_disabled_after_auth_error', 'request_hash': None, 'retrieved_at': None}
        query = dict(params)
        headers = {'User-Agent': 'AgentMemoryAtlas/0.1', 'Accept': 'application/json'}
        if provider == 'openalex':
            mailto = os.environ.get('OPENALEX_MAILTO')
            if not mailto:
                raise RuntimeError('OPENALEX_MAILTO is required for the polite pool')
            query['mailto'] = mailto
            if os.environ.get('OPENALEX_API_KEY'):
                query['api_key'] = os.environ['OPENALEX_API_KEY']
        elif os.environ.get('S2_API_KEY'):
            if provider == 's2': headers['x-api-key'] = os.environ['S2_API_KEY']
        if provider in ('jina', 'openrouter', '9router'):
            key_name = {'jina':'JINA_API_KEY','openrouter':'OPENROUTER_API_KEY','9router':'ATLAS_NINEROUTER_API_KEY'}[provider]
            if not os.environ.get(key_name): raise RuntimeError(key_name + ' missing from server environment')
            headers['Authorization'] = 'Bearer ' + os.environ[key_name]
        if body is not None: headers['Content-Type'] = 'application/json'
        url = PROVIDERS[provider] + endpoint + '?' + urllib.parse.urlencode(query)
        request_data = json.dumps(body).encode() if body is not None else None
        for attempt in range(attempts):
            interval = max(1.2,float(os.environ.get('ATLAS_S2_INTERVAL_SECONDS','1.2'))) if provider == 's2' else 3.1 if provider == 'arxiv' else 0.3
            time.sleep(max(0, interval - (time.monotonic() - self.last.get(provider, 0))))
            self.last[provider] = time.monotonic(); self.network_calls += 1
            retry_after = None
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers, data=request_data), timeout=120 if provider in ('jina', 'openrouter', '9router') else 30) as reply:
                    status, body = reply.status, reply.read()
            except urllib.error.HTTPError as exc:
                status, body, retry_after = exc.code, exc.read(), exc.headers.get('Retry-After')
            except (OSError, TimeoutError):
                status, body = 0, b'{"error":"network_error_redacted"}'
            # Some error services echo their request URL: never persist a credential.
            redacted = False
            for secret in self.secrets:
                if secret.encode() in body:
                    body = body.replace(secret.encode(), b'[REDACTED]'); redacted = True
            body_hash = hashlib.sha256(body).hexdigest()
            body_path = self.root / 'responses' / (body_hash + '.body')
            if not body_path.exists():
                body_path.write_bytes(body)
            entry = {'status': status, 'retrieved_at': now(), 'response_sha256': body_hash,
                     'body_path': str(body_path.relative_to(self.root)), 'credential_echo_redacted': redacted}
            manifest['attempts'].append(entry); path.write_bytes(stable_json(manifest))
            if status in (401, 403):
                self.disabled[provider] = status
            if status != 429 and status not in (0, 500, 502, 503, 504):
                break
            if attempt == attempts - 1:
                break
            try:
                delay = float(retry_after) if retry_after else 2 ** (attempt + 1)
            except ValueError:
                from email.utils import parsedate_to_datetime
                try: delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError): delay = 2 ** (attempt + 1)
            time.sleep(max(2 ** (attempt + 1), delay))
        return self.unpack(manifest, manifest['attempts'][-1], fingerprint)

    def unpack(self, manifest, entry, fingerprint):
        body = (self.root / entry['body_path']).read_bytes()
        try: data = json.loads(body)
        except (ValueError, UnicodeError): data = None
        return {'status': entry['status'], 'data': data, 'request_hash': fingerprint,
                'retrieved_at': entry['retrieved_at'], 'response_sha256': entry['response_sha256']}


def resolve(seed, cache, hint=None):
    original_seed = seed
    if hint:
        seed = dict(seed, arxiv_id=hint['arxiv_id'])
    evidence = []; candidates = {'s2': [], 'openalex': []}; selected = {}; notes = {}
    def fetch(provider, endpoint, params):
        result = cache.request(provider, endpoint, params)
        evidence.append({k: result.get(k) for k in ('status', 'error', 'request_hash', 'retrieved_at', 'response_sha256')} | {'provider': provider})
        return result
    if seed.get('arxiv_id'):
        result = fetch('s2', '/paper/ARXIV:' + seed['arxiv_id'], {'fields': S2_FIELDS})
        if result['status'] == 200 and isinstance(result['data'], dict): candidates['s2'] = [result['data']]
    else:
        result = fetch('s2', '/paper/search/match', {'query': title_query(seed), 'fields': S2_FIELDS})
        if result['status'] == 200 and isinstance(result['data'], dict):
            candidates['s2'] = result['data'].get('data', [result['data']])
    selected['s2'], notes['s2'] = select_candidate(candidates['s2'], seed, 's2')
    if not selected['s2'] and not seed.get('arxiv_id'):
        result = fetch('s2', '/paper/search', {'query': title_query(seed), 'limit': 10, 'fields': S2_FIELDS})
        if result['status'] == 200 and isinstance(result['data'], dict):
            candidates['s2'].extend(result['data'].get('data') or [])
            candidates['s2'] = list({x.get('paperId'): x for x in candidates['s2']}.values())
            selected['s2'], notes['s2'] = select_candidate(candidates['s2'], seed, 's2')
    linked_doi = doi_from_record(selected['s2'], 's2') if selected['s2'] else None
    if linked_doi:
        result = fetch('openalex', '/works/https://doi.org/' + urllib.parse.quote(linked_doi, safe='/'), {'select': OA_FIELDS})
        if result['status'] == 200 and isinstance(result['data'], dict): candidates['openalex'] = [result['data']]
    elif seed.get('arxiv_id'):
        # This is a lookup candidate, never an asserted DOI. The response must
        # independently return the same arXiv identifier before it can resolve.
        result = fetch('openalex', '/works/https://doi.org/10.48550/arxiv.' + seed['arxiv_id'], {'select': OA_FIELDS})
        if result['status'] == 200 and isinstance(result['data'], dict): candidates['openalex'] = [result['data']]
    selected['openalex'], notes['openalex'] = select_candidate(candidates['openalex'], seed, 'openalex', linked_doi)
    if not selected['openalex']:
        query = seed.get('arxiv_id') or title_query(seed)
        result = fetch('openalex', '/works', {'search': query, 'per-page': 5 if seed.get('arxiv_id') else 25, 'select': OA_FIELDS})
        if result['status'] == 200 and isinstance(result['data'], dict):
            candidates['openalex'].extend(result['data'].get('results') or [])
        # Avoid duplicate hits on the direct-lookup and search paths.
        candidates['openalex'] = list({x.get('id'): x for x in candidates['openalex']}.values())
        selected['openalex'], notes['openalex'] = select_candidate(candidates['openalex'], seed, 'openalex', linked_doi)
    if not selected['s2'] and selected['openalex']:
        doi = doi_from_record(selected['openalex'], 'openalex')
        if doi:
            result = fetch('s2', '/paper/DOI:' + urllib.parse.quote(doi, safe='/'), {'fields': S2_FIELDS})
            if result['status'] == 200 and isinstance(result['data'], dict):
                candidates['s2'].append(result['data']); selected['s2'], notes['s2'] = select_candidate(candidates['s2'], seed, 's2', doi)
    oa, s2 = selected['openalex'], selected['s2']
    canonical = candidate_summary(oa, 'openalex') if oa else candidate_summary(s2, 's2') if s2 else {}
    mismatch = False
    review = []
    if hint:
        review.append('Benchmark alias was resolved through a linked discovery lead and an API-confirmed arXiv identifier; owner review required.')
    if seed.get('arxiv_id') and canonical:
        alias = normalized(seed['input'].split(' (')[0])
        words = normalized(canonical.get('title'))
        # The input is often an acronym or informal alias, not a supplied title.
        alias_tokens = [v for v in re.split(r'[/"()]', seed['input']) if v.strip()]
        if not any(normalized(v) in words for v in alias_tokens if len(normalized(v)) > 2):
            mismatch = True; review.append('Supplied name/alias not found in returned title; owner review required.')
    if oa and s2 and normalized(oa.get('title')) != normalized(s2.get('title')):
        review.append('Provider titles differ; keep both original records for review.')
    if oa and s2 and oa.get('publication_year') != s2.get('year'):
        review.append('Provider publication years differ; keep both original values for owner review.')
    if canonical and seed['group'] == 'F':
        expected_year = re.search(r'\b(19\d{2}|20\d{2})\b', seed['input'])
        if expected_year and canonical.get('year') != int(expected_year.group(1)):
            review.append('Supplied year differs from the selected API record; owner review required.')
        prefix = seed['input'].split(expected_year.group(1))[0] if expected_year else ''
        expected_authors = [normalized(re.sub(r'et al\.?', '', name)).strip() for name in re.split(r',| and ', prefix)]
        actual_authors = ' '.join(normalized(a.get('name')) for a in (s2 or {}).get('authors', []))
        actual_authors += ' ' + ' '.join(normalized((a.get('author') or {}).get('display_name')) for a in (oa or {}).get('authorships', []))
        if any(name and name not in actual_authors for name in expected_authors):
            review.append('One or more supplied author names were not confirmed in the API authorship; owner review required.')
    if any('prefix' in v for v in notes.values()):
        review.append('Resolution used an unambiguous title prefix; confirm the full returned title.')
    statuses = [e['status'] for e in evidence]
    if not canonical:
        status = 'source_error' if any(x in (0, 401, 403, 429, 500, 502, 503, 504) for x in statuses) else 'unresolved'
    else:
        status = 'needs_review' if mismatch or review else 'resolved'
    return {'seed_id': seed['seed_id'], 'group': seed['group'], 'input': seed['input'], 'input_arxiv_id': original_seed.get('arxiv_id') or None,
            'resolution_hint': hint,
            'status': status, 'openalex_id': oa.get('id') if oa else None, 's2_paper_id': s2.get('paperId') if s2 else None,
            'doi': canonical.get('doi'), 'arxiv_id': canonical.get('arxiv_id') or (arxiv_from_record(s2, 's2') if s2 else None),
            'title': canonical.get('title'), 'year': canonical.get('year'), 'venue': canonical.get('venue'),
            'match_confidence_note': notes, 'title_mismatch': mismatch, 'review_notes': review,
            'source_records': {p: candidate_summary(r, p) for p, r in selected.items() if r},
            'unaccepted_candidates': {p: [candidate_summary(r, p) for r in rows if r is not selected[p]] for p, rows in candidates.items()},
            'provenance': evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--cache-only', action='store_true')
    parser.add_argument('--retry-errors', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:-[a-z0-9-]+)?', args.snapshot): raise ValueError('Invalid snapshot name')
    rows = list(csv.DictReader((ROOT / 'config/seeds.tsv').open(), delimiter='\t'))
    group_indices = Counter()
    for row in rows:
        group_indices[row['group']] += 1; row['seed_id'] = row['group'] + str(group_indices[row['group']]).zfill(2)
    if args.limit: rows = rows[:args.limit]
    cache = Cache(raw_root(), args.cache_only, args.retry_errors)
    hints_path = ROOT / 'config/resolution_hints.json'
    hints = json.loads(hints_path.read_text()) if hints_path.exists() else {}
    results = []
    for row in rows:
        results.append(resolve(row, cache, hints.get(row['seed_id'])))
        print(json.dumps({'seed': row['seed_id'], 'status': results[-1]['status'], 'requests': cache.network_calls}), flush=True)
    payload = {'schema_version': 1, 'snapshot': args.snapshot, 'phase': 'checkpoint_1_seed_resolution',
               'input_sha256': hashlib.sha256((ROOT / 'config/seeds.tsv').read_bytes()).hexdigest(),
               'resolution_hints_sha256': hashlib.sha256(hints_path.read_bytes()).hexdigest() if hints_path.exists() else None,
               'seeds': results}
    output = ROOT / 'data' / ('snapshot-' + args.snapshot)
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'seeds.json'
    content = stable_json(payload)
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError('Snapshot already exists with different contents; choose a new dated run suffix')
    path.write_bytes(content)
    counts = {'input_seeds': len(rows), 'by_group': dict(Counter(r['group'] for r in rows)), 'by_status': dict(Counter(r['status'] for r in results)),
              'resolved_openalex': sum(bool(r['openalex_id']) for r in results), 'resolved_s2': sum(bool(r['s2_paper_id']) for r in results),
              'both_providers': sum(bool(r['openalex_id'] and r['s2_paper_id']) for r in results),
              'title_mismatches': sum(r['title_mismatch'] for r in results)}
    (output / 'counts.json').write_bytes(stable_json(counts))
    print(json.dumps({'counts': counts, 'network_calls_this_run': cache.network_calls, 'output': str(path)}), flush=True)


if __name__ == '__main__': main()
