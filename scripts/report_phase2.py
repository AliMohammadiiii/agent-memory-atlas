#!/usr/bin/env python3
"""Export checkpoint 2 from private derived inputs; no network or abstract export."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import yaml
import numpy as np
from resolve_seeds import ROOT, stable_json, raw_root
from server_runtime import private_root, phase2_config


PUBLIC_FIELDS = ('id', 'title', 'display_short_name', 'aliases', 'dois', 'arxiv_ids',
    'source_ids', 'authors', 'venue', 'venue_publication_year', 'first_public_date',
    'first_public_date_basis', 'first_public_year', 'arxiv_year', 'arxiv_year_label',
    'metadata_years', 'publication_versions', 'canonical_record_reason',
    'original_version_note', 'seed_ids', 'seed_groups', 'citation_counts',
    'is_retracted', 'open_access_urls', 'abstract_available', 'abstract_sha256',
    'abstract_source', 'abstract_provenance', 'abstract_display_allowed', 'evidence_level', 'source_id_retention')


def public_paper(paper):
    result = {key: paper.get(key) for key in PUBLIC_FIELDS}
    result['abstract_display_allowed'] = False
    result['full_text_stored'] = False
    review = json.loads((ROOT/'config/seed_review.json').read_text())
    result['owner_approved_alias_flags'] = sorted(set(paper.get('seed_ids', [])) & set(review['approved_alias_seed_ids']))
    return result


def evidence_counts(papers):
    counts = Counter(p['evidence_level'] for p in papers)
    if sum(counts.values()) != len(papers):
        raise ValueError('Evidence levels do not partition the corpus')
    return dict(sorted(counts.items()))


def s2_snowball_coverage(seed_metadata, namespace=None):
    """Recover endpoint/page coverage from stored manifests, without new calls."""
    wanted = {row['s2_paper_id']: seed for seed,row in seed_metadata.items()
              if row['group'] != 'F' and row.get('s2_paper_id')}
    groups = {}
    for path in sorted((raw_root()/'requests').glob('*.json')):
        manifest = json.loads(path.read_text()); request = manifest['request']
        if request.get('snapshot_scope') != namespace:
            continue
        if request['provider'] != 's2':
            continue
        match = re.fullmatch(r'/paper/([^/]+)/(references|citations)', request['endpoint'])
        if not match or match[1] not in wanted or not manifest['attempts']:
            continue
        last = manifest['attempts'][-1]; body = json.loads((raw_root()/last['body_path']).read_text())
        key = (wanted[match[1]], match[2]); page = {
            'offset': request['params'].get('offset', 0), 'status': last['status'],
            'received': len(body.get('data') or []) if last['status'] == 200 else 0,
            'next': body.get('next') if last['status'] == 200 else None,
            'request_hash': path.stem, 'response_sha256': last['response_sha256'],
            'retrieved_at': last['retrieved_at']}
        groups.setdefault(key, []).append(page)
    rows = []
    for paper_id, seed in sorted(wanted.items(), key=lambda pair: pair[1]):
        for direction in ('references', 'citations'):
            pages = sorted(groups.get((seed,direction), []), key=lambda p: p['offset'])
            complete = bool(pages) and all(p['status'] == 200 for p in pages) and pages[-1]['next'] is None
            rows.append({'provider': 's2', 'kind': 'seed_'+direction, 'seed_id': seed,
                'query': paper_id, 'pages': len(pages), 'received': sum(p['received'] for p in pages),
                'reported_total': None, 'complete': complete, 'page_provenance': pages})
    return rows


def embedding_response_evidence(parameters, namespace=None):
    rows = []
    for path in sorted((raw_root()/'requests').glob('*.json')):
        manifest = json.loads(path.read_text()); request = manifest['request']
        if request.get('snapshot_scope') != namespace:
            continue
        body = request.get('body') or {}
        if request['provider'] != 'jina' or body.get('model') != parameters['model']:
            continue
        if body.get('dimensions') != parameters['dimensions'] or body.get('task') != parameters['document_task']:
            continue
        for response in manifest['attempts']:
            if response['status'] == 200:
                rows.append({'request_hash': path.stem, 'response_sha256': response['response_sha256'],
                    'retrieved_at': response['retrieved_at'], 'input_count': len(body.get('input') or [])})
    return sorted(rows, key=lambda r: (r['retrieved_at'], r['request_hash']))


def render_report(counts, threshold, protocol, queries):
    a = threshold['sample_agreement']; c = threshold['calibration']; v = threshold['validation']
    cc = threshold['calibration_confusion']
    lines = ['# Phase 2 — checkpoint 2', '',
        f"Snapshot cutoff: **{counts['snapshot_date']}**. Processing: **private server**.", '',
        'This checkpoint covers acquisition, identity merges, private abstract analysis and relevance screening. '
        'No graph, clusters, capability extraction or public site has been built.', '',
        '| Measure | Count |', '|---|---:|']
    labels = [('Candidate observations', 'candidate_observations'), ('Phase 2 source identities', 'unique_source_identities'),
        ('Additional prior verified seed identities retained', 'prior_seed_identities_retained'),
        ('Deduplicated candidate works', 'after_dedup'), ('Included works', 'included'),
        ('Excluded works', 'excluded'), ('Deferred relevance decisions', 'deferred'),
        ('Unresolved seeds', 'unresolved_seeds'), ('Candidate works with abstracts (private)', 'candidate_abstracts_available'),
        ('Included works with abstracts (private)', 'abstracts_available'),
        ('Candidate works with open-access full-text links', 'candidate_oa_full_text_available'),
        ('Included works with open-access full-text links', 'open_access_full_text_available'),
        ('Stored full texts', 'full_text_works'), ('Within-corpus citation links', 'resolved_links'),
        ('Acquisition gaps', 'acquisition_gaps'), ('Suspected duplicate pairs awaiting review', 'suspected_duplicates')]
    lines += [f'| {label} | {counts[key]} |' for label, key in labels]
    lines += ['', '## Frozen screening method', '', protocol['inclusion_definition'], '',
        f"A uniform random sample of {a['items']} non-seed deduplicated works was frozen before scoring, "
        f"with RNG seed {protocol['sample_random_seed']}. The first {protocol['calibration_size']} "
        f"items calibrated the threshold; the last {protocol['validation_size']} were held out. "
        'The reference labels are machine-generated evidence assessments, not human gold labels. '
        'Luna received the titles/abstracts and inclusion definition without those labels or embedding scores.', '',
        f"Three-class agreement: **{a['agreements']}/{a['items']} ({a['agreement']:.1%})**; "
        f"Cohen’s κ **{a['cohen_kappa']:.3f}**. Reference labels: {a['manual_labels']}. "
        f"Model labels: {a['model_labels']}.", '',
        f"Cosine threshold: **{threshold['threshold']:.9f}**, selected by maximum calibration precision "
        'subject to recall ≥0.90, with ties choosing the highest threshold. '
        'Uncertain labels are omitted from binary metrics, never treated as negatives.', '',
        f"Calibration: {c['decidable_items']}/{protocol['calibration_size']} decidable items; "
        f"TP={cc['tp']}, FP={cc['fp']}, FN={cc['fn']}, TN={cc['tn']}; "
        f"precision {cc['tp']}/{cc['tp']+cc['fp']} = {c['precision']:.3f}, "
        f"recall {cc['tp']}/{cc['tp']+cc['fn']} = {c['recall']:.3f}.", '',
        f"Held-out validation: {v['decidable_items']}/{protocol['validation_size']} decidable items; "
        f"TP={v['tp']}, FP={v['fp']}, FN={v['fn']}, TN={v['tn']}; "
        f"precision={v['precision']}, recall={v['recall']}.", '',
        f"The ±{protocol['borderline_margin']} cosine band uses an LLM relevance judgment. "
        'Approved seeds and theory anchors are retained. Deferred decisions are held outside the included corpus. '
        'Agreement is not an accuracy estimate; the held-out set is small and shares the agent-generated reference labels.', '',
        '## Keyword acquisition', '',
        'Queries used English title/abstract matching and the 2023-to-cutoff window. '
        'The received count is the number cached, and may be below the API-reported total. '
        'Snowballing is logged separately in query-log.json. Group F anchors were not expanded.', '',
        '| API | Query | Reported total | Received | Complete |', '|---|---|---:|---:|---|']
    for row in queries:
        if row.get('kind') == 'keyword':
            query = row['query'].replace('|', '\\|')
            lines.append(f"| {row['provider']} | {query} | {row.get('reported_total')} | {row['received']} | {row['complete']} |")
    lines += ['', '## Coverage and data quality', '',
        'The exploratory OpenAlex search initially used its default search scope, which also searched full text. '
        'It was stopped before sampling or scoring. Its responses remain in the private archive. '
        'The final cohort was rebuilt using explicit title_and_abstract.search with the same query list; '
        'no results from the broader exploratory run entered the frozen cohort unless independently reacquired.', '',
        'PLACE’s one authorized S2 retry returned 429; it remains OpenAlex-only. '
        'Reiter’s DOI retry succeeded. Neither was guessed from a title. '
        'A verified KR 1991 proceedings record is canonical for Katsuno and Mendelzon, with the Cambridge version retained. '
        'Separate first-public and venue years are preserved; all identity merges and suspected duplicates are exported.', '',
        'Abstract availability means private evidence availability, not permission to display that text. '
        'No abstracts or full texts are included in this export. OA full-text counts represent links, not fetched documents. '
        'API failures, unexpanded or incomplete citation results, missing abstracts, English-query bias, '
        'metadata errors and the cutoff limit coverage. See docs/LIMITATIONS.md and data-quality.json.', '',
        '**Review gate:** checkpoint 2 requires owner approval before clustering or checkpoint 3. '
        'Nothing is published.']
    return '\n'.join(lines) + '\n'


def build(source, output):
    def read(name):
        return json.loads((source / name).read_text())
    papers = read('papers.private.json'); decisions = read('screening_decisions.json')
    by_id = {p['id']: p for p in papers}; decision = {d['id']: d for d in decisions}
    if len(by_id) != len(papers) or set(by_id) != set(decision) or len(decision) != len(decisions):
        raise ValueError('Screening decisions do not partition the frozen cohort')
    included = [p for p in papers if decision[p['id']]['label'] == 'include']
    published_records = [{**public_paper(p), 'screening': decision[p['id']]} for p in included]
    included_ids = {p['id'] for p in included}
    edges = [e for e in read('resolved_edges.json') if e[0] in included_ids and e[1] in included_ids]
    collection = read('COLLECTION.json'); dedup = read('DEDUPLICATION.json')
    protocol = read('SCREENING-PROTOCOL.json'); threshold = read('FROZEN-THRESHOLD.json')
    manual = read('manual_labels.json'); model = {r['id']: r for r in read('sample_model_judgments.json')}
    from phase2_screen import threshold_metrics
    scores = np.load(source/'centroid_scores.npy', allow_pickle=False)
    if len(scores) != len(papers):
        raise ValueError('Score rows differ from candidate rows')
    score = {p['id']: float(s) for p,s in zip(papers,scores)}
    calibration_rows = manual[:protocol['calibration_size']]
    confusion = threshold_metrics([score[r['id']] for r in calibration_rows],
        [r['label'] for r in calibration_rows], threshold['threshold'])
    if any(confusion[k] != threshold['calibration'][k] for k in ('precision','recall','decidable_items')):
        raise ValueError('Calibration recomputation differs from the frozen result')
    threshold = {**threshold, 'calibration_confusion': confusion}
    config = phase2_config()
    queries = read('query_log.json'); seed_meta = read('seed_metadata.json')
    receipts_path = source/'FROZEN-API-COVERAGE.json'
    if receipts_path.exists():
        receipts = json.loads(receipts_path.read_text())
    else:
        receipts = {'s2_snowball': s2_snowball_coverage(seed_meta, collection.get('cache_namespace')),
            'embedding_responses': embedding_response_evidence(protocol['embedding_parameters'], collection.get('cache_namespace'))}
        receipts_path.write_bytes(stable_json(receipts))
    s2_coverage = receipts['s2_snowball']
    queries += s2_coverage
    seed_papers = {s: p for p in papers for s in p['seed_ids']}
    counts = {'snapshot_date': config['cutoff'], 'candidate_observations': collection['candidate_observations'],
        'unique_source_identities': dedup['source_identities'], 'after_dedup': len(papers),
        'prior_seed_identities_retained': sum(len(p.get('source_id_retention', [])) for p in papers),
        'source_identity_links_total': dedup['source_identity_links_total'],
        'included': len(included), 'excluded': sum(d['label'] == 'exclude' for d in decisions),
        'deferred': sum(d['label'] == 'uncertain' for d in decisions),
        'borderline_candidates': sum(d.get('judgment_model') is not None for d in decisions),
        'unresolved_seeds': len(set(seed_meta) - set(seed_papers)),
        'candidate_abstracts_available': sum(p['abstract_available'] for p in papers),
        'abstracts_available': sum(p['abstract_available'] for p in included),
        'candidate_oa_full_text_available': sum(bool(p['open_access_urls']) for p in papers),
        'open_access_full_text_available': sum(bool(p['open_access_urls']) for p in included),
        'full_text_works': sum(p['evidence_level'].replace('_',' ').replace('-',' ') == 'full text' for p in included),
        'full_texts_republished': sum('full_text' in p for p in published_records),
        'abstracts_republished': sum('abstract' in p for p in published_records),
        'resolved_links': len(edges), 'candidate_resolved_links': len(read('resolved_edges.json')),
        'unresolved_citation_observations': dedup['unresolved_citation_observations'],
        'acquisition_gaps': len(read('acquisition_gaps.json')),
        'merge_events': len(read('merge_events.json')), 'suspected_duplicates': len(read('suspected_duplicates.json')),
        'corpus_records': len(included), 'selected_studies': sum(bool(p['seed_ids']) for p in included),
        'evidence_levels': evidence_counts(included),
        'citation_only_placeholders': sum('citation' in p['evidence_level'] for p in included),
        'title_only_embedding_records': sum(not p['abstract_available'] for p in papers),
        'missing_arxiv_v1_dates': len(read('missing_arxiv_v1_dates.json'))}
    counts.update(keyword_queries_attempted=sum(q['kind'] == 'keyword' for q in queries),
        keyword_queries_complete=sum(q['kind'] == 'keyword' and q['complete'] for q in queries),
        s2_snowball_endpoints=len(s2_coverage),
        s2_snowball_endpoints_complete=sum(q['complete'] for q in s2_coverage))
    if counts['included'] + counts['excluded'] + counts['deferred'] != len(papers):
        raise ValueError('Screening labels do not sum to the candidate count')
    quality = {'unresolved_seeds': sorted(set(seed_meta) - set(seed_papers)),
        'alias_review': json.loads((ROOT/'config/seed_review.json').read_text()),
        'prior_seed_identity_retention': [r for p in papers for r in p.get('source_id_retention', [])],
        'seeds_missing_s2': sorted(s for s,p in seed_papers.items() if not p['source_ids'].get('s2')),
        'records_without_abstracts': [p['id'] for p in papers if not p['abstract_available']],
        'single_source_records': [p['id'] for p in papers if sum(bool(v) for v in p['source_ids'].values()) == 1],
        'retracted_records': [p['id'] for p in papers if p['is_retracted']],
        'merges': read('merge_events.json'), 'suspected_duplicates': read('suspected_duplicates.json'),
        'requested_seed_retries': read('requested_retries.json'),
        'missing_arxiv_v1_dates': read('missing_arxiv_v1_dates.json'), 'acquisition_gaps': read('acquisition_gaps.json')}
    sample = [{'id': r['id'], 'sample_index': r['sample_index'], 'title': by_id[r['id']]['title'],
        'split': 'calibration' if i < protocol['calibration_size'] else 'validation',
        'reference_label': r['label'], 'reference_rationale': r['rationale'],
        'model_label': model[r['id']]['label'], 'model_reason': model[r['id']]['reason'],
        'model': model[r['id']]['response_model'], 'response_sha256': model[r['id']]['response_sha256']}
        for i,r in enumerate(manual)]
    input_files = sorted(['candidate_events.json', 'citation_events.json', 'arxiv_dates.json', 'redirects.json',
        'papers.private.json', 'screening_decisions.json', 'resolved_edges.json',
        'COLLECTION.json', 'DEDUPLICATION.json', 'SCREENING-PROTOCOL.json', 'FROZEN-THRESHOLD.json',
        'manual_labels.json', 'sample_model_judgments.json', 'query_log.json', 'seed_metadata.json',
        'merge_events.json', 'suspected_duplicates.json', 'requested_retries.json', 'acquisition_gaps.json',
        'missing_arxiv_v1_dates.json', 'vector_manifest.json', 'vectors.float16.npy', 'centroid_scores.npy', 'FROZEN-API-COVERAGE.json'])
    provenance = {'processing_location': 'private server', 'raw_archive': 'private external archive; not exported',
        'snapshot_id': config['snapshot'],
        'seed_snapshot_sha256': hashlib.sha256((ROOT/'data'/('snapshot-'+config['seed_snapshot'])/'seeds.json').read_bytes()).hexdigest(),
        'source_files_sha256': {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in input_files},
        'config_files_sha256': {name: hashlib.sha256((ROOT/'config'/name).read_bytes()).hexdigest()
            for name in ('config.yaml', 'phase2.yaml', 'seed_review.json', 'seeds.tsv')},
        'sample_models': sorted({r['response_model'] for r in model.values()}),
        'borderline_models': sorted({r['judgment_model'] for r in decisions if r.get('judgment_model')}),
        'embedding_parameters': protocol['embedding_parameters'], 'centroid_seed_documents': read('vector_manifest.json')['centroid_seed_documents']}
    embedding_evidence = receipts['embedding_responses']
    provenance['embedding_last_response_at'] = embedding_evidence[-1]['retrieved_at'] if embedding_evidence else None
    files = {'papers.json': published_records,
        'screening-decisions.json': decisions, 'counts.json': counts, 'edges.json': edges,
        'embedding-responses.json': embedding_evidence,
        'relevance-report.json': threshold, 'screening-protocol.json': protocol, 'sample-labels.json': sample,
        'data-quality.json': quality, 'query-log.json': queries, 'provenance.json': provenance,
        'seed-records.json': [public_paper(p) for p in papers if p['seed_ids']]}
    output.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output/name).write_bytes(stable_json(value))
    for label, name in [('exclude', 'excluded.jsonl'), ('uncertain', 'deferred.jsonl')]:
        rows = [{**d, 'title': by_id[d['id']]['title']} for d in decisions if d['label'] == label]
        (output/name).write_text(''.join(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n' for r in rows))
    (output/'PHASE2-REPORT.md').write_text(render_report(counts, threshold, protocol, queries))
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
                if p.is_file() and p.name != 'FILES.sha256.json'}
    (output/'FILES.sha256.json').write_bytes(stable_json(manifest))
    return counts


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    config = phase2_config()
    destination = args.output or ROOT/'data'/('snapshot-'+config['snapshot'])
    print(json.dumps(build(private_root()/config['snapshot'], destination), sort_keys=True))
