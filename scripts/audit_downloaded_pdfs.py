"""Private, server-side PDF identity/extraction audit; no public paper text."""
import argparse,gzip,hashlib,json,re,subprocess,unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

def normalize(s):
    s=unicodedata.normalize('NFKD',s).lower();return ' '.join(re.findall(r'[a-z0-9]+',s))

def audit(folder):
    root=Path(__file__).resolve().parents[1]
    assert root not in folder.resolve().parents
    incoming=folder/'incoming';manifest=json.loads((incoming/'first-batch-audit-manifest.json').read_text());output=folder/'extracted';output.mkdir(exist_ok=True)
    rows=[]
    for record in manifest:
        name=record['file'];assert Path(name).name==name
        path=incoming/name;blob=path.read_bytes();sha=hashlib.sha256(blob).hexdigest()
        assert len(blob)==record['bytes'] and blob.startswith(b'%PDF-')
        row={k:record.get(k) for k in ('paper_id','title','arxiv_id','doi','file')};row.update(sha256=sha,bytes=len(blob),status='unresolved')
        try:
            result=subprocess.run(['pdftotext','-layout','-enc','UTF-8',str(path),'-'],capture_output=True,timeout=120)
            if result.returncode:raise RuntimeError('PDF text extraction failed')
            text=result.stdout.decode('utf8',errors='replace');pages=text.split('\f');pages=[page for page in pages if page.strip()]
            front=pages[0] if pages else '';front=re.split(r'\babstract\b|\bintroduction\b',front,flags=re.I)[0][:6000]
            target=normalize(record['title']);tokens=normalize(front).split();needle=target.split();best=0.0
            if target and target in normalize(front):best=1.0
            elif len(needle)>=3:
                for n in (max(3,len(needle)-3),len(needle),len(needle)+3):
                    for i in range(max(1,len(tokens)-n+1)):
                        best=max(best,SequenceMatcher(None,needle,tokens[i:i+n],autojunk=False).ratio())
            banner=' '.join(pages[:2]);ids=set(m.group(1).lower() for m in re.finditer(r'arxiv\s*:\s*([a-z-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?',banner,re.I))
            expected=(record.get('arxiv_id') or '').lower();identifier_match=bool(expected and expected in ids)
            if best==1.0 and len(target)>=15:status='frontmatter_title_match'
            elif identifier_match and best>=0.5:status='arxiv_and_title_consistent'
            elif identifier_match:status='arxiv_match_title_review_required'
            else:status='identity_review_required'
            rows.append({**row,'status':status,'title_similarity':best,'arxiv_banner_match':identifier_match,'observed_arxiv_banners':sorted(ids),'pages_extracted':len(pages),'text_characters':len(text),'full_text_evidence_assessed':False})
            payload={'paper_id':record['paper_id'],'pdf_sha256':sha,'identity_status':status,'page_number_basis':'physical PDF page; extracted text only','pages':[{'page':i+1,'text':page} for i,page in enumerate(pages)]}
            with gzip.open(output/(sha+'.pages.json.gz'),'wt',encoding='utf8') as f:json.dump(payload,f,ensure_ascii=False)
        except (subprocess.TimeoutExpired,RuntimeError) as e:rows.append({**row,'status':'parse_failed','reason':type(e).__name__})
        (folder/'audit.private.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps({'processed':len(rows),'total':len(manifest),'status':rows[-1]['status']}),flush=True)
    counts=Counter(r['status'] for r in rows);summary={'received_first_batch':len(manifest),'parsed':sum(r['status']!='parse_failed' for r in rows),'identity_consistent':sum(counts[k] for k in ('frontmatter_title_match','arxiv_and_title_consistent')),'review_required':sum(counts[k] for k in ('arxiv_match_title_review_required','identity_review_required')),'status_counts':dict(counts),'full_text_evidence_assessed':0,'public_text_exported':False,'method':'Frontmatter title match, or matching arXiv banner plus title token-sequence similarity >=0.5. These automated identity checks are not a human reading or content/rights assessment.'}
    (folder/'AUDIT-SUMMARY.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);a=p.parse_args();audit(a.folder)
