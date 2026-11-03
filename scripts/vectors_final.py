"""Cached Jina document vectors and within-corpus citation enrichment, on server."""
import hashlib
import json
import time
import os
import numpy as np
from final_common import folder, settings, read_json, write_json
from phase2_vectors import content_for, content_key
from resolve_seeds import Cache, raw_root
from server_runtime import private_root


def require_cache_hit(reply,offline):
    if offline and reply.get('error')=='cache_miss':
        raise RuntimeError('Frozen snapshot API response is missing from its acquisition cache')


def bind_snapshot_namespace(base,offline):
    recorded=read_json(base/'COLLECTION.json').get('cache_namespace')
    if not recorded:raise RuntimeError('Snapshot acquisition cache namespace is not recorded')
    configured=os.environ.get('ATLAS_CACHE_NAMESPACE')
    if offline and configured and configured!=recorded:
        raise RuntimeError('Offline cache namespace differs from the frozen acquisition snapshot')
    if not configured:os.environ['ATLAS_CACHE_NAMESPACE']=recorded


def main():
    bind_snapshot_namespace(folder(),os.environ.get('ATLAS_CACHE_ONLY')=='1')
    from abstract_permissions import refresh as refresh_permissions
    refresh_permissions()
    from audit_final_inputs import main as audit_inputs
    audit_inputs()
    f=folder();config=settings();parameters=config['embeddings'];all_papers=read_json(f/'papers.private.json')
    papers=[p for p in all_papers if p['tier'] in ('CORE','ADJACENT')]
    cache_dir=private_root()/'embedding-cache';cache_dir.mkdir(exist_ok=True);cache=Cache(raw_root(),offline=os.environ.get('ATLAS_CACHE_ONLY')=='1')
    documents=[];todo={}
    for p in papers:
        text,truncated=content_for(p,parameters);key=content_key(text,parameters)
        documents.append({'id':p['id'],'content_hash':key,'representation':'title_abstract' if p.get('abstract') else 'title_only','input_truncated':truncated})
        if not (cache_dir/(key+'.npy')).exists():todo[key]=text
    rows=list(todo.items());computed=0
    for start in range(0,len(rows),parameters['batch_size']):
        batch=rows[start:start+parameters['batch_size']];begin=time.monotonic()
        reply=cache.request('jina','/v1/embeddings',{},body={'model':parameters['model'],'dimensions':parameters['dimensions'],
            'task':parameters['document_task'],'normalized':True,'embedding_type':'float','input':[text for _,text in batch]},attempts=3)
        if reply['status']!=200:raise PermissionError('Jina document embeddings unavailable: status '+str(reply['status']))
        returned=sorted(reply['data']['data'],key=lambda r:r['index'])
        if len(returned)!=len(batch):raise RuntimeError('Embedding count mismatch')
        for (key,_),row in zip(batch,returned):
            vector=np.asarray(row['embedding'],dtype=np.float32)
            if vector.shape!=(parameters['dimensions'],) or not np.isfinite(vector).all() or not np.linalg.norm(vector):raise RuntimeError('Invalid Jina vector')
            vector/=np.linalg.norm(vector);np.save(cache_dir/(key+'.npy'),vector.astype(np.float16),allow_pickle=False)
        computed+=len(batch);write_json(f/'EMBEDDING-PROGRESS.json',{'completed_new':computed,'new_total':len(rows),'retained':len(papers)})
        print(json.dumps({'stage':'final_embeddings','completed_new':computed,'new_total':len(rows),'retained':len(papers)}),flush=True)
        delay=60*(sum(len(t) for _,t in batch)/3)/parameters['estimated_tokens_per_minute']-(time.monotonic()-begin)
        if delay>0 and start+len(batch)<len(rows):time.sleep(delay)
    matrix=np.vstack([np.load(cache_dir/(r['content_hash']+'.npy'),allow_pickle=False).astype(np.float32) for r in documents])
    matrix/=np.linalg.norm(matrix,axis=1,keepdims=True);np.save(f/'vectors.float16.npy',matrix.astype(np.float16),allow_pickle=False)
    receipt=f/'VECTOR-ACQUISITION.json'
    if not receipt.exists():write_json(receipt,{'new_vectors':len(rows),'reused_vectors':len(documents)-len(rows)})
    write_json(f/'vector_manifest.json',{'parameters':parameters,'documents':documents,**read_json(receipt)})
    retained={p['id'] for p in papers};edges={tuple(e) for e in read_json(f/'resolved_edges.all.json') if e[0] in retained and e[1] in retained}
    redirects=read_json(f/'redirects.json');s2ids=sorted({s for p in papers for s in p['source_ids'].get('s2',[])})
    coverage=[]
    for start in range(0,len(s2ids),50):
        batch=s2ids[start:start+50]
        reply=cache.request('s2','/paper/batch',{'fields':'paperId,referenceCount,references.paperId'},body={'ids':batch},attempts=3)
        require_cache_hit(reply,cache.offline)
        coverage.append({k:reply.get(k) for k in ('status','response_sha256','request_hash','retrieved_at')})
        if reply['status']==200:
            for row in reply.get('data') or []:
                if not row:continue
                a=redirects.get('s2:'+str(row.get('paperId')))
                for ref in row.get('references') or []:
                    b=redirects.get('s2:'+str(ref.get('paperId')))
                    if a in retained and b in retained and a!=b:edges.add((a,b))
        print(json.dumps({'stage':'citation_enrichment','requested':min(start+50,len(s2ids)),'total':len(s2ids),'status':reply['status']}),flush=True)
    context_path=f/'citation_contexts.private.json'
    if context_path.exists():
        from context_citation_edges import merge as merge_context_edges
        merged,context_receipt=merge_context_edges(sorted(edges),all_papers,read_json(context_path))
        edges={tuple(e) for e in merged};write_json(f/'CITATION-CONTEXT-EDGES.json',context_receipt)
    write_json(f/'resolved_edges.json',sorted(edges));write_json(f/'citation_enrichment.json',coverage)
    # Compare tiers with the historical embedding signal only where cached parent scores exist.
    parent=private_root()/config['parent_snapshot'];old=read_json(parent/'papers.private.json');scores=np.load(parent/'centroid_scores.npy',allow_pickle=False)
    tiers={p['id']:p['tier'] for p in all_papers};pairs=[(float(s),tiers[p['id']]) for p,s in zip(old,scores) if p['id'] in tiers]
    signal={'coverage':len(pairs),'candidate_denominator':len(all_papers),'scope':'parent cohort with already-cached embeddings; no extrapolation to newly excluded papers',
        'mean_cosine_by_tier':{tier:float(np.mean([s for s,t in pairs if t==tier])) if any(t==tier for _,t in pairs) else None for tier in ('CORE','ADJACENT','EXCLUDE')}}
    if len({t=='CORE' for _,t in pairs})>1:
        from sklearn.metrics import roc_auc_score
        signal['core_vs_other_auc']=float(roc_auc_score([t=='CORE' for _,t in pairs],[s for s,_ in pairs]))
    write_json(f/'embedding_tier_agreement.json',signal)
    print(json.dumps({'stage':'retained_vectors_complete','records':len(papers),'citation_edges':len(edges)}),flush=True)


if __name__=='__main__':main()
