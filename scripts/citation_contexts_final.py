#!/usr/bin/env python3
"""Bounded seed-only S2 citation snippets; private analysis, version-bound publication gate."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

FIELDS='paperId,title,url,externalIds,contexts,intents,contextsWithIntent,isInfluential'
DOC_URL='https://api.semanticscholar.org/graph/v1/swagger.json'
WITHHELD='Semantic Scholar context does not identify its exact source version or bind that version to a permissive content license. Another version, open-access status, or an abstract license cannot authorize this snippet.'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def provenance(result):
    return {key:result.get(key) for key in ('status','request_hash','response_sha256','retrieved_at')}


def seed_scope(papers):
    mapping={};missing=[]
    for paper in sorted(papers,key=lambda p:p['id']):
        if not paper.get('seed_ids'):continue
        ids=paper.get('source_ids',{}).get('s2') or []
        if not ids:missing.append(paper['id'])
        for sid in ids:
            if sid in mapping and mapping[sid]!=paper['id']:raise ValueError('One seed S2 ID resolves to conflicting canonical papers')
            mapping[sid]=paper['id']
    if len(mapping)>65:raise ValueError('Seed-only scope exceeds the authorized 65 S2 identifiers')
    return dict(sorted(mapping.items())),missing


class Collector:
    def __init__(self,base,papers,request,cap=1000,page_size=100,cache_only=False,existing_edges=None):
        if not 1<=cap<=1000 or not 1<=page_size<=1000:raise ValueError('Citation limits must be between one and 1000')
        self.base=Path(base);self.papers={p['id']:p for p in papers};self.requester=request;self.cap=cap;self.page_size=page_size;self.cache_only=cache_only
        self.scope,self.missing=seed_scope(papers)
        self.citing_map={}
        for paper in papers:
            if paper.get('tier') not in ('CORE','ADJACENT'):continue
            for sid in paper.get('source_ids',{}).get('s2',[]):
                if sid in self.citing_map and self.citing_map[sid]!=paper['id']:raise ValueError('Conflicting retained citing identities')
                self.citing_map[sid]=paper['id']
        self.input_key=digest({'scope':self.scope,'citing_map':self.citing_map,'cap':cap,'page_size':page_size,'fields':FIELDS,'version':1})
        self.cache=self.base/'citation-context-cache'/'processed';self.cache.mkdir(parents=True,exist_ok=True)
        baseline_path=self.base/'citation-context-cache/resolved-edge-baseline.json'
        if baseline_path.exists():baseline=json.loads(baseline_path.read_text())
        else:
            pairs=[]
            for edge in existing_edges or []:
                source,target=(edge.get('source'),edge.get('target')) if isinstance(edge,dict) else edge[:2]
                if source and target:pairs.append((source,target))
            baseline={'edges':sorted(set(pairs)),'comparison_basis':'Resolved citation pairs before seed-context edge enrichment; frozen for later replay.'}
            atomic_json(baseline_path,baseline)
        self.existing_edges={tuple(pair) for pair in baseline['edges']};self.edge_baseline_sha256=digest(baseline)
    def request(self,endpoint,params):
        result=self.requester(endpoint,params)
        if result.get('error')=='cache_miss':raise RuntimeError('Citation-context cache miss; offline mode cannot call the API')
        if result.get('status') in (401,403):raise PermissionError('S2 citation-context access denied; credential/access response remains private')
        return result
    def entry(self,row,sid,offset,row_index,receipt):
        gaps=[];citing=row.get('citingPaper') or {}
        if not isinstance(citing,dict):gaps.append({'field':'citingPaper','reason':'invalid_metadata_schema'});citing={}
        citing_sid=citing.get('paperId') if isinstance(citing.get('paperId'),str) else None;canonical=self.citing_map.get(citing_sid)
        key='canonical:'+canonical if canonical else 's2:'+citing_sid if citing_sid else 'unresolved:'+sid+':'+str(offset)+':'+str(row_index)
        endpoint='/paper/'+quote(sid,safe=':')+'/citations'
        contexts={};observations=0
        def add(text,field,index,intents=None):
            nonlocal observations
            if not isinstance(text,str) or not text.strip():return
            observations+=1;sha=hashlib.sha256(text.encode()).hexdigest()
            location={'field':field,'index':index,'row_index':row_index,'page_offset':offset,'cited_s2_id':sid,'api_endpoint':endpoint}
            context=contexts.setdefault(sha,{'quote':text,'quote_sha256':sha,'display_allowed':False,'withheld_reason':WITHHELD,
                'location':location,'source_locations':[],'provenance':receipt,'intents':[],
                'source_version':None,'content_license':None,'license_binding_status':'not_supplied_by_context_API'})
            context['source_locations'].append({'location':location,'provenance':receipt})
            context['intents']=sorted(set(context['intents'])|{i for i in (intents or []) if isinstance(i,str)})
        raw_contexts=row.get('contexts') or []
        if not isinstance(raw_contexts,list):gaps.append({'field':'contexts','reason':'invalid_context_schema'});raw_contexts=[]
        for index,text in enumerate(raw_contexts):
            if isinstance(text,str):add(text,'contexts',index)
            else:gaps.append({'field':'contexts','index':index,'reason':'invalid_context_schema'})
        paired=row.get('contextsWithIntent') or []
        if not isinstance(paired,list):gaps.append({'field':'contextsWithIntent','reason':'invalid_context_schema'});paired=[]
        for index,pair in enumerate(paired):
            if isinstance(pair,dict) and isinstance(pair.get('context'),str):
                intents=pair.get('intents') or []
                if not isinstance(intents,list):gaps.append({'field':'contextsWithIntent.intents','index':index,'reason':'invalid_intent_schema'});intents=[]
                add(pair['context'],'contextsWithIntent.context',index,intents)
            else:gaps.append({'field':'contextsWithIntent','index':index,'reason':'invalid_context_schema'})
        citation_intents=row.get('intents') or []
        if not isinstance(citation_intents,list):gaps.append({'field':'intents','reason':'invalid_intent_schema'});citation_intents=[]
        influential=row.get('isInfluential') if isinstance(row.get('isInfluential'),bool) else None
        return {'_key':key,'citing_id':canonical,'citing_s2_ids':[citing_sid] if citing_sid else [],'cited_s2_ids':[sid],
            'citing_title':citing.get('title'),'source_url':citing.get('url') or ('https://www.semanticscholar.org/paper/'+citing_sid if citing_sid else None),
            'contexts':list(contexts.values()),'context_observations':observations,
            'intents':sorted({i for i in citation_intents if isinstance(i,str)}),'gaps':gaps,'isInfluential':influential,
            'influential_observations':[{'cited_s2_id':sid,'value':influential,'provenance':receipt}], 'provenance':[receipt]}
    def acquire(self,sid):
        cache_path=self.cache/(digest({'input':self.input_key,'seed_s2_id':sid})+'.json')
        if cache_path.exists():return json.loads(cache_path.read_text())
        endpoint='/paper/'+quote(sid,safe=':');gaps=[];citations=[];receipts=[]
        metadata=self.request(endpoint,{'fields':'citationCount'})
        reported=(metadata.get('data') or {}).get('citationCount') if isinstance(metadata.get('data'),dict) else None
        if isinstance(reported,bool) or not isinstance(reported,int):reported=None
        if metadata.get('status')!=200:gaps.append({'stage':'reported_count','status':metadata.get('status'),'provenance':provenance(metadata)})
        offset=0;acquired=pages=returned_rows=0;complete=capped=False;last_status=metadata.get('status')
        while acquired<self.cap:
            params={'fields':FIELDS,'offset':offset,'limit':min(self.page_size,self.cap-acquired)}
            result=self.request(endpoint+'/citations',params);last_status=result.get('status');receipt=provenance(result);receipts.append(receipt)
            if last_status!=200 or not isinstance(result.get('data'),dict):
                gaps.append({'stage':'citations','offset':offset,'status':last_status,'provenance':receipt});break
            data=result['data'];rows=data.get('data')
            if not isinstance(rows,list):gaps.append({'stage':'citations','offset':offset,'status':200,'reason':'invalid_data_schema','provenance':receipt});break
            pages+=1;returned_rows+=len(rows)
            if len(rows)>params['limit']:gaps.append({'stage':'citations','offset':offset,'reason':'API_returned_more_than_requested_limit','omitted_rows':len(rows)-params['limit'],'provenance':receipt})
            for row_index,row in enumerate(rows[:params['limit']]):
                if not isinstance(row,dict):gaps.append({'stage':'citation_row','offset':offset,'row_index':row_index,'reason':'invalid_row_schema','provenance':receipt});continue
                citations.append(self.entry(row,sid,offset,row_index,receipt))
            acquired+=min(len(rows),params['limit']);nxt=data.get('next')
            if nxt is None:complete=True;break
            if acquired>=self.cap:capped=True;break
            if not rows or isinstance(nxt,bool) or not isinstance(nxt,int) or nxt<=offset:
                gaps.append({'stage':'pagination','offset':offset,'reason':'empty_or_nonadvancing_next','provenance':receipt});break
            offset=nxt
        if acquired>=self.cap and (not complete or (reported is not None and reported>acquired)):capped=True
        status='unavailable' if not pages else 'partial' if gaps or not complete and not capped else 'capped' if capped else 'complete'
        acquisition={'s2_id':sid,'reported_total':reported,'reported_total_basis':'S2 paper.citationCount, retrieved separately from citation pagination',
            'reported_total_provenance':provenance(metadata),'acquired':acquired,'returned_rows':returned_rows,'pages':pages,'status':status,
            'complete':complete,'capped':capped,'cap':self.cap,'last_status':last_status,'gaps':gaps,'provenance':receipts}
        output={'acquisition':acquisition,'citations':citations};atomic_json(cache_path,output);return output
    def run(self):
        result={pid:{'paper_id':pid,'title':self.papers[pid].get('title'),'seed_s2_ids':[],'acquisitions':[],'citations':[],'gaps':[]} for pid in sorted(set(self.scope.values())|set(self.missing))}
        for pid in self.missing:result[pid]['gaps'].append({'reason':'seed_has_no_resolved_S2_identifier','status':'unavailable'})
        merged={pid:{} for pid in result}
        for index,(sid,pid) in enumerate(self.scope.items()):
            output=self.acquire(sid);result[pid]['seed_s2_ids'].append(sid);result[pid]['acquisitions'].append(output['acquisition'])
            for row in output['citations']:
                key=row['_key'];current=merged[pid].get(key)
                if current is None:merged[pid][key]=json.loads(json.dumps(row));continue
                current['citing_s2_ids']=sorted(set(current['citing_s2_ids']+row['citing_s2_ids']));current['cited_s2_ids']=sorted(set(current['cited_s2_ids']+row['cited_s2_ids']))
                current['intents']=sorted(set(current['intents']+row['intents']));current['provenance']+=row['provenance'];current['context_observations']+=row['context_observations'];current['gaps']+=row['gaps']
                current['influential_observations']+=row['influential_observations']
                flags=[x['value'] for x in current['influential_observations'] if x['value'] is not None];current['isInfluential']=any(flags) if flags else None
                contexts={c['quote_sha256']:c for c in current['contexts']}
                for context in row['contexts']:
                    existing=contexts.get(context['quote_sha256'])
                    if existing:existing['source_locations']+=context['source_locations'];existing['intents']=sorted(set(existing['intents']+context['intents']))
                    else:contexts[context['quote_sha256']]=context
                current['contexts']=list(contexts.values())
            progress={'stage':'seed_citation_contexts','completed_s2_ids':index+1,'total_s2_ids':len(self.scope),'status':output['acquisition']['status']}
            atomic_json(self.base/'CITATION-CONTEXT-PROGRESS.json',progress);print(json.dumps(progress),flush=True)
        for pid,paper in result.items():
            for key,row in sorted(merged[pid].items()):
                row.pop('_key',None);row['contexts'].sort(key=lambda c:c['quote_sha256']);row['context_count']=len(row['contexts']);paper['citations'].append(row)
            paper['context_count']=sum(row['context_count'] for row in paper['citations']);paper['citation_count']=len(paper['citations'])
        acquisitions=[a for p in result.values() for a in p['acquisitions']];citations=[c for p in result.values() for c in p['citations']]
        documentation=self.base/'citation-context-cache/docs/receipt.json'
        retained={pid for pid,paper in self.papers.items() if paper.get('tier') in ('CORE','ADJACENT')}
        resolved_edges={(citing['citing_id'],pid) for pid,paper in result.items() if pid in retained for citing in paper['citations'] if citing['citing_id'] in retained and citing['citing_id']!=pid}
        coverage={'resolved_citation_edges':len(resolved_edges),'resolved_citation_edges_already_present':len(resolved_edges & self.existing_edges),
            'new_resolved_citation_edges':len(resolved_edges-self.existing_edges),'seed_works':len(result),'resolved_seed_s2_ids':len(self.scope),'seeds_without_s2_id':len(self.missing),'acquired_citation_rows':sum(a['acquired'] for a in acquisitions),
            'unique_seed_citing_pairs':len(citations),'linked_retained_citing_pairs':sum(c['citing_id'] is not None for c in citations),
            'contexts':sum(len(c['contexts']) for c in citations),'displayable_contexts':0,'acquisition_statuses':dict(Counter(a['status'] for a in acquisitions)),
            'capped_seed_s2_ids':sum(a['capped'] for a in acquisitions),'gap_count':len(self.missing)+sum(len(a['gaps']) for a in acquisitions)+sum(len(c['gaps']) for c in citations)}
        return {'papers':result,'resolved_citation_edges':[list(pair) for pair in sorted(resolved_edges)],'coverage':coverage,'method':{'scope':'Resolved S2 identifiers of owner seeds only; no new papers or corpus changes.',
            'cap_per_seed_s2_id':self.cap,'page_size':self.page_size,'fields':FIELDS,'source_documentation':DOC_URL,
            'source_documentation_receipt':json.loads(documentation.read_text()) if documentation.exists() else None,
            'source_input_sha256':self.input_key,'resolved_edge_baseline_sha256':self.edge_baseline_sha256,
            'edge_identity_rule':'Exact retained S2 source-ID to canonical-ID map only; unique directed citing-to-seed pairs, no new nodes or identity guesses. New-edge counts compare the frozen pre-context baseline.',
            'citation_order':'S2 default API ordering with sequential offset pages; capped rows are not a representative random sample.','license_policy':WITHHELD,'citing_id_scope':'Retained CORE or ADJACENT canonical corpus IDs only.',
            'annotations':'Intents and influential flags are S2 API annotations, not independently verified findings. Per-context intents come only from exact contextsWithIntent matches.',
            'influential_merge':'Any true among retained source-ID observations; all original observations retained.',
            'quote_deduplication':'Exact UTF-8 text SHA256 within canonical cited/citing pair; original locations and receipts retained.'}}


def main(cache_only=False,credentials_pid=None):
    from final_common import folder,read_json,write_json
    from resolve_seeds import Cache
    offline=cache_only or os.environ.get('ATLAS_CACHE_ONLY')=='1'
    if credentials_pid is not None and not offline and not os.environ.get('S2_API_KEY'):
        environment=dict(item.split(b'=',1) for item in Path('/proc').joinpath(str(credentials_pid),'environ').read_bytes().split(b'\0') if b'=' in item)
        if environment.get(b'S2_API_KEY'):os.environ['S2_API_KEY']=environment[b'S2_API_KEY'].decode()
    if not offline and not os.environ.get('S2_API_KEY'):raise RuntimeError('S2_API_KEY is required in the online process environment; no credential value is logged or persisted')
    base=folder();papers=read_json(base/'papers.private.json')
    os.environ.setdefault('ATLAS_S2_INTERVAL_SECONDS','2.5')
    cache=Cache(base/'citation-context-cache/raw',offline=offline,retry_errors=not offline)
    request=lambda endpoint,params:cache.request('s2',endpoint,params,attempts=4)
    existing=read_json(base/'resolved_edges.json') if (base/'resolved_edges.json').exists() else []
    output=Collector(base,papers,request,cache_only=offline,existing_edges=existing).run()
    write_json(base/'citation_contexts.private.json',output)
    print(json.dumps({'stage':'seed_citation_contexts_complete','coverage':output['coverage']}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cache-only',action='store_true');parser.add_argument('--credentials-pid',type=int);args=parser.parse_args();main(args.cache_only,args.credentials_pid)
