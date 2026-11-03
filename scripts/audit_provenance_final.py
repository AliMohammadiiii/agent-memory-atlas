"""Verify normalized metadata against the privately stored primary API bodies."""
import argparse
from collections import defaultdict
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from phase2_collect import normalized_record


def walk(value):
    if isinstance(value,dict):
        if value.get('title') and (value.get('paperId') or str(value.get('id','')).startswith('https://openalex.org/')):
            yield value
        for child in value.values():yield from walk(child)
    elif isinstance(value,list):
        for child in value:yield from walk(child)


def audit(private,raw):
    events=json.loads((private/'candidate_events.json').read_text());papers=json.loads((private/'papers.private.json').read_text())
    groups=defaultdict(list)
    for event in events:
        provenance=event['provenance']
        assert provenance.get('retrieved_at') and provenance.get('response_sha256'),'Missing API retrieval provenance'
        groups[provenance['response_sha256']].append(event)
    verified=[];derived_arxiv=[];identifier_pairs=set();fields=['title','doi','year','publication_date','venue','authors','abstract','citation_count']
    dates=json.loads((private/'arxiv_dates.json').read_text())
    for sha in {r['provenance']['response_sha256'] for r in dates.values() if r.get('provenance',{}).get('response_sha256')}:
        body=(raw/'responses'/(sha+'.body')).read_bytes()
        assert hashlib.sha256(body).hexdigest()==sha,'arXiv response hash mismatch'
        for entry in ET.fromstring(body).findall('{http://www.w3.org/2005/Atom}entry'):
            match=re.search(r'(\d{4}\.\d{4,5})(?:v\d+)?$',entry.findtext('{http://www.w3.org/2005/Atom}id') or '')
            if match:
                for doi in re.findall(r'10\.\d{4,9}/\S+',entry.findtext('{http://arxiv.org/schemas/atom}doi') or ''):
                    identifier_pairs.add((doi.rstrip(';,').lower(),match[1]))
    for sha,rows in sorted(groups.items()):
        body=(raw/'responses'/(sha+'.body')).read_bytes()
        assert hashlib.sha256(body).hexdigest()==sha,'Primary response hash mismatch'
        candidates=defaultdict(list)
        for source in walk(json.loads(body)):
            provider='s2' if source.get('paperId') else 'openalex'
            candidates[(provider,source.get('paperId') if provider=='s2' else source['id'])].append(source)
        for event in rows:
            options=candidates[(event['provider'],event['source_id'])]
            matched=False
            for source in options:
                observed=normalized_record(source,event['provider'],event['provenance'],event.get('discovery',{}))
                if observed.get('doi') and observed.get('arxiv_id'):identifier_pairs.add((observed['doi'],observed['arxiv_id']))
                if all(event.get(field)==observed.get(field) for field in fields):
                    if event.get('arxiv_id')!=observed.get('arxiv_id'):
                        assert observed.get('arxiv_id') is None,'Conflicting arXiv identity replaced a supplied API identifier'
                        derived_arxiv.append((event.get('doi'),event.get('arxiv_id')))
                    matched=True;break
            assert matched,'Normalized metadata is not present in its primary API response: '+event['source_id']
            verified.append(event)
    assert all(pair in identifier_pairs for pair in derived_arxiv),'Derived arXiv identity lacks primary cross-API DOI linkage'
    by_source=defaultdict(list)
    for event in verified:by_source[(event['provider'],event['source_id'])].append(event)
    for paper in papers:
        observations=[row for provider,ids in paper['source_ids'].items() for ident in ids for row in by_source[(provider,ident)]]
        assert any(r['title']==paper['title'] for r in observations),'Canonical title lacks verified primary source'
        if paper.get('abstract'):assert any(r.get('abstract')==paper['abstract'] for r in observations),'Selected abstract lacks verified primary source'
    return {'status':'passed','primary_response_bodies_sha256_verified':len(groups),'normalized_observations_verified':len(verified),'canonical_papers_verified':len(papers),'abstracts_verified':sum(bool(p.get('abstract')) for p in papers),'fields_checked':fields,'derived_arxiv_id_observations_verified_against_primary_doi_links':len(derived_arxiv),'raw_archive_copied':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--private',type=Path,required=True);parser.add_argument('--raw',type=Path,required=True);parser.add_argument('--out',type=Path);a=parser.parse_args();r=audit(a.private,a.raw)
    if a.out:a.out.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
    print(json.dumps(r,sort_keys=True))
