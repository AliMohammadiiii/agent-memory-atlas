"""Inspect explicit notices on the exact private PDF version; unknown stays unknown."""
import argparse,gzip,json,re,sqlite3
from pathlib import Path

def run(private,out):
 out.mkdir(parents=True,exist_ok=True);papers={p['id']:p for p in json.loads((private/'2026-11-01-final/papers.private.json').read_text())};db=sqlite3.connect(private/'fulltext-rag-2026-11-02/index.sqlite');rows=[]
 for pid,sha in db.execute('SELECT paper_id,pdf_sha256 FROM papers ORDER BY paper_id'):
  if papers[pid]['tier']!='CORE':continue
  with gzip.open(private/'pdf-stream-2026-11-02/pages'/(sha+'.json.gz'),'rt') as f:pages=json.load(f)['pages']
  notices=[]
  for page in pages[:2]+pages[-2:]:
   text=page['text'];flat=re.sub(r'\s+',' ',text)
   patterns=[r'(?:this\s+)?(?:open access\s+)?(?:article|work|paper|preprint|manuscript)\s*[,;]?\s*(?:is\s+|was\s+)?(?:licensed|distributed|made available|published)\s+(?:under\s+)?(?:the\s+terms\s+of\s+)?(?:a\s+)?(?:Creative Commons|CC[ -]?BY|CC[ -]?0|public domain|creativecommons\.org/licenses)',r'copyright (?:in )?(?:this )?paper by (?:the )?authors\.\s*Use permitted under (?:a )?Creative Commons']
   for pattern in patterns:
    for m in re.finditer(pattern,flat,re.I):
     context=flat[max(0,m.start()-50):min(len(flat),m.end()+180)]
     notices.append({'page':page['page'],'notice':context,'basis':'explicit own-work license notice'})
  rows.append({'paper_id':pid,'title':papers[pid]['title'],'pdf_sha256':sha,'status':'explicit_license' if notices else 'permission_unresolved','private_processing_allowed':bool(notices),'public_short_quote_allowed':bool(notices),'notices':notices})
  if len(rows)%100==0:(out/'RIGHTS.private.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n');print(json.dumps({'rights_processed':len(rows)}),flush=True)
 (out/'RIGHTS.private.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
 summary={'core_with_accepted_pdf':len(rows),'explicit_private_processing_license':sum(r['private_processing_allowed'] for r in rows),'permission_unresolved':sum(not r['private_processing_allowed'] for r in rows),'rule':'Exact-PDF first/last-page own-work Creative Commons notices; unknown permissions do not authorize matrix processing.'};(out/'RIGHTS-SUMMARY.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n');print(json.dumps(summary),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.private,a.out)
