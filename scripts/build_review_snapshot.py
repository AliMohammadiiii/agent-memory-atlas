"""Build a review-only public snapshot from completed private evidence artifacts.

Input artifacts stay private. Atomic replacement prevents changing hardlinked parents.
"""
import argparse, collections, json, os, shutil, sqlite3
from pathlib import Path
from build_pdf_receipt_update import read, write, inventory
from build_site import contains_ipv4


def build(parent, out, private, site_data=None, overrides_path=None):
    assert parent.resolve() != out.resolve()
    before = inventory(parent)
    facets = read(private / 'facets/FACETS.private.json')
    labels = read(private / 'facets/PLAIN-LABELS.private.json')
    stability = read(private / 'stability/STABILITY-REPORT.json')
    matrix_result = read(private / 'matrix-v3/MATRIX.private.json')
    assert matrix_result['summary']['assessed_core_papers'] == matrix_result['summary']['eligible_core_papers']
    if not out.exists():
        shutil.copytree(parent, out, copy_function=os.link)
    manifest = read(parent / 'manifest.json')
    papers = read(parent / 'papers-index.json')
    graph = read(parent / 'graph.json')
    matrix = read(parent / 'matrix.json')
    tags = {r['paper_id']: r for r in facets['rows']}
    assert set(tags) == {p['id'] for p in papers}
    definitions = [{k: f[k] for k in ('id', 'label', 'definition')} | {'size': facets['counts'].get(f['id'], 0)} for f in facets['facets']]
    for paper in papers:
        entries = tags[paper['id']]['tags']
        paper['facet_ids'] = [entry['facet'] for entry in entries]
        paper['facet_primary'] = paper['facet_ids'][0] if entries else 'untagged'
        paper['facet_evidence'] = []
        for entry in entries:
            evidence = entry['evidence']
            quote = evidence['text']
            permitted = entry['display_allowed'] and len(quote.split()) <= 25 and not contains_ipv4(quote)
            paper['facet_evidence'].append({'facet': entry['facet'], 'quote': quote if permitted else None, 'location': evidence['field'], 'model': entry.get('model'), 'source_url': entry.get('source_url')})
    graph['method']['five_seed_stability'] = {'seeds': stability['seeds'], 'pair_count': stability['pair_count'], 'comparison': [{'id': x['id'], 'coverage': x['reference']['coverage'], 'cluster_count': x['reference']['clusters'], 'cluster_sizes': x['reference']['cluster_sizes'], 'mean_all_ari': x['mean_all_ari'], 'mean_joint_ari': x['mean_joint_ari']} for x in stability['comparison']], 'interpretation': stability['interpretation']}
    by_cluster = labels['labels']
    label_evidence = {str(entry['id']): entry for entry in labels['evidence']}
    for cluster in graph['clusters']:
        cluster_id = str(cluster['id'])
        source = label_evidence[cluster_id]
        assert cluster['evidence_titles'][:5] == source['titles'] and len(source['titles']) == 5
        cluster['previous_label'] = cluster['label']
        cluster['label'] = by_cluster[cluster_id]
        cluster['evidence_titles'] = source['titles']
        cluster['evidence_ids'] = cluster['evidence_ids'][:5]
        cluster['top_terms'] = source['top_terms']
        cluster['method'] = 'Model label from five central titles and top terms; exploratory interpretation.'
        cluster['model'] = labels['provenance'].get('model')
        cluster['provenance'] = labels['provenance']
    cluster_names = {str(c['id']): c['label'] for c in graph['clusters']}
    for node in graph['nodes']:
        if str(node.get('cluster_id')) in cluster_names:
            node['cluster_label'] = cluster_names[str(node['cluster_id'])]
    for paper in papers:
        if str(paper.get('cluster_id')) in cluster_names:
            paper['cluster_label'] = cluster_names[str(paper['cluster_id'])]
    for pid, row in matrix_result['rows'].items():
        assert pid in matrix['rows']
        clean = {k: row[k] for k in ('paper_id','source_scope','source_sha256','license_status','validation_status') if k in row}
        clean['cells'] = {}
        for capability, cell in row['cells'].items():
            item = {k: cell[k] for k in ('value','quote','display_allowed','location','reason','source_url','model','verification_model','license_status') if k in cell}
            quote = item.get('quote')
            assert not quote or len(quote.split()) <= 25
            if quote and not item.get('display_allowed'):
                item.update(quote=None, quote_withheld=True, withheld_reason='The exact downloaded-version permission for public quotation is unresolved.')
            clean['cells'][capability] = item
        matrix['rows'][pid] = clean
    overrides = read(overrides_path or Path(__file__).resolve().parents[1]/'config/review-matrix-exclusions.json')
    for exclusion in overrides['exclusions']:
        row = matrix['rows'][exclusion['paper_id']]
        previous = row['cells'][exclusion['capability']]
        assert previous.get('value') in ('yes','partial')
        row['cells'][exclusion['capability']] = {'value':'not stated', 'quote':None, 'display_allowed':False, 'location':None, 'reason':'Manual source review found the extracted evidence insufficient for this capability.', 'manual_review_reason':exclusion['reason']}
    # Legacy abstract cells can contain longer excerpts; withhold them rather
    # than publish a fragment as if it were the complete evidence sentence.
    for row in matrix['rows'].values():
        for cell in row['cells'].values():
            if cell.get('quote') and (len(cell['quote'].split()) > 25 or not cell.get('display_allowed')):
                reason = 'The source sentence exceeds the 25-word display limit.' if len(cell['quote'].split()) > 25 else 'Public display permission is unresolved.'
                cell.update(quote=None, quote_withheld=True, display_allowed=False, withheld_reason=reason)
    all_cells = [cell for row in matrix['rows'].values() for cell in row['cells'].values()]
    groups = collections.defaultdict(collections.Counter)
    for row in matrix['rows'].values():
        for capability, cell in row['cells'].items():
            groups[capability][cell.get('value', 'not stated')] += 1
    coverage = matrix['coverage']
    coverage.update(papers=len(matrix['rows']), cells=len(all_cells), by_capability={k: dict(v) for k,v in sorted(groups.items())}, evidence_cells=sum(c.get('value') in ('yes','partial') for c in all_cells), displayable_evidence_cells=sum(bool(c.get('display_allowed') and c.get('quote')) for c in all_cells), not_stated_cells=sum(c.get('value') == 'not stated' for c in all_cells), source_scope='Abstracts and eligible private PDF excerpts; see each row.')
    matrix['method']['review_fulltext'] = 'Model extraction and a second model check on short raw PDF sentences; manual validation is pending. Not stated does not mean absence.'
    manifest['atlas']['researchFacets'] = definitions
    counts = manifest['counts']
    counts['matrix_fulltext_assessed'] = matrix_result['summary']['assessed_core_papers']
    eligible = {r['paper_id'] for r in read(private/'RIGHTS.private.json') if r.get('private_processing_allowed')}
    index = private.parent/'fulltext-rag-2026-11-02/index.sqlite'
    with sqlite3.connect('file:'+str(index)+'?mode=ro', uri=True) as db:
        indexed = {r[0] for r in db.execute('select paper_id from papers')}
    counts['fulltext_rag_accessible_papers'] = len(eligible & indexed)
    counts['research_facet_untagged'] = facets['untagged']
    manifest['snapshot'].update(id='2026-11-02-research-review', parents=[manifest['snapshot']['id']], method_update='Exploratory research facets, five-seed stability, and privately assessed eligible full-text evidence.')
    manifest['files']['reviewStability'] = 'review-stability.json'
    manifest['limitations'].extend(['Research facets are exploratory model-assisted tags of title and abstract. Spot checks found temporal, scope and governance tags broader than the intended definitions; full validation is pending.', 'Private PDF evaluation covers only records with documented processing permission. Provider licenses matched by URL do not verify downloaded-version identity; their public quotes are withheld.', 'Full-text cells are machine extracted from PDF reading order and independently model checked, not manually validated. Missing evidence is not evidence of absence.'])
    counts['limitations_count'] = len(manifest['limitations'])
    rag = read(parent/'fulltext-rag.json')
    rag.update(matrix_reextracted=True, eligible_private_papers=counts['fulltext_rag_accessible_papers'])
    write(out/'fulltext-rag.json', rag)
    receipt = read(parent/'fulltext-receipt.json')
    receipt['definition'] = 'Private full-text RAG and model-assisted capability extraction are separate; full-text assessment requires recorded private processing permission.'
    receipt['matrix_fulltext_assessed'] = counts['matrix_fulltext_assessed']
    write(out/'fulltext-receipt.json', receipt)
    for name, data in [('papers-index.json',papers),('graph.json',graph),('matrix.json',matrix),('counts.json',counts),('manifest.json',manifest),('review-stability.json',stability)]:
        write(out / name, data)
    diff = read(parent / 'diff.json')
    diff.update(parent=read(parent/'manifest.json')['snapshot']['id'], current=manifest['snapshot']['id'], status='Private research review; not a public release.')
    write(out/'diff.json', diff)
    hashes = inventory(out)
    hashes.pop('FILES.sha256.json', None)
    write(out/'FILES.sha256.json', hashes)
    assert inventory(parent) == before
    if site_data:
        candidate = site_data.with_name('.research-review-next')
        previous = site_data.with_name('.research-review-old')
        if candidate.exists(): shutil.rmtree(candidate)
        if previous.exists(): shutil.rmtree(previous)
        shutil.copytree(out, candidate, copy_function=os.link)
        if site_data.exists(): os.replace(site_data, previous)
        os.replace(candidate, site_data)
        if previous.exists(): shutil.rmtree(previous)
    return {'papers':len(papers), 'facets': facets['counts'], 'matrix_fulltext_assessed': counts['matrix_fulltext_assessed']}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--private',type=Path,required=True)
    parser.add_argument('--site-data',type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.parent,args.out,args.private,args.site_data),sort_keys=True))
