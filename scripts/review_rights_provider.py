"""Augment explicit PDF notices with API-licensed exact download URLs from raw cache."""
import csv,hashlib,json,os,urllib.parse
from pathlib import Path

def norm(u):
 if not isinstance(u,str) or not u.startswith(('http://','https://')):return ''
 x=urllib.parse.urlsplit(u.strip());return x.scheme.lower()+'://'+x.netloc.lower()+x.path.rstrip('/')+('?' + x.query if x.query else '')
def run(private,review):
 p=Path('/proc/2086542/environ');env=dict(x.split(b'=',1) for x in p.read_bytes().split(b'\0') if b'=' in x);rawroot=Path(env[b'ATLAS_RAW_DIR'].decode())
 papers={p['id']:p for p in json.loads((private/'2026-11-01-final/papers.private.json').read_text())};receipts={r['paper_id']:r for r in csv.DictReader((private/'fulltexts-2026-11-02/download-results.csv').open()) if r['status']=='downloaded'}
 previous=review/'RIGHTS.private.json';direct=review/'RIGHTS-DIRECT-PDF.private.json';rows=json.loads((direct if direct.exists() else previous).read_text());
 if not direct.exists():direct.write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
 cache={};added=0
 for row in rows:
  if row['private_processing_allowed']:continue
  p=papers[row['paper_id']];download=receipts.get(row['paper_id'],{});urls={norm(download.get('download_url'))};details=download.get('details','').split(';',1)
  if len(details)>1:urls.add(norm(details[1].strip()))
  urls.discard('');matches=[]
  for obs in p.get('content_license_observations',[]):
   license=str(obs.get('license') or '').lower();source=obs.get('source_id','');prov=obs.get('provenance') or {};req=prov.get('request_hash');sha=prov.get('response_sha256')
   if not source.startswith('https://openalex.org/') or not req or not sha or not (license in ('cc-by','cc-by-sa','cc-by-nc','cc-by-nc-sa','cc-by-nc-nd','cc-by-nd','cc0','cc-0')):continue
   if req not in cache:
    f=rawroot/'requests'/(req+'.json');data=None
    if f.exists():
     entry=json.loads(f.read_text());att=next((a for a in entry.get('attempts',[]) if a.get('status')==200 and a.get('response_sha256')==sha),None)
     if att:
      body=(rawroot/att['body_path']).read_bytes();assert hashlib.sha256(body).hexdigest()==sha
      try:data=json.loads(body)
      except (ValueError,UnicodeDecodeError):pass
    cache[req]=data
   data=cache[req];records=([data] if isinstance(data,dict) else [])
   if isinstance(data,dict) and isinstance(data.get('results'),list):records=data['results']
   for item in records:
    if not isinstance(item,dict) or item.get('id')!=source:continue
    locations=list(item.get('locations') or [])+[item.get('primary_location'),item.get('best_oa_location')]
    for loc in locations:
     if not isinstance(loc,dict):continue
     ll=str(loc.get('license') or '').lower();pdf=loc.get('pdf_url')
     if norm(pdf) in urls and norm(pdf) and (ll in ('cc-by','cc-by-sa','cc-by-nc','cc-by-nc-sa','cc-by-nc-nd','cc-by-nd','cc0','cc-0')):
      matches.append({'basis':'OpenAlex reports a Creative Commons license for the same PDF download URL','license':ll,'pdf_url':pdf,'source_id':source,'retrieved_at':prov.get('retrieved_at'),'response_sha256':sha,'version_limit':'Exact URL matched; the provider does not provide a PDF hash, so version equivalence is not independently established.'})
  if matches:
   row.update(status='provider_license_exact_url',private_processing_allowed=True,public_short_quote_allowed=False,provider_license_evidence=matches);added+=1
 (review/'RIGHTS.private.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n');summary={'core_with_accepted_pdf':len(rows),'explicit_pdf_notice':sum(r['status']=='explicit_license' for r in rows),'provider_license_exact_url':added,'eligible_for_private_processing':sum(r['private_processing_allowed'] for r in rows),'permission_unresolved':sum(not r['private_processing_allowed'] for r in rows),'limitation':'Provider licenses match the download URL but not a PDF checksum; exact version identity remains unverified.'};(review/'RIGHTS-SUMMARY.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n');print(json.dumps(summary),flush=True)
if __name__=='__main__':run(Path('/var/lib/agent-memory-atlas/private'),Path('/var/lib/agent-memory-atlas/private/review-2026-11-02'))
