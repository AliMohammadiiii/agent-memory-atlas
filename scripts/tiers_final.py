"""Score-blind three-tier census of every final candidate, including seeds."""
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from final_common import settings, folder, read_json, write_json, digest, source_spans, Model
from server_runtime import private_root


SYSTEM='''Assign every candidate exactly one tier using only the supplied title and abstract spans.
CORE: the main contribution is persistent memory of LLM agents: storage, update, revision, deletion, governance, retrieval or evaluation across interactions.
ADJACENT: persistent agent memory is a substantive component or evaluation axis, or the work is a direct method or theory anchor for that problem.
EXCLUDE: ordinary model pretraining, hardware memory, human memory, generic static-document RAG, generic personalization without persistent memory, and generic GUI/navigation/agent skills without a substantive persistent-memory contribution.
Do not classify a work CORE merely because it uses agents or mentions memory. For ambiguous title-only records conservatively EXCLUDE unless the title explicitly establishes agent-memory scope. A tier is a relevance judgment, never validation of scientific claims. Never infer findings from a title.
Return {"decisions":[{"id":"exact input id","tier":"CORE|ADJACENT|EXCLUDE","reason":"short scope rationale","evidence_span":0,"benchmark_candidate":true}]}. evidence_span selects one supplied zero-based span; null is allowed for EXCLUDE when no scope evidence exists. Do not transcribe quotes. No embedding scores are supplied.'''


def valid_decision(result, paper):
    tier=str(result.get('tier','')).upper()
    if tier not in ('CORE','ADJACENT','EXCLUDE') or not result.get('reason'):return None
    spans=source_spans(paper);index=result.get('evidence_span')
    if index is None and tier=='EXCLUDE':quote=''
    elif isinstance(index,int) and not isinstance(index,bool) and 0<=index<len(spans):quote=spans[index]
    else:quote=''
    # Relevance requires a model tier and rationale, not a quotation. A bad
    # optional pointer must never become invented evidence or discard a valid
    # scope judgment. Capability extraction retains its separate strict gate.
    quote_status='verified_span' if quote else 'not_supplied' if index is None else 'invalid_span_withheld'
    return {**result,'tier':tier,'evidence_quote':quote,'evidence_quote_status':quote_status}


def main():
    f=folder();config=settings();papers=read_json(f/'papers.private.json')
    cache=private_root()/'final-tier-cache';cache.mkdir(exist_ok=True)
    model=Model();results={}
    def key(p):return digest({'title':p['title'],'abstract':p.get('abstract'),'id':p['id'],'system':SYSTEM,
        'definition':config['inclusion_definition'],'model':config['model'],'source_max_chars':config['source_max_chars']})
    missing=[]
    for p in papers:
        path=cache/(key(p)+'.json')
        if path.exists():results[p['id']]=read_json(path)
        else:missing.append(p)
    def batch(rows,attempt=0):
        payload={'frozen_inclusion_definition':config['inclusion_definition'],'papers':[{'id':p['id'],'title':p['title'],
            'abstract_available':bool(p.get('abstract')),'source_spans':source_spans(p)} for p in rows],'repair_iteration':attempt}
        data,meta=model.generate(SYSTEM,payload,max_tokens=6000,tag='final-score-blind-tiers')
        expected={p['id']:p for p in rows};parsed={};invalid=[]
        for r in data.get('decisions',[]):
            if r.get('id') not in expected or r['id'] in parsed:continue
            good=valid_decision(r,expected[r['id']])
            if good:
                item={**good,'provenance':meta,'input_sha256':digest({'title':expected[r['id']]['title'],'abstract':expected[r['id']].get('abstract')})}
                parsed[r['id']]=item;write_json(cache/(key(expected[r['id']])+'.json'),item)
        invalid=[p for p in rows if p['id'] not in parsed]
        if invalid:
            if len(invalid)==1 and attempt>=2:raise RuntimeError('Tier judge failed the required three-tier/evidence schema after retries')
            if len(invalid)==len(rows) and len(rows)>1:
                middle=len(rows)//2;parsed.update(batch(rows[:middle],attempt+1));parsed.update(batch(rows[middle:],attempt+1))
            else:parsed.update(batch(invalid,attempt+1))
        return parsed
    size=config.get('tier_batch_size',24)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(batch,missing[start:start+size]) for start in range(0,len(missing),size)]
        for future in as_completed(futures):
            results.update(future.result())
            write_json(f/'TIER-PROGRESS.json',{'completed':len(results),'total':len(papers)})
            print(json.dumps({'stage':'final_tiers','completed':len(results),'total':len(papers)}),flush=True)
    for p in papers:
        result=results[p['id']];proposed=result['tier'];groups=set(p.get('seed_groups') or [])
        tier='CORE' if groups&set('ABC') else 'ADJACENT' if p.get('seed_ids') else proposed
        p.update(tier=tier,tier_proposed=proposed,tier_reason='Owner seed-group assignment; model proposal retained separately' if p.get('seed_ids') else result['reason'],
            tier_model=result['provenance']['model'],tier_provenance=result['provenance'],tier_origin='owner_seed_rule' if p.get('seed_ids') else 'model_judgment',
            tier_evidence_quote=result['evidence_quote'],tier_evidence_quote_status=result.get('evidence_quote_status','verified_span' if result['evidence_quote'] else 'not_supplied'),benchmark_candidate=result.get('benchmark_candidate',True),
            tier_input_truncated=len(p['title']+'\n\n'+(p.get('abstract') or ''))>config['source_max_chars'])
    if any(p['tier'] not in ('CORE','ADJACENT','EXCLUDE') for p in papers):raise RuntimeError('Incomplete tier census')
    write_json(f/'papers.private.json',papers)
    write_json(f/'TIER-REPORT.json',{'counts':dict(Counter(p['tier'] for p in papers)),'judged_candidates':len(results),
        'seeds_assigned_by_owner':sum(bool(p['seed_ids']) for p in papers),'precision_estimate':'pending owner labels',
        'source_only_definition_sha256':digest(SYSTEM),'models':dict(Counter(p['tier_model'] for p in papers)),
        'input_truncated':sum(p['tier_input_truncated'] for p in papers),'embedding_scores_used_for_decisions':False,
        'optional_scope_quote_status':dict(Counter(p['tier_evidence_quote_status'] for p in papers))})
    parent=private_root()/config['parent_snapshot'];old_papers={p['id']:p for p in read_json(parent/'papers.private.json')}
    redirects=read_json(f/'redirects.json');final_by_id={p['id']:p for p in papers};resolved=[]
    for old in read_json(parent/'screening_decisions.json'):
        if old['label']!='uncertain':continue
        prior=old_papers[old['id']];targets=sorted({redirects[provider+':'+sid] for provider,ids in prior['source_ids'].items() for sid in ids if provider+':'+sid in redirects})
        if not targets:raise RuntimeError('Parent deferred record lost all source identities')
        for pid in targets:resolved.append({'original_id':old['id'],'final_id':pid,'final_tier':final_by_id[pid]['tier']})
    write_json(f/'deferred_resolution.json',{'parent_deferred_count':sum(r['label']=='uncertain' for r in read_json(parent/'screening_decisions.json')),
        'resolved_original_count':len({r['original_id'] for r in resolved}),'resolved':resolved,'unresolved':0})
    print(json.dumps({'stage':'tier_census_complete','counts':dict(Counter(p['tier'] for p in papers))}),flush=True)


if __name__=='__main__':main()
