"""Corrected acquisition into a new snapshot, never the approved parents."""
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from urllib.parse import unquote

from final_common import settings, folder, read_json, write_json, digest
from phase2_collect import Collector, envelope, OA_FIELDS, S2_FIELDS
from resolve_seeds import ROOT, Cache, raw_root, now, normalized
from server_runtime import private_root
import phase2_merge


class FinalCollector(Collector):
    def __init__(self):
        self.config=settings();self.folder=folder();self.parent=private_root()/self.config['parent_snapshot']
        self.cache=Cache(raw_root(),offline=os.environ.get('ATLAS_CACHE_ONLY')=='1');self.first_retry=[]
        resume=(self.folder/'candidate_events.json').exists()
        base=self.folder if resume else self.parent
        self.events=read_json(base/'candidate_events.json');self.edges=read_json(base/'citation_events.json')
        self.seed_metadata=read_json(self.parent/'seed_metadata.json');self.arxiv=read_json(base/'arxiv_dates.json')
        self.queries=read_json(self.folder/'query_log.json') if resume else []
        self.gaps=read_json(self.folder/'acquisition_gaps.json') if resume else []
        self.seed_rows=read_json(ROOT/'data'/('snapshot-'+self.config['seed_snapshot'])/'seeds.json')['seeds']
        self.config['api']['transient_attempts']=3
        self.keyword_recovery=os.environ.get('ATLAS_RECOVER_KEYWORDS')=='1' and not self.cache.offline
        if self.keyword_recovery:
            self.cache.retry_errors=True
            self.config['api']['transient_attempts']=6
            interrupted=[q for q in self.queries if q['provider']=='s2' and q.get('last_status') in (0,429,500,502,503,504)]
            receipt=self.folder/'keyword_recovery_before.json'
            if not receipt.exists():write_json(receipt,interrupted)
            self.queries=[q for q in self.queries if q not in interrupted]

    def request(self, provider, endpoint, params, **kwargs):
        result=super().request(provider,endpoint,params,**kwargs)
        if provider in ('s2','openalex','jina') and result['status'] in (401,403):
            raise PermissionError(provider+' rejected the server credential or access policy; response retained privately')
        return result

    def checkpoint(self, stage):
        for name,value in [('candidate_events.json',self.events),('citation_events.json',self.edges),
            ('query_log.json',self.queries),('arxiv_dates.json',self.arxiv),('seed_metadata.json',self.seed_metadata),
            ('acquisition_gaps.json',self.gaps)]:write_json(self.folder/name,value)
        write_json(self.folder/'COLLECTION.json',{'snapshot':self.config['snapshot'],'stage':stage,
            'candidate_observations':len(self.events),'citation_observations':len(self.edges),
            'cache_namespace':self.cache.namespace,'queries':len(self.queries),'checkpoint_at':now()})

    def ingest(self, provider, endpoint, result, discovery):
        data=result.get('data') or {}
        if result['status']!=200:return
        if provider=='openalex':
            rows=data.get('results') if isinstance(data,dict) and 'results' in data else [data]
            for row in rows:self.add(row,provider,result,discovery)
        elif provider=='s2':
            match=re.search(r'/paper/([^/]+)/(references|citations)',endpoint)
            rows=data.get('data') if 'data' in data else [data]
            for entry in rows or []:
                paper=entry.get('citedPaper' if match and match[2]=='references' else 'citingPaper') if match else entry
                record=self.add(paper or {},provider,result,discovery)
                if match and record:
                    source,target=(unquote(match[1]),record['source_id']) if match[2]=='references' else (record['source_id'],unquote(match[1]))
                    self.edges.append({'provider':'s2','source':source,'target':target,'provenance':envelope(result),
                        'contexts':entry.get('contexts') or [],'is_influential':entry.get('isInfluential')})

    def retry_gaps(self):
        path=self.folder/'gap_retries.json';rows=read_json(path) if path.exists() else []
        done={x['parent_request_hash'] for x in rows}
        for gap in read_json(self.parent/'acquisition_gaps.json'):
            if gap['request_hash'] in done:continue
            result=self.cache.request(gap['provider'],gap['endpoint'],gap['parameters'],attempts=1)
            if result['status'] in (401,403):raise PermissionError(gap['provider']+' credential/access rejected on gap retry')
            lookup=gap['endpoint'].split('/paper/')[-1].split('/')[0]
            seed=next((s for s,m in self.seed_metadata.items() if m.get('s2_paper_id')==lookup),None)
            self.ingest(gap['provider'],gap['endpoint'],result,{'method':'seed' if seed and '/references' not in gap['endpoint'] and '/citations' not in gap['endpoint'] else 'gap_retry','seed_id':seed})
            rows.append({'parent_request_hash':gap['request_hash'],'provider':gap['provider'],'endpoint':gap['endpoint'],
                         'prior_status':gap['status'],**envelope(result)})
            write_json(path,rows);self.checkpoint('gap_retries')
            print(json.dumps({'stage':'gap_retry','completed':len(rows),'total':29,'status':result['status']}),flush=True)

    def keyword_queries(self):
        for query in self.config['queries']:
            if not any(q['provider']=='openalex' and q['query']==query for q in self.queries):
                details=self.pages_oa({'filter':'title_and_abstract.search:'+query+',from_publication_date:2023-01-01,to_publication_date:'+self.config['cutoff']},
                                      {'method':'keyword_final','query':query})
                self.queries.append({'provider':'openalex','kind':'keyword','query':query,'search_fields':'title_and_abstract',**details})
                self.checkpoint('keywords')
            if not any(q['provider']=='s2' and q['query']==query for q in self.queries):
                received=0;pages=0;total=None;offset=0;complete=False;last_status=None
                while offset<self.config['api']['s2_query_limit']:
                    params={'query':query,'year':'2023:'+self.config['cutoff'][:4],'offset':offset,'limit':100,'fields':S2_FIELDS}
                    result=self.request('s2','/paper/search',params);last_status=result['status']
                    if result['status']!=200:break
                    data=result.get('data') or {};total=data.get('total',total);rows=data.get('data') or [];pages+=1
                    for row in rows:
                        if not row.get('publicationDate') or row['publicationDate']<=self.config['cutoff']:
                            self.add(row,'s2',result,{'method':'keyword_relevance_final','query':query})
                    received+=len(rows)
                    nxt=data.get('next')
                    if not rows or nxt is None:complete=True;break
                    offset=int(nxt)
                self.queries.append({'provider':'s2','kind':'keyword','query':query,'method':'relevance_search',
                    'reported_total':total,'received':received,'pages':pages,'limit':1000,
                    'complete':complete,'capped':not complete and received>=1000,'last_status':last_status})
                self.checkpoint('keywords')
            print(json.dumps({'stage':'final_keywords','completed':len(self.queries),'total':len(self.config['queries'])*2,'observations':len(self.events)}),flush=True)

    def dates_new(self):
        ids=sorted({r['arxiv_id'] for r in self.events if r.get('arxiv_id')}-set(self.arxiv))
        for start in range(0,len(ids),100):
            batch=ids[start:start+100]
            result=self.request('arxiv','/api/query',{'id_list':','.join(batch),'max_results':100})
            if result['status']==200 and result.get('response_sha256'):
                root=ET.fromstring((raw_root()/'responses'/(result['response_sha256']+'.body')).read_bytes())
                for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                    match=re.search(r'(\d{4}\.\d{4,5})(?:v\d+)?$',entry.findtext('{http://www.w3.org/2005/Atom}id') or '')
                    if match:self.arxiv[match[1]]={'first_public_date':entry.findtext('{http://www.w3.org/2005/Atom}published'),'provenance':envelope(result)}
            self.checkpoint('dates')
            print(json.dumps({'stage':'final_arxiv_dates','requested':min(start+100,len(ids)),'new_ids':len(ids)}),flush=True)

    def run(self):
        state=self.folder/'COLLECTION.json'
        if state.exists() and read_json(state)['stage']=='complete' and not self.keyword_recovery:return
        self.retry_gaps();self.keyword_queries();self.dates_new()
        for record in self.events:
            if record['provider']=='openalex':
                for target in record.get('references',[]):self.edges.append({'provider':'openalex','source':record['source_id'],'target':target,'provenance':record['provenance']})
        self.checkpoint('complete')
        parent_queries=read_json(self.parent/'query_log.json');new_s2=[q for q in self.queries if q['provider']=='s2']
        comparison=[]
        for query in self.config['original_queries']:
            old=next((q for q in parent_queries if q['provider']=='s2' and q['kind']=='keyword' and q['query']==query),{})
            new=next(q for q in new_s2 if q['query']==query)
            comparison.append({'query':query,'bulk_reported':old.get('reported_total'),'bulk_received':old.get('received',0),
                'relevance_reported':new['reported_total'],'relevance_received':new['received'],'relevance_capped':new['capped'],'complete':new['complete']})
        discovered={r['source_id'] for r in self.events if r['provider']=='s2' and r['discovery'].get('method')=='keyword_relevance_final'}
        parent_ids={r['source_id'] for r in read_json(self.parent/'candidate_events.json') if r['provider']=='s2'}
        write_json(self.folder/'s2_fix_report.json',{'method':'Graph relevance search /paper/search; plain queries ranked, up to 1000 per query',
            'comparison':comparison,'original_bulk_received':sum(x['bulk_received'] for x in comparison),
            'corrected_original_queries_received':sum(x['relevance_received'] for x in comparison),'all_s2_keywords_received':sum(q['received'] for q in new_s2),
            'unique_s2_keyword_ids':len(discovered),'new_s2_keyword_ids_vs_parent':len(discovered-parent_ids)})


def enhanced_dedup(events):
    observations=defaultdict(list)
    for r in events:observations[r['provider']+':'+r['source_id']].append(r)
    records={key:max(rows,key=lambda r:(bool(r.get('abstract')),bool(r.get('venue')),r.get('provenance',{}).get('retrieved_at') or '',len(r.get('abstract') or ''))) for key,rows in observations.items()}
    merges=[]
    parent={key:key for key in records}
    def find(k):
        while parent[k]!=k:parent[k]=parent[parent[k]];k=parent[k]
        return k
    def join(a,b,reason):
        x,y=find(a),find(b)
        if x!=y:parent[max(x,y)]=min(x,y);merges.append({'left':a,'right':b,'reason':reason})
    for field in ('doi','arxiv_id'):
        index={}
        for key,r in sorted(records.items()):
            for value in [r.get(field)]+(r.get('linked_dois') or [] if field=='doi' else []):
                if not value:continue
                if value in index:join(key,index[value],'shared_'+field)
                else:index[value]=key
    family=[key for key,r in records.items() if (r.get('discovery') or {}).get('seed_id')=='F02']
    for key in sorted(family)[1:]:join(key,sorted(family)[0],'owner_authorized_F02_version_family')
    triples={}
    for key,r in sorted(records.items()):
        authors=r.get('authors') or [];name=normalized(authors[0].get('name')) if authors else ''
        title=normalized(r['title']);year=r.get('year')
        if not name or not title or year is None:continue
        triple=(title,name,year)
        if triple in triples:join(key,triples[triple],'normalized_title_first_author_year')
        else:triples[triple]=key
    result=defaultdict(list)
    for key in records:result[find(key)].append(key)
    global DUPLICATE_AUDIT
    DUPLICATE_AUDIT=[]
    parent_pairs=read_json(private_root()/settings()['parent_snapshot']/'suspected_duplicates.json')
    for pair in parent_pairs:
        a,b=pair['left'],pair['right'];decision='merge' if a in parent and b in parent and find(a)==find(b) else 'keep_separate'
        reason='shared_identifier_or_exact_title_first_author_year' if decision=='merge' else 'no_decisive_shared_identifier_or_exact_title_first_author_year'
        DUPLICATE_AUDIT.append({**pair,'decision':decision,'final_reason':reason,'needs_review':decision=='keep_separate'})
    return records,observations,[sorted(v) for _,v in sorted(result.items())],merges,[r for r in DUPLICATE_AUDIT if r['needs_review']]


ORIGINAL_DEDUP=phase2_merge.deduplicate
DUPLICATE_AUDIT=[]


def build_final_papers():
    f=folder();events=read_json(f/'candidate_events.json');dates=read_json(f/'arxiv_dates.json');seeds=read_json(f/'seed_metadata.json')
    for h in {r['provenance']['response_sha256'] for r in dates.values() if r.get('provenance')}:
        doc=ET.fromstring((raw_root()/'responses'/(h+'.body')).read_bytes())
        for e in doc.findall('{http://www.w3.org/2005/Atom}entry'):
            m=re.search(r'(\d{4}\.\d{4,5})(?:v\d+)?$',e.findtext('{http://www.w3.org/2005/Atom}id') or '')
            if m and m[1] in dates:dates[m[1]]['related_dois']=[d.rstrip(';,').lower() for d in re.findall(r'10\.\d{4,9}/\S+',e.findtext('{http://arxiv.org/schemas/atom}doi') or '')]
    for r in events:
        if r.get('arxiv_id') in dates:r['linked_dois']=dates[r['arxiv_id']].get('related_dois') or []
    phase2_merge.deduplicate=enhanced_dedup
    try:papers,redirects,merges,suspicious,missing=phase2_merge.build_papers(events,seeds,dates)
    finally:phase2_merge.deduplicate=ORIGINAL_DEDUP
    phase2_merge.retain_prior_seed_ids(papers,read_json(ROOT/'data'/('snapshot-'+settings()['seed_snapshot'])/'seeds.json')['seeds'])
    observations=defaultdict(list)
    for r in events:observations[r['provider']+':'+r['source_id']].append(r)
    for p in papers:
        license_evidence=[]
        for provider,ids in p['source_ids'].items():
            for identifier in ids:
                redirects[provider+':'+identifier]=p['id']
                for row in observations[provider+':'+identifier]:
                    for license_id in row.get('content_license_observations') or []:
                        license_evidence.append({'license':license_id,'source_id':identifier,'provenance':row['provenance'],
                            'matches_selected_abstract':bool(p.get('abstract')) and row.get('abstract')==p.get('abstract')})
        allowed=[r for r in license_evidence if r['matches_selected_abstract'] and str(r['license']).lower().replace('_','-') in ('cc0','cc-by','cc-by-sa','cc0-1.0','cc-by-4.0','cc-by-sa-4.0')]
        p['content_license_observations']=license_evidence;p['abstract_display_allowed']=bool(allowed)
        p['abstract_license']=allowed[0]['license'] if allowed else None
    edges=set()
    for e in read_json(f/'citation_events.json'):
        a=redirects.get(e['provider']+':'+e['source']);b=redirects.get(e['provider']+':'+e['target'])
        if a and b and a!=b:edges.add((a,b))
    for name,value in [('papers.private.json',papers),('redirects.json',redirects),('resolved_edges.all.json',sorted(edges)),
        ('merge_events.json',merges),('duplicate_audit.json',DUPLICATE_AUDIT),('suspected_duplicates.json',suspicious),('missing_arxiv_v1_dates.json',missing)]:write_json(f/name,value)
    write_json(f/'DEDUPLICATION.json',{'candidate_observations':len(events),'source_identities':len(observations),'after_dedup':len(papers),
        'merge_events':len(merges),'parent_pairs_reviewed':len(DUPLICATE_AUDIT),'pairs_merged':sum(r['decision']=='merge' for r in DUPLICATE_AUDIT),
        'pairs_kept_separate':sum(r['decision']=='keep_separate' for r in DUPLICATE_AUDIT),'abstracts_available':sum(bool(p['abstract']) for p in papers),
        'abstract_display_allowed':sum(p['abstract_display_allowed'] for p in papers),'citation_edges':len(edges)})
    print(json.dumps({'stage':'final_dedup_complete','papers':len(papers),'pairs_reviewed':len(DUPLICATE_AUDIT)}),flush=True)


if __name__=='__main__':
    FinalCollector().run();build_final_papers()
