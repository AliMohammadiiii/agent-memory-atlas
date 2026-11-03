"""Fork public metadata for private acquisition counts; never export PDF text."""
import argparse,hashlib,json,os,shutil
from pathlib import Path

def read(p):return json.loads(p.read_text())
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.new');tmp.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n');os.replace(tmp,p)
def inventory(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}
def build(parent,out,summary_path,site_data=None):
    assert parent.resolve()!=out.resolve()
    before=inventory(parent);summary=read(summary_path)
    assert summary['assessed_full_text_evidence']==0 and not summary['used_in_chat']
    if not out.exists():shutil.copytree(parent,out,copy_function=os.link)
    manifest=read(parent/'manifest.json');counts=manifest['counts'];checklist=read(parent/'downloads/fulltext-downloads.json')
    mapping={'processed_files':'collection_processed_files','extracted_files':'collection_extracted_files','identity_consistent_files':'collection_identity_consistent_files','identity_review_required':'collection_identity_review_required','failed_files':'collection_failed_files','physical_pages':'collection_physical_pages','unique_identity_consistent_papers':'collection_unique_identity_consistent_papers'}
    for source,key in mapping.items():
        assert isinstance(summary[source],int) and summary[source]>=0
        counts[key]=checklist['counts'][key]=summary[source]
    assert counts['collection_processed_files']<=counts['received_pdf_files']
    assert counts['collection_extracted_files']+counts['collection_failed_files']==counts['collection_processed_files']
    counts['full_text_works']=read(parent/'counts.json')['full_text_works']
    manifest['snapshot'].update(id='2026-11-02-pdf-receipt',parents=[read(parent/'manifest.json')['snapshot']['id']],pdf_processing_date='2026-11-02')
    manifest['files']['fulltextReceipt']='fulltext-receipt.json'
    public={k:summary[k] for k in ('protocol','processed_files','extracted_files','failed_files','identity_consistent_files','identity_review_required','unique_identity_consistent_papers','physical_pages','assessed_full_text_evidence','used_in_chat','public_pdf_or_text_exported')}
    public.update(received_pdf_files=counts['received_pdf_files'],definition='Acquisition and machine extraction only. Identity checks are heuristic; no scientific-claim validation or full-text RAG integration.')
    write(out/'fulltext-receipt.json',public);write(out/'downloads/fulltext-downloads.json',checklist)
    write(out/'counts.json',counts);write(out/'manifest.json',manifest)
    diff=read(parent/'diff.json');diff.update(parent=read(parent/'manifest.json')['snapshot']['id'],current=manifest['snapshot']['id'],status='Private PDF receipt and extraction counts only; scientific corpus and evidence unchanged.');write(out/'diff.json',diff)
    hashes=inventory(out);hashes.pop('FILES.sha256.json',None);write(out/'FILES.sha256.json',hashes)
    assert inventory(parent)==before,'Previous snapshot changed'
    for path in ('matrix.json','papers-index.json','graph.json'):
        assert hashlib.sha256((parent/path).read_bytes()).digest()==hashlib.sha256((out/path).read_bytes()).digest()
    if site_data:
        n=site_data.with_name('.pdf-receipt-next');old=site_data.with_name('.pdf-receipt-old')
        for p in (n,old):
            if p.exists():shutil.rmtree(p)
        shutil.copytree(out,n,copy_function=os.link)
        if site_data.exists():os.replace(site_data,old)
        os.replace(n,site_data)
        if old.exists():shutil.rmtree(old)
    return public
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--summary',type=Path,required=True);p.add_argument('--site-data',type=Path);a=p.parse_args();print(json.dumps(build(a.parent,a.out,a.summary,a.site_data)))
