#!/usr/bin/env python3
"""Deterministic version-aware deduplication; no graph layout is computed here."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

import yaml
from resolve_seeds import ROOT, normalized, stable_json, raw_root
from server_runtime import private_root, phase2_config


def source_key(record): return record['provider'] + ':' + record['source_id']


def deduplicate(events):
    observations = defaultdict(list)
    for record in events: observations[source_key(record)].append(record)
    records = {k: max(rows, key=lambda r: (bool(r.get('abstract')), bool(r.get('venue')), len(r.get('abstract') or ''))) for k, rows in observations.items()}
    parent = {k: k for k in records}; merges = []; suspicious = []
    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]; key = parent[key]
        return key
    def join(a, b, reason):
        x, y = find(a), find(b)
        if x != y:
            parent[max(x,y)] = min(x,y); merges.append({'left': a, 'right': b, 'reason': reason})
    for field in ('doi', 'arxiv_id'):
        index = {}
        for key, record in sorted(records.items()):
            values = [record.get(field)] + (record.get('linked_dois') or [] if field == 'doi' else [])
            for value in values:
                if not value: continue
                if value in index: join(key, index[value], 'shared_' + field)
                else: index[value] = key
    titles = defaultdict(list)
    for key, record in records.items():
        if record.get('year') is not None: titles[(normalized(record['title']), record['year'])].append(key)
    for _, keys in sorted(titles.items()):
        for key in sorted(keys)[1:]:
            base = sorted(keys)[0]
            if find(key) == find(base): continue
            a, b = records[key], records[base]
            if a.get('doi') and b.get('doi') and a['doi'] != b['doi']:
                suspicious.append({'left': key, 'right': base, 'reason': 'same_title_year_but_conflicting_strong_identifiers'})
            else: join(key, base, 'normalized_title_and_year')
    # The owner explicitly authorized preserving this original/proceedings and
    # book-chapter version family. It is not a generic fuzzy-title merge rule.
    f02 = []
    for key, record in records.items():
        names = ' '.join(normalized(a.get('name')) for a in record.get('authors', []))
        if normalized(record['title']).startswith('on the difference between updating a knowledge base and revising it') and 'katsuno' in names and 'mendelzon' in names:
            f02.append(key)
    for key in sorted(f02)[1:]: join(key, sorted(f02)[0], 'owner_authorized_F02_version_family')
    groups = defaultdict(list)
    for key in records: groups[find(key)].append(key)
    return records, observations, [sorted(v) for _,v in sorted(groups.items())], merges, suspicious


def build_papers(events, seed_metadata, arxiv_dates):
    records, observations, groups, merges, suspicious = deduplicate(events)
    papers = []; redirects = {}; missing_dates = []
    for keys in groups:
        versions = [records[k] for k in keys]
        seed_ids = set()
        for key in keys:
            for record in observations[key]:
                discovery = record.get('discovery') or {}
                if discovery.get('method') in ('seed', 'requested_one_time_retry') and discovery.get('seed_id'):
                    seed_ids.add(discovery['seed_id'])
        # Detect the genuine KR proceedings version by its venue, not year alone.
        kr = [r for r in versions if r.get('year') == 1991 and re.search(r'\bKR\b|knowledge representation and reasoning|principles of knowledge representation', r.get('venue') or '', re.I)] if 'F02' in seed_ids else []
        if kr:
            canonical = sorted(kr, key=source_key)[0]; canonical_reason = 'KR_1991_proceedings_version_observed_in_API'
        elif 'F02' in seed_ids:
            book = [r for r in versions if r.get('year') == 1992 and ('cambridge' in (r.get('venue') or '').lower() or (r.get('doi') or '').startswith('10.1017/'))]
            canonical = sorted(book or versions, key=source_key)[0]; canonical_reason = 'Cambridge_1992_record_with_original_KR_1991_note'
        else:
            canonical = max(versions, key=lambda r: (not r.get('is_repository'), r['provider'] == 'openalex', bool(r.get('venue')), r['source_id']))
            canonical_reason = 'venue_version_preferred_all_source_versions_retained'
        identifier = canonical['source_id'] if canonical['provider'] == 'openalex' else 's2:' + canonical['source_id']
        for key in keys: redirects[key] = identifier
        arxiv_ids = sorted({r['arxiv_id'] for r in versions if r.get('arxiv_id')})
        v1s = [arxiv_dates[a]['first_public_date'] for a in arxiv_ids if a in arxiv_dates and arxiv_dates[a].get('first_public_date')]
        if v1s:
            first_date = min(v1s); date_basis = 'arxiv_v1'; first_year = int(first_date[:4])
        elif arxiv_ids:
            first_date = None; first_year = None; date_basis = 'arxiv_v1_unavailable'
            missing_dates.append(identifier)
        else:
            dates = sorted(r['publication_date'] for r in versions if r.get('publication_date'))
            first_date = dates[0] if dates else None
            first_year = int(first_date[:4]) if first_date else min((r['year'] for r in versions if r.get('year')), default=None)
            date_basis = 'earliest_available_provider_publication_metadata'
        if 'F02' in seed_ids and not kr:
            first_year = 1991; first_date = None; date_basis = 'owner_supplied_original_KR_year_date_unknown'
        abstract_version = max(versions, key=lambda r: (bool(r.get('abstract')), r['provider'] == 'openalex', len(r.get('abstract') or '')))
        abstract = abstract_version.get('abstract')
        venue_versions = [r for r in versions if not r.get('is_repository') and r.get('venue')]
        venue_version = canonical if canonical in venue_versions else max(venue_versions, key=lambda r: (r['provider'] == 'openalex', r.get('year') or 0), default=None)
        aliases = [seed_metadata[s]['display_short_name'] for s in sorted(seed_ids) if s in seed_metadata]
        papers.append({'id': identifier, 'title': canonical['title'], 'display_short_name': aliases[0] if aliases else None,
            'aliases': aliases, 'seed_ids': sorted(seed_ids), 'seed_groups': sorted({seed_metadata[s]['group'] for s in seed_ids if s in seed_metadata}),
            'source_ids': {'openalex': sorted(r['source_id'] for r in versions if r['provider'] == 'openalex'), 's2': sorted(r['source_id'] for r in versions if r['provider'] == 's2')},
            'dois': sorted({doi for r in versions for doi in [r.get('doi')]+r.get('linked_dois',[]) if doi}), 'arxiv_ids': arxiv_ids,
            'first_public_date': first_date, 'first_public_year': first_year, 'first_public_date_basis': date_basis,
            'venue': venue_version.get('venue') if venue_version else None,
            'venue_publication_year': venue_version.get('year') if venue_version else None,
            'arxiv_year': first_year if date_basis == 'arxiv_v1' else None,
            'arxiv_year_label': 'arXiv ' + str(first_year) if date_basis == 'arxiv_v1' and first_year != (venue_version.get('year') if venue_version else None) else None,
            'metadata_years': sorted({r['year'] for r in versions if r.get('year')}),
            'canonical_record_reason': canonical_reason,
            'original_version_note': 'Originally appeared at KR 1991; date and original venue attribution supplied by the owner.' if 'F02' in seed_ids and not kr else None,
            'authors': canonical.get('authors') or [], 'citation_counts': {r['provider']: r.get('citation_count') for r in versions},
            'abstract': abstract, 'abstract_available': bool(abstract), 'abstract_source': abstract_version.get('abstract_source'),
            'abstract_provenance': abstract_version.get('provenance') if abstract else None,
            'abstract_sha256': hashlib.sha256(abstract.encode()).hexdigest() if abstract else None,
            'abstract_display_allowed': False,
            'evidence_level': 'abstract' if abstract else 'metadata',
            'open_access_urls': sorted({u for r in versions for u in r.get('open_access_urls', [])}),
            'is_retracted': any(r.get('is_retracted') for r in versions),
            'publication_versions': [{k:r.get(k) for k in ('provider','source_id','doi','arxiv_id','year','publication_date','venue','provenance')} for r in sorted(versions,key=source_key)]})
    return sorted(papers, key=lambda p:p['id']), redirects, merges, suspicious, missing_dates


def retain_prior_seed_ids(papers, prior_seeds):
    """Preserve verified identities when a later detail endpoint is unavailable."""
    by_seed = {seed: paper for paper in papers for seed in paper['seed_ids']}
    owners = {(provider, identifier): paper['id'] for paper in papers
              for provider, identifiers in paper['source_ids'].items() for identifier in identifiers}
    for seed in prior_seeds:
        paper = by_seed.get(seed['seed_id'])
        if not paper:
            continue
        for provider, record in seed.get('source_records', {}).items():
            identifier = record.get('id')
            if not identifier or identifier in paper['source_ids'].get(provider, []):
                continue
            if (provider, identifier) in owners and owners[(provider, identifier)] != paper['id']:
                raise RuntimeError('Prior identity exposes a frozen-cohort conflict; review in a new run')
            provenance = next((p for p in seed['provenance']
                if p.get('provider') == provider and p.get('status') == 200), None)
            if not provenance:
                raise RuntimeError('Prior seed identity has no successful stored API provenance')
            paper['source_ids'].setdefault(provider, []).append(identifier)
            paper['source_ids'][provider].sort()
            paper['publication_versions'].append({'provider': provider, 'source_id': identifier,
                'arxiv_id': record.get('arxiv_id'), 'doi': record.get('doi'),
                'year': record.get('year'), 'venue': record.get('venue'), 'publication_date': None,
                'provenance': provenance, 'metadata_from_prior_snapshot': True})
            paper.setdefault('source_id_retention', []).append({'provider': provider, 'id': identifier,
                'seed_id': seed['seed_id'], 'reason': 'prior verified API identity retained after later detail lookup failure'})
            owners[(provider, identifier)] = paper['id']


def main():
    config = phase2_config(); folder = private_root() / config['snapshot']
    collection = json.loads((folder / 'COLLECTION.json').read_text())
    if collection.get('stage') != 'complete': raise RuntimeError('Acquisition is not complete')
    events = json.loads((folder / 'candidate_events.json').read_text())
    seeds = json.loads((folder / 'seed_metadata.json').read_text()); dates = json.loads((folder / 'arxiv_dates.json').read_text())
    # The official arXiv metadata links an arXiv identity to its registered venue
    # DOI. Keep that identity evidence, rather than guessing by similar titles.
    for digest in {d['provenance']['response_sha256'] for d in dates.values()}:
        document=ET.fromstring((raw_root()/'responses'/(digest+'.body')).read_bytes())
        for entry in document.findall('{http://www.w3.org/2005/Atom}entry'):
            identifier=entry.findtext('{http://www.w3.org/2005/Atom}id') or ''
            match=re.search(r'(\d{4}\.\d{4,5})(?:v\d+)?$',identifier)
            doi_text=entry.findtext('{http://arxiv.org/schemas/atom}doi') or ''
            if match and match.group(1) in dates:
                dates[match.group(1)]['related_dois']=[d.rstrip(';,').lower() for d in re.findall(r'10\.\d{4,9}/\S+',doi_text)]
    for record in events:
        if record.get('arxiv_id') in dates:record['linked_dois']=dates[record['arxiv_id']].get('related_dois') or []
    papers, redirects, merges, suspicious, missing_dates = build_papers(events, seeds, dates)
    observed_source_identities = len(redirects)
    prior = json.loads((ROOT/'data'/('snapshot-'+config['seed_snapshot'])/'seeds.json').read_text())['seeds']
    retain_prior_seed_ids(papers, prior)
    for paper in papers:
        for provider, identifiers in paper['source_ids'].items():
            for identifier in identifiers:
                redirects[provider+':'+identifier] = paper['id']
    protocol_path=folder/'SCREENING-PROTOCOL.json'
    if protocol_path.exists():
        frozen=json.loads(protocol_path.read_text())
        cohort_hash=hashlib.sha256(stable_json([p['id'] for p in papers])).hexdigest()
        if cohort_hash!=frozen['cohort_sha256']:raise RuntimeError('Identity changes would alter the frozen screening cohort; create a separately documented run')
    edges = set(); unresolved = 0
    for edge in json.loads((folder / 'citation_events.json').read_text()):
        a = redirects.get(edge['provider'] + ':' + edge['source']); b = redirects.get(edge['provider'] + ':' + edge['target'])
        if a and b and a != b: edges.add((a,b))
        else: unresolved += 1
    for name,value in [('papers.private.json',papers),('redirects.json',redirects),('merge_events.json',merges),('suspected_duplicates.json',suspicious),
                       ('resolved_edges.json',sorted(edges)),('missing_arxiv_v1_dates.json',missing_dates)]: (folder/name).write_bytes(stable_json(value))
    summary={'candidate_observations':len(events),'source_identities':observed_source_identities,
        'source_identity_links_total':len(redirects),'after_dedup':len(papers),'merge_events':len(merges),
        'suspected_duplicates':len(suspicious),'abstracts_available':sum(p['abstract_available'] for p in papers),
        'open_fulltext_links_available':sum(bool(p['open_access_urls']) for p in papers),'resolved_citation_links':len(edges),
        'unresolved_citation_observations':unresolved,'arxiv_v1_dates_missing':len(missing_dates)}
    (folder/'DEDUPLICATION.json').write_bytes(stable_json(summary));print(json.dumps(summary),flush=True)


if __name__ == '__main__': main()
