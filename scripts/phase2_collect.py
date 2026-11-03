#!/usr/bin/env python3
"""Acquire a bounded-hop snapshot; paginate every available result, report gaps.

Raw API responses and abstract text stay in the external private archive.
Only metadata, provenance, acquisition counts, and permission flags are exported.
"""
import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import yaml
from resolve_seeds import ROOT, Cache, raw_root, normalized, doi_from_record, arxiv_from_record, stable_json, now
from server_runtime import inherit_research_credentials, private_root, phase2_config

OA_FIELDS = 'id,doi,title,publication_year,publication_date,primary_location,locations,best_oa_location,ids,authorships,open_access,is_retracted,abstract_inverted_index,referenced_works,cited_by_count,type,language'
S2_FIELDS = 'paperId,title,year,venue,externalIds,authors,abstract,citationCount,referenceCount,publicationDate,publicationVenue,publicationTypes,url,isOpenAccess,openAccessPdf'


def envelope(result):
    return {k: result.get(k) for k in ('status', 'request_hash', 'retrieved_at', 'response_sha256', 'error')}


def abstract_from_index(index):
    if not isinstance(index, dict): return None
    pairs = [(pos, token) for token, positions in index.items() for pos in positions]
    return ' '.join(token for _, token in sorted(pairs)) or None


def f02_original_candidate(data, provider):
    title = normalized(data.get('title'))
    names = ' '.join(normalized((a.get('author') or {}).get('display_name')) for a in data.get('authorships') or []) if provider == 'openalex' else ' '.join(normalized(a.get('name')) for a in data.get('authors') or [])
    year = data.get('publication_year') if provider == 'openalex' else data.get('year')
    return title.startswith('on the difference between updating a knowledge base and revising it') and 'katsuno' in names and 'mendelzon' in names and year == 1991


def normalized_record(data, provider, provenance, discovery):
    identifier = data.get('id') if provider == 'openalex' else data.get('paperId')
    if not identifier or not data.get('title'): return None
    if provider == 'openalex':
        location = data.get('primary_location') or {}; source = location.get('source') or {}
        venue = source.get('display_name'); source_type = source.get('type')
        authors = [{'id': (a.get('author') or {}).get('id'), 'name': (a.get('author') or {}).get('display_name')} for a in data.get('authorships') or []]
        abstract = abstract_from_index(data.get('abstract_inverted_index'))
        locations = data.get('locations') or []
        oa_urls = [l.get('pdf_url') or l.get('landing_page_url') for l in locations if l.get('is_oa')]
        licenses = sorted({str(l['license']) for l in locations if l.get('license')})
        year = data.get('publication_year'); date = data.get('publication_date')
        references = data.get('referenced_works') or []
    else:
        venue = data.get('venue') or (data.get('publicationVenue') or {}).get('name')
        source_type = None; authors = data.get('authors') or []; abstract = data.get('abstract')
        year = data.get('year'); date = data.get('publicationDate'); references = []
        oa_urls = [(data.get('openAccessPdf') or {}).get('url')] if data.get('isOpenAccess') else []
        licenses = [(data.get('openAccessPdf') or {}).get('license')]
        licenses = [x for x in licenses if x]
    arxiv = arxiv_from_record(data, provider)
    is_repository = bool(re.search(r'arxiv|biorxiv|medrxiv|repository|zenodo', venue or '', re.I)) or source_type == 'repository'
    return {'provider': provider, 'source_id': identifier, 'title': data['title'], 'doi': doi_from_record(data, provider),
            'arxiv_id': arxiv, 'year': year, 'publication_date': date, 'venue': venue, 'is_repository': is_repository,
            'authors': authors, 'abstract': abstract, 'abstract_source': provider if abstract else None,
            'abstract_display_allowed': False, 'content_license_observations': licenses,
            'open_access_urls': [v for v in oa_urls if v], 'citation_count': data.get('cited_by_count') if provider == 'openalex' else data.get('citationCount'),
            'is_retracted': bool(data.get('is_retracted')), 'references': references,
            'provenance': provenance, 'discovery': discovery}


class Collector:
    def __init__(self, offline=False):
        self.config = phase2_config()
        self.cache = Cache(raw_root(), offline=offline)
        self.folder = private_root() / self.config['snapshot']; self.folder.mkdir(exist_ok=True)
        self.events = []; self.edges = []; self.gaps = []; self.queries = []; self.arxiv = {}
        self.seed_rows = json.loads((ROOT / 'data' / ('snapshot-' + self.config['seed_snapshot']) / 'seeds.json').read_text())['seeds']
        self.seed_metadata = {}; self.first_retry = []

    def request(self, provider, endpoint, params, **kwargs):
        result = self.cache.request(provider, endpoint, params, attempts=self.config['api']['transient_attempts'], **kwargs)
        if result['status'] != 200:
            self.gaps.append({'provider': provider, 'endpoint': endpoint, 'parameters': params, **envelope(result)})
        return result

    def add(self, data, provider, result, discovery):
        record = normalized_record(data, provider, envelope(result), discovery)
        if record:
            self.events.append(record)
            return record
        return None

    def pages_oa(self, params, discovery):
        cursor = '*'; pages = 0; received = 0; total = None
        while cursor:
            result = self.request('openalex', '/works', dict(params, cursor=cursor, **{'per-page': 200, 'select': OA_FIELDS}))
            if result['status'] != 200 or not isinstance(result['data'], dict): break
            data = result['data']; total = (data.get('meta') or {}).get('count', total)
            rows = data.get('results') or []; pages += 1; received += len(rows)
            for row in rows:
                if discovery.get('method') != 'f02_original_version_discovery' or f02_original_candidate(row, 'openalex'):
                    self.add(row, 'openalex', result, discovery)
            nxt = (data.get('meta') or {}).get('next_cursor')
            if not rows or not nxt or nxt == cursor or total is not None and received >= total: break
            cursor = nxt
        return {'reported_total': total, 'received': received, 'pages': pages, 'complete': total is not None and received >= total}

    def pages_s2(self, seed_id, paper_id, direction):
        offset = 0
        while True:
            result = self.request('s2', '/paper/' + quote(paper_id, safe=':') + '/' + direction,
                                  {'fields': S2_FIELDS + ',contexts,intents,isInfluential', 'limit': 1000, 'offset': offset})
            if result['status'] != 200 or not isinstance(result['data'], dict): break
            data = result['data']; rows = data.get('data') or []
            for entry in rows:
                paper = entry.get('citedPaper' if direction == 'references' else 'citingPaper') or {}
                record = self.add(paper, 's2', result, {'method': direction, 'seed_id': seed_id})
                if record:
                    source, target = (paper_id, record['source_id']) if direction == 'references' else (record['source_id'], paper_id)
                    self.edges.append({'provider': 's2', 'source': source, 'target': target,
                                       'provenance': envelope(result), 'contexts': entry.get('contexts') or [],
                                       'is_influential': entry.get('isInfluential')})
            nxt = data.get('next')
            if nxt is None or not rows or nxt == offset: break
            offset = nxt

    def retry_missing_once(self):
        for seed in self.seed_rows:
            if seed['seed_id'] not in ('A02', 'F03'): continue
            external = 'ARXIV:' + seed['arxiv_id'] if seed.get('arxiv_id') else 'DOI:' + seed['doi']
            # Exactly one HTTP attempt, no title guess and no hidden retry loop.
            result = self.cache.request('s2', '/paper/' + quote(external, safe=':/'), {'fields': S2_FIELDS}, attempts=1)
            self.first_retry.append({'seed_id': seed['seed_id'], 'lookup': external, **envelope(result)})
            if result['status'] == 200 and isinstance(result['data'], dict):
                seed['s2_paper_id'] = result['data'].get('paperId')
                self.add(result['data'], 's2', result, {'method': 'requested_one_time_retry', 'seed_id': seed['seed_id']})
            else:
                seed['s2_paper_id'] = None
        (self.folder / 'requested_retries.json').write_bytes(stable_json(self.first_retry))

    def seeds(self):
        for seed in self.seed_rows:
            label = seed['input'].split(' (')[0].split(' "')[0].strip()
            self.seed_metadata[seed['seed_id']] = {'group': seed['group'], 'display_short_name': label,
                'approved_alias': bool(seed.get('title_mismatch')), 'alias_approved_on': '2026-11-01' if seed.get('title_mismatch') else None,
                'arxiv_id': seed.get('arxiv_id'), 'openalex_id': seed.get('openalex_id'), 's2_paper_id': seed.get('s2_paper_id')}
            if seed.get('openalex_id'):
                result = self.request('openalex', '/works/' + seed['openalex_id'].rsplit('/', 1)[-1], {'select': OA_FIELDS})
                if result['status'] == 200:
                    record = self.add(result['data'], 'openalex', result, {'method': 'seed', 'seed_id': seed['seed_id']})
                    if record and not record['arxiv_id']: record['arxiv_id'] = seed.get('arxiv_id')
            if seed.get('s2_paper_id'):
                result = self.request('s2', '/paper/' + seed['s2_paper_id'], {'fields': S2_FIELDS})
                if result['status'] == 200:
                    record = self.add(result['data'], 's2', result, {'method': 'seed', 'seed_id': seed['seed_id']})
                    if record and not record['arxiv_id']: record['arxiv_id'] = seed.get('arxiv_id')
            print(json.dumps({'stage': 'seed_metadata', 'seed': seed['seed_id'], 'events': len(self.events)}), flush=True)
        # Search for a proceedings identity instead of inferring it from a date.
        query = 'On the difference between updating a knowledge base and revising it'
        self.pages_oa({'search': query, 'filter': 'publication_year:1991'}, {'method': 'f02_original_version_discovery', 'seed_id': 'F02'})
        result = self.request('s2', '/paper/search', {'query': query, 'year': '1991', 'limit': 100, 'fields': S2_FIELDS})
        if result['status'] == 200:
            for row in (result['data'] or {}).get('data') or []:
                if f02_original_candidate(row, 's2'):
                    self.add(row, 's2', result, {'method': 'f02_original_version_discovery', 'seed_id': 'F02'})

    def snowball(self):
        initial = list(self.events); refs = set(); fetched_oa = {r['source_id'] for r in initial if r['provider'] == 'openalex'}
        for seed in self.seed_rows:
            if seed['group'] == 'F': continue
            records = [r for r in initial if r['discovery'].get('seed_id') == seed['seed_id'] and r['provider'] == 'openalex']
            for record in records:
                for target in record['references']:
                    self.edges.append({'provider': 'openalex', 'source': record['source_id'], 'target': target, 'provenance': record['provenance']})
                    refs.add(target)
            if seed.get('openalex_id'):
                detail = self.pages_oa({'filter': 'cites:' + seed['openalex_id'].rsplit('/', 1)[-1]}, {'method': 'citations', 'seed_id': seed['seed_id']})
                self.queries.append({'provider': 'openalex', 'kind': 'seed_citations', 'query': seed['openalex_id'], **detail})
            if seed.get('s2_paper_id'):
                for direction in ('references', 'citations'): self.pages_s2(seed['seed_id'], seed['s2_paper_id'], direction)
            print(json.dumps({'stage': 'snowball', 'seed': seed['seed_id'], 'events': len(self.events)}), flush=True)
        missing = sorted(refs - fetched_oa)
        for start in range(0, len(missing), 50):
            identifiers = '|'.join(value.rsplit('/', 1)[-1] for value in missing[start:start+50])
            self.pages_oa({'filter': 'openalex:' + identifiers}, {'method': 'seed_references'})
        # An OpenAlex citing work supplies referenced_works, preserving direction.
        for record in self.events:
            if record['provider'] == 'openalex':
                for target in record['references']:
                    self.edges.append({'provider': 'openalex', 'source': record['source_id'], 'target': target, 'provenance': record['provenance']})

    def keywords(self):
        for query in self.config['queries']:
            cutoff = self.config['cutoff']
            details = self.pages_oa({'filter': 'title_and_abstract.search:' + query + ',from_publication_date:2023-01-01,to_publication_date:' + cutoff}, {'method': 'keyword', 'query': query})
            self.queries.append({'provider': 'openalex', 'kind': 'keyword', 'search_fields': 'title_and_abstract', 'query': query, **details})
            token = None; received = 0; total = None; pages = 0
            while True:
                params = {'query': query, 'year': '2023:2026', 'fields': S2_FIELDS}
                if token: params['token'] = token
                result = self.request('s2', '/paper/search/bulk', params)
                if result['status'] != 200 or not isinstance(result['data'], dict): break
                data = result['data']; total = data.get('total', total); rows = data.get('data') or []
                for row in rows:
                    if not row.get('publicationDate') or row['publicationDate'] <= cutoff:
                        self.add(row, 's2', result, {'method': 'keyword', 'query': query})
                received += len(rows); pages += 1; nxt = data.get('token')
                if not nxt or not rows or nxt == token: break
                token = nxt
            self.queries.append({'provider': 's2', 'kind': 'keyword', 'query': query, 'reported_total': total, 'received': received, 'pages': pages, 'complete': total is not None and received >= total})
            print(json.dumps({'stage': 'keyword', 'query': query, 'events': len(self.events)}), flush=True)

    def dates(self):
        ids = sorted({r['arxiv_id'] for r in self.events if r['arxiv_id']})
        for start in range(0, len(ids), 100):
            group = ids[start:start+100]
            result = self.request('arxiv', '/api/query', {'id_list': ','.join(group), 'max_results': 100})
            if result['status'] == 200:
                try:
                    data = ET.fromstring((raw_root() / 'responses' / (result['response_sha256'] + '.body')).read_bytes())
                    for entry in data.findall('{http://www.w3.org/2005/Atom}entry'):
                        text = entry.findtext('{http://www.w3.org/2005/Atom}id') or ''
                        match = re.search(r'(\d{4}\.\d{4,5})(?:v\d+)?$', text)
                        if match:
                            self.arxiv[match.group(1)] = {'first_public_date': entry.findtext('{http://www.w3.org/2005/Atom}published'),
                                'updated': entry.findtext('{http://www.w3.org/2005/Atom}updated'), 'provenance': envelope(result)}
                except ET.ParseError:
                    self.gaps.append({'provider': 'arxiv', 'error': 'invalid_xml', **envelope(result)})
            print(json.dumps({'stage': 'arxiv_v1_dates', 'requested': min(start+100, len(ids)), 'total': len(ids), 'resolved': len(self.arxiv)}), flush=True)

    def save(self, stage):
        for name, value in [('candidate_events.json', self.events), ('citation_events.json', self.edges), ('acquisition_gaps.json', self.gaps),
                            ('query_log.json', self.queries), ('arxiv_dates.json', self.arxiv), ('seed_metadata.json', self.seed_metadata), ('requested_retries.json', self.first_retry)]:
            (self.folder / name).write_bytes(stable_json(value))
        (self.folder / 'COLLECTION.json').write_bytes(stable_json({'candidate_observations': len(self.events), 'citation_observations': len(self.edges),
            'api_gaps': len(self.gaps), 'query_log_entries': len(self.queries), 'arxiv_v1_dates': len(self.arxiv), 'network_calls': self.cache.network_calls,
            'cache_namespace': self.cache.namespace,
            'stage': stage, 'checkpoint_at': now(), 'snapshot': self.config['snapshot']}))

    def run(self):
        self.retry_missing_once(); self.seeds(); self.save('seeds')
        self.snowball(); self.save('snowball')
        self.keywords(); self.save('keywords')
        self.dates(); self.save('complete')
        print((self.folder / 'COLLECTION.json').read_text(), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--cache-only', action='store_true'); parser.add_argument('--prepare-screening', action='store_true'); args = parser.parse_args()
    os.umask(0o077); inherit_research_credentials(); Collector(args.cache_only).run()
    if args.prepare_screening:
        import phase2_merge, phase2_vectors
        phase2_merge.main(); phase2_vectors.main(args.cache_only)
