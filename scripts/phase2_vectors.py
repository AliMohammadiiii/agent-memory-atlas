#!/usr/bin/env python3
"""Server-only embeddings and frozen screening sample. No graph is produced."""
import argparse
import hashlib
import json
import math
import random
import time

import numpy as np
import yaml
from resolve_seeds import ROOT, Cache, raw_root, stable_json
from server_runtime import private_root, inherit_research_credentials, phase2_config


def content_for(paper, parameters):
    text = (paper['title'] + '\n\n' + (paper.get('abstract') or '')).strip()
    cap = parameters['max_document_chars']
    return text[:cap], len(text) > cap


def content_key(text, parameters):
    return hashlib.sha256(stable_json({'text': text, 'model': parameters['model'], 'dimensions': parameters['dimensions'],
        'task': parameters['document_task'], 'normalized': parameters['normalized']})).hexdigest()


def freeze_sample(papers, config, parameters, folder):
    candidates=[p for p in papers if not p.get('seed_ids')]
    if len(candidates)<config['sample_size']:raise RuntimeError('Fewer than 60 non-seed candidates; no reduced sample is silently substituted')
    selected=random.Random(config['sample_random_seed']).sample(candidates,config['sample_size'])
    protocol={'snapshot':config['snapshot'],'cohort_sha256':hashlib.sha256(stable_json([p['id'] for p in papers])).hexdigest(),
        'inclusion_definition':config['inclusion_definition'],'sample_random_seed':config['sample_random_seed'],'sample_size':config['sample_size'],
        'calibration_size':config['calibration_size'],'validation_size':config['validation_size'],'threshold_rule':config['threshold_rule'],
        'borderline_margin':config['borderline_margin'],'labels':['include','exclude','uncertain'],'sample_frame':'all non-seed deduplicated candidates',
        'manual_rater':'machine-generated evidence assessment, not a human gold standard','comparison_rater':config['relevance']['primary_model'],
        'sample_ids':[p['id'] for p in selected], 'embedding_parameters':parameters}
    path=folder/'SCREENING-PROTOCOL.json';content=stable_json(protocol)
    if path.exists() and path.read_bytes()!=content:raise RuntimeError('Frozen screening protocol differs; preserve it and create a new run')
    path.write_bytes(content)
    sample=[]
    for i,paper in enumerate(selected):
        sample.append({'index':i+1,'split':'calibration' if i<config['calibration_size'] else 'validation',
            **{k:paper.get(k) for k in ['id','title','abstract','abstract_provenance','abstract_sha256','evidence_level']}})
    (folder/'screening_sample.private.json').write_bytes(stable_json(sample))
    print(json.dumps({'stage':'screening_sample_frozen_before_vectors','sample_size':len(sample),'candidate_papers':len(papers)}),flush=True)


def main(cache_only=False):
    config = phase2_config(); parameters = yaml.safe_load((ROOT/'config/config.yaml').read_text())['embeddings']
    assert parameters['model'] and parameters['dimensions'] and parameters['document_task'] and parameters['query_task']
    base = private_root(); folder = base/config['snapshot']; papers = json.loads((folder/'papers.private.json').read_text())
    freeze_sample(papers,config,parameters,folder)
    cache = Cache(raw_root(), offline=cache_only); vector_cache = base/'embedding-cache'; vector_cache.mkdir(exist_ok=True)
    manifest=[]; todo=[]
    for paper in papers:
        text,truncated=content_for(paper,parameters); key=content_key(text,parameters); path=vector_cache/(key+'.npy')
        manifest.append({'id':paper['id'],'content_hash':key,'representation':'title_abstract' if paper.get('abstract') else 'title_only','input_truncated':truncated})
        if not path.exists():todo.append((key,text))
    unique = list(dict(todo).items()); computed=0
    for start in range(0,len(unique),parameters['batch_size']):
        batch=unique[start:start+parameters['batch_size']]; started=time.monotonic()
        result=cache.request('jina','/v1/embeddings',{},body={'model':parameters['model'],'dimensions':parameters['dimensions'],
            'task':parameters['document_task'],'normalized':parameters['normalized'],'embedding_type':'float','input':[t for _,t in batch]},attempts=3)
        if result['status'] != 200: raise RuntimeError('Jina embedding batch failed; cached status '+str(result['status']))
        returned=(result.get('data') or {}).get('data') or []
        if len(returned)!=len(batch):raise RuntimeError('Jina response count does not match input count')
        returned=sorted(returned,key=lambda v:v['index'])
        for (key,_),row in zip(batch,returned):
            vector=np.asarray(row['embedding'],dtype=np.float32)
            if vector.shape!=(parameters['dimensions'],) or not np.isfinite(vector).all() or np.linalg.norm(vector)==0:
                raise RuntimeError('Invalid real embedding; no synthetic fallback is allowed')
            vector=vector/np.linalg.norm(vector); np.save(vector_cache/(key+'.npy'),vector.astype(np.float16),allow_pickle=False)
        computed+=len(batch)
        (folder/'EMBEDDING-PROGRESS.json').write_bytes(stable_json({'total_documents':len(papers),'newly_computed':computed,'remaining_uncached':len(unique)-computed,'model':parameters['model']}))
        print(json.dumps({'stage':'embeddings','newly_computed':computed,'uncached_total':len(unique),'model':parameters['model']}),flush=True)
        estimated=sum(len(text) for _,text in batch)/3
        delay=60*estimated/parameters['estimated_tokens_per_minute']-(time.monotonic()-started)
        if delay>0 and start+len(batch)<len(unique):time.sleep(delay)
    matrix=np.stack([np.load(vector_cache/(m['content_hash']+'.npy'),allow_pickle=False) for m in manifest]).astype(np.float32)
    matrix/=np.linalg.norm(matrix,axis=1,keepdims=True)
    mask=np.array([bool(set(p.get('seed_groups') or [])&set(config['seed_groups_for_centroid'])) for p in papers])
    if not mask.any():raise RuntimeError('No resolved A-C seeds available for centroid')
    centroid=matrix[mask].mean(axis=0);centroid/=np.linalg.norm(centroid);scores=matrix@centroid
    np.save(folder/'vectors.float16.npy',matrix.astype(np.float16),allow_pickle=False)
    np.save(folder/'centroid_scores.npy',scores,allow_pickle=False)
    (folder/'vector_manifest.json').write_bytes(stable_json({'parameters':parameters,'documents':manifest,'centroid_seed_documents':int(mask.sum())}))
    print(json.dumps({'stage':'vectors_complete','centroid_seeds':int(mask.sum()),'vectors':len(papers),
        'title_only':sum(not p.get('abstract') for p in papers)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cache-only',action='store_true');args=parser.parse_args()
    inherit_research_credentials();main(args.cache_only)
