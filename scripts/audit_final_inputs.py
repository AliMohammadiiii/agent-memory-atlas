"""Post-acquisition receipts and deferred mapping; never changes judgments."""
from final_common import settings, folder, read_json, write_json
from server_runtime import private_root


def main():
    f=folder();cfg=settings();parent=private_root()/cfg['parent_snapshot']
    queries=read_json(f/'query_log.json');old_queries=read_json(parent/'query_log.json');events=read_json(f/'candidate_events.json')
    comparison=[]
    for query in cfg['original_queries']:
        old=next((q for q in old_queries if q['provider']=='s2' and q.get('kind')=='keyword' and q['query']==query),{})
        new=next(q for q in queries if q['provider']=='s2' and q['query']==query)
        comparison.append({'query':query,'bulk_reported':old.get('reported_total'),'bulk_received':old.get('received',0),
            'relevance_reported':new['reported_total'],'relevance_received':new['received'],'relevance_capped':new['capped'],'complete':new['complete']})
    current={r['source_id'] for r in events if r['provider']=='s2' and r['discovery'].get('method')=='keyword_relevance_final'}
    prior={r['source_id'] for r in read_json(parent/'candidate_events.json') if r['provider']=='s2'}
    write_json(f/'s2_fix_report.json',{'method':'Graph relevance search /paper/search; up to1000 ranked results/query; paired comparison against archived plain bulk search',
        'comparison':comparison,'original_bulk_received':sum(r['bulk_received'] for r in comparison),
        'corrected_original_queries_received':sum(r['relevance_received'] for r in comparison),
        'all_s2_keywords_received':sum(q['received'] for q in queries if q['provider']=='s2'),
        'unique_s2_keyword_ids':len(current),'new_s2_keyword_ids_vs_parent':len(current-prior)})
    papers=read_json(f/'papers.private.json');by_id={p['id']:p for p in papers};redirects=read_json(f/'redirects.json')
    original={p['id']:p for p in read_json(parent/'papers.private.json')};rows=[];deferred=[r for r in read_json(parent/'screening_decisions.json') if r['label']=='uncertain']
    for d in deferred:
        p=original[d['id']];targets=sorted({redirects[provider+':'+sid] for provider,ids in p['source_ids'].items() for sid in ids if provider+':'+sid in redirects})
        if not targets:raise RuntimeError('Deferred record lost its source identity')
        for pid in targets:
            if by_id[pid].get('tier') not in ('CORE','ADJACENT','EXCLUDE'):raise RuntimeError('A deferred record has no final tier')
            rows.append({'original_id':d['id'],'final_id':pid,'final_tier':by_id[pid]['tier']})
    write_json(f/'deferred_resolution.json',{'parent_deferred_count':len(deferred),'resolved_original_count':len({r['original_id'] for r in rows}),
        'resolved':rows,'unresolved':0})


if __name__=='__main__':main()
