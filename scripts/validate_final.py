"""Audit actual final evidence and exported data; runs on the private server."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def validate(private,public):
    papers=load(private/'papers.private.json');by_id={p['id']:p for p in papers}
    assert len(by_id)==len(papers),'Duplicate canonical paper ids'
    tiers=Counter(p.get('tier') for p in papers)
    assert set(tiers)<={'CORE','ADJACENT','EXCLUDE'},'Unresolved tier'
    assert all(p.get('tier_reason') and p.get('tier_model') for p in papers),'Missing tier judgment provenance'
    assert all(not p.get('abstract_display_allowed') or any(r.get('matches_selected_abstract') for r in p.get('content_license_observations',[])) for p in papers),'Abstract permission not bound to selected source text'
    kept={p['id'] for p in papers if p['tier']!='EXCLUDE'}
    manifest=load(private/'vector_manifest.json')
    assert {r['id'] for r in manifest['documents']}==kept,'Vector coverage differs from retained corpus'
    import numpy as np
    vectors=np.load(private/'vectors.float16.npy',allow_pickle=False)
    assert vectors.shape==(len(kept),manifest['parameters']['dimensions'])
    assert vectors.dtype==np.float16 and np.isfinite(vectors).all()
    assert np.all(np.abs(np.linalg.norm(vectors.astype(np.float32),axis=1)-1)<.005)
    edges=load(private/'resolved_edges.json')
    assert len({tuple(e) for e in edges})==len(edges),'Duplicate citations'
    assert all(a in kept and b in kept and a!=b for a,b in edges),'Unresolved citation endpoint'
    matrix=load(private/'matrix.private.json');rows=matrix['rows']
    core={p['id'] for p in papers if p['tier']=='CORE'}
    assert set(rows)==core,'Matrix must cover every CORE paper'
    columns={c['id'] for c in matrix['columns']};quoted=0
    for ident,row in rows.items():
        assert set(row['cells'])==columns,'Capability column mismatch'
        for cell in row['cells'].values():
            assert cell['value'] in ('yes','partial','not stated')
            assert cell.get('model') or not by_id[ident].get('abstract'),'Missing extraction model for an available abstract'
            if cell['value']=='not stated':continue
            quote=cell.get('quote');location=cell.get('location') or {}
            source=by_id[ident].get(location.get('field')) or ''
            assert quote and source[location['char_start']:location['char_end']]==quote,'Evidence quote/offset mismatch'
            assert not cell.get('display_allowed') or by_id[ident].get('abstract_display_allowed'),'Invalid quote publication permission'
            quoted+=1
    index=load(public/'papers-index.json');ids={p['id'] for p in index}
    assert ids==kept and len(ids)==len(index),'Public corpus mismatch'
    counts=load(public/'counts.json')
    for tier in ('CORE','ADJACENT','EXCLUDE'):
        assert counts[tier.lower()]==tiers[tier],'Tier count mismatch'
    assert counts['default_core_plus_seeds']==sum(p['tier']=='CORE' or p.get('is_seed') or bool(p.get('seed_ids')) for p in papers if p['tier']!='EXCLUDE')
    graph=load(public/'graph.json')
    assert {n['id'] for n in graph['nodes']}==kept
    assert all(e['source'] in kept and e['target'] in kept for e in graph['edges'])
    pub_matrix=load(public/'matrix.json')
    for ident,row in pub_matrix['rows'].items():
        for cap,cell in row['cells'].items():
            original=rows[ident]['cells'][cap]
            assert cell['value']==original['value'],'Withheld evidence changed capability state'
            if cell.get('quote'):assert original.get('display_allowed') and cell['quote']==original['quote']
    details=0
    for path in sorted((public/'details').glob('*.json')):
        for ident,row in load(path).items():
            details+=1
            if row.get('abstract'):
                assert by_id[ident].get('abstract_display_allowed') and row['abstract']==by_id[ident].get('abstract')
    assert details==len(kept),'Missing details'
    deferred=load(private/'deferred_resolution.json')
    if isinstance(deferred,dict):deferred=deferred.get('resolved',deferred.get('records',deferred.get('items',[])))
    assert len({r['original_id'] for r in deferred})==170,'Deferred mapping denominator changed'
    assert all(r.get('final_id') in by_id and r.get('final_tier')==by_id[r['final_id']]['tier'] for r in deferred)
    return {'status':'passed','candidates':len(papers),'tiers':dict(tiers),'vector_rows':len(vectors),'citation_edges':len(edges),'matrix_rows':len(rows),'matrix_cells':len(rows)*len(columns),'exact_quote_cells':quoted,'public_details':details,'deferred_resolved':len({r['original_id'] for r in deferred}),'deferred_mapping_rows':len(deferred),'public_files_sha256':{str(p.relative_to(public)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(public.rglob('*')) if p.is_file()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--private',required=True,type=Path);parser.add_argument('--public',required=True,type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=validate(args.private,args.public)
    if args.out:args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='public_files_sha256'},sort_keys=True))
