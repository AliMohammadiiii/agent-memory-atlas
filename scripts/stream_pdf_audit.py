"""Private, resumable server-side PDF extraction over a bounded-memory stream.

Protocol: one JSON header line, exactly `bytes` PDF bytes, one JSON receipt.
No PDF or extracted text is written beneath the source tree. No model/API calls.
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

def normalized(text):
    text=unicodedata.normalize('NFKD',text).casefold()
    text=re.sub(r'-\s*\n\s*','',text)
    return ' '.join(re.findall(r'[a-z0-9]+',text))

def identity(record,pages):
    front=pages[0] if pages else ''
    front=re.split(r'\babstract\b|\bintroduction\b',front,flags=re.I)[0][:8000]
    target=normalized(record['title']);candidate=normalized(front)
    exact=len(target)>=15 and (target in candidate or target.replace(' ','') in candidate.replace(' ',''))
    arxiv={m.group(1).lower() for m in re.finditer(r'arxiv\s*:\s*([a-z-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?',' '.join(pages[:2]),re.I)}
    expected=(record.get('arxiv_id') or '').lower()
    overlap=len(set(target.split())&set(candidate.split()))/max(1,len(set(target.split())))
    id_match=bool(expected and expected in arxiv)
    # This is a frozen identity heuristic, not a relevance or scientific-quality test.
    status='title_match' if exact else 'arxiv_and_title_match' if id_match and overlap>=0.8 else 'identity_review_required'
    return {'identity_status':status,'title_exact_normalized':exact,'title_token_recall':round(overlap,6),'arxiv_banner_match':id_match,'observed_arxiv_banners':sorted(arxiv)}

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.new.'+str(os.getpid()));tmp.write_text(json.dumps(value,sort_keys=True,ensure_ascii=False)+'\n');os.replace(tmp,path)

def summarize(folder):
    rows=[json.loads(p.read_text()) for p in sorted((folder/'records').glob('*.json'))]
    counts=Counter(r['status'] for r in rows)
    consistent=[r for r in rows if r['status']=='extracted' and r['identity_status'] in ('title_match','arxiv_and_title_match')]
    summary={'protocol':'private-pdf-stream-v1','processed_files':len(rows),'extracted_files':counts['extracted'],'failed_files':len(rows)-counts['extracted'],'identity_consistent_files':len(consistent),'identity_review_required':sum(r.get('identity_status')=='identity_review_required' for r in rows),'unique_identity_consistent_papers':len({r['paper_id'] for r in consistent}),'unique_pdf_hashes':len({r['pdf_sha256'] for r in rows}),'physical_pages':sum(r.get('physical_pages',0) for r in rows),'text_characters':sum(r.get('text_characters',0) for r in rows),'assessed_full_text_evidence':0,'used_in_chat':False,'public_pdf_or_text_exported':False,'status_counts':dict(counts)}
    atomic_json(folder/'SUMMARY.json',summary)
    return summary

def serve(folder):
    root=Path(__file__).resolve().parents[1];folder=folder.resolve()
    if folder==root or root in folder.parents:raise ValueError('Private destination must be outside engine')
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name in ('records','pages','spool'):(folder/name).mkdir(exist_ok=True,mode=0o700)
    while line:=sys.stdin.buffer.readline(65536):
        header=json.loads(line);size=header['bytes'];expected_sha=header['pdf_sha256']
        if not isinstance(size,int) or not 0<size<=100_000_000 or not re.fullmatch('[a-f0-9]{64}',expected_sha):raise ValueError('Invalid stream header')
        key=hashlib.sha256((header['paper_id']+'\0'+expected_sha).encode()).hexdigest()
        record_path=folder/'records'/(key+'.json');cached=record_path.exists()
        if shutil.disk_usage(folder).free<250_000_000+size:raise RuntimeError('Insufficient bounded extraction reserve')
        with tempfile.TemporaryDirectory(dir=folder/'spool') as tmp:
            pdf=Path(tmp)/'input.pdf';h=hashlib.sha256();remaining=size
            with pdf.open('wb') as out:
                while remaining:
                    chunk=sys.stdin.buffer.read(min(1_048_576,remaining))
                    if not chunk:raise EOFError('Truncated PDF stream')
                    out.write(chunk);h.update(chunk);remaining-=len(chunk)
            if h.hexdigest()!=expected_sha:raise ValueError('Transport hash mismatch')
            if not cached:
                row={k:header.get(k) for k in ('paper_id','title','file','arxiv_id','doi','bytes','pdf_sha256')}
                row.update(processed_at=datetime.now(timezone.utc).isoformat(),status='parse_failed')
                try:
                    if pdf.open('rb').read(5)!=b'%PDF-':raise ValueError('Not a PDF')
                    output=Path(tmp)/'text.txt'
                    r=subprocess.run(['pdftotext','-layout','-enc','UTF-8',str(pdf),str(output)],capture_output=True,timeout=90)
                    if r.returncode or not output.exists():raise ValueError('Extraction failed')
                    if output.stat().st_size>25_000_000:raise ValueError('Text exceeds safety bound')
                    text=output.read_text(errors='replace');pages=text.split('\f')
                    if pages and not pages[-1].strip():pages.pop()
                    row.update(identity(header,pages),physical_pages=len(pages),text_characters=len(text))
                    if len(re.findall(r'\w+',text))<100:row['status']='insufficient_text'
                    else:
                        row['status']='extracted'
                        payload={'pdf_sha256':expected_sha,'page_number_basis':'Physical PDF pages, including blank pages','pages':[{'page':i+1,'text':p} for i,p in enumerate(pages)]}
                        dest=folder/'pages'/(expected_sha+'.json.gz')
                        if not dest.exists():
                            with gzip.open(str(dest)+'.new','wt',encoding='utf8') as f:json.dump(payload,f,ensure_ascii=False)
                            os.replace(str(dest)+'.new',dest)
                except (ValueError,subprocess.TimeoutExpired) as exc:row['error_type']=type(exc).__name__
                atomic_json(record_path,row)
        row=json.loads(record_path.read_text())
        print(json.dumps({'paper_id':row['paper_id'],'status':row['status'],'cached':cached}),flush=True)
    summarize(folder)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--summary',action='store_true');p.add_argument('--completed',action='store_true');a=p.parse_args()
    if a.summary:print(json.dumps(summarize(a.folder)))
    elif a.completed:print(json.dumps([json.loads(x.read_text()) for x in sorted((a.folder/'records').glob('*.json'))]))
    else:serve(a.folder)
