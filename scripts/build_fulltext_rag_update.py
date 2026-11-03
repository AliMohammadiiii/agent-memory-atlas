"""Export only public RAG coverage metadata; source pages remain private."""
import argparse,json,os,shutil
from pathlib import Path
from build_pdf_receipt_update import read,write,inventory
def build(parent,out,index,site_data=None):
    assert parent.resolve()!=out.resolve();before=inventory(parent)
    raw=read(index/'manifest.json');audit=read(index/'SOURCE-AUDIT.json')
    assert audit['status']=='passed' and audit['all_spans_exact_page_substrings'] and audit['index_sha256']==raw['index_sha256']
    assert raw['papers']==len(raw['paper_chunks'])==2452 and raw['excluded_identity_files']==33
    assert set(raw['paper_chunks'])<={p['id'] for p in read(parent/'papers-index.json')}
    if not out.exists():shutil.copytree(parent,out,copy_function=os.link)
    m=read(parent/'manifest.json');c=m['counts']
    c.update(fulltext_rag_papers=raw['papers'],fulltext_rag_passages=raw['passages'],fulltext_rag_pages=raw['physical_pages'],fulltext_rag_excluded_files=33,matrix_fulltext_assessed=c['full_text_works'])
    m['snapshot'].update(id='2026-11-02-fulltext-rag',parents=[read(parent/'manifest.json')['snapshot']['id']],rag_date='2026-11-02')
    m['files']['fulltextRag']='fulltext-rag.json'
    # Replace superseded availability statements only in this new snapshot.
    def update_limit(value):
        if isinstance(value,dict):return {k:update_limit(v) for k,v in value.items()}
        if isinstance(value,str):
            if value.startswith('Source depth:'):return 'Source depth: the original corpus contains abstracts and metadata. Full-text chat now uses 2,452 privately indexed PDF identities; other records retain abstract-only coverage.'
            return value.replace('Newly received private PDFs are pending evidence/rights assessment and are not used in this snapshot’s answers or capability matrix.','Accepted private PDFs are now available in chat. Public full-text quotations remain withheld, and capability-matrix cells remain abstract-based.')
        return value
    m['limitations']=[update_limit(v) for v in m['limitations']]
    m['limitations'].append({'title':'Full-text retrieval coverage','detail':'Only the 2,452 identity-consistent PDFs are indexed; 33 identity flags are excluded. Extraction and scientific conclusions are not human-validated. Semantic paper recall uses title/abstract embeddings; full-text passages use BM25 and Jina reranking. Matrix cells remain abstract-based. Full-text quotations are withheld pending permission for each exact PDF version.'})
    c['limitations_count']=len(m['limitations'])
    public={k:raw[k] for k in ('id','papers','passages','physical_pages','excluded_identity_files','parameters','index_sha256')}
    public.update(source_audit=audit,used_in_chat=True,matrix_reextracted=False,public_pdf_or_page_text_exported=False)
    write(out/'fulltext-rag.json',public)
    downloads=read(parent/'downloads/fulltext-downloads.json');downloads['counts'].update({k:v for k,v in c.items() if k.startswith('fulltext_rag_') or k=='matrix_fulltext_assessed'});write(out/'downloads/fulltext-downloads.json',downloads)
    receipt=read(parent/'fulltext-receipt.json');receipt.update(used_in_chat=True,rag_indexed_papers=raw['papers'],rag_excluded_identity_files=33,definition='Acquisition and extraction counts are separate from RAG availability. Only identity-consistent PDFs are used in chat; matrix full-text assessments remain zero.');write(out/'fulltext-receipt.json',receipt)
    write(out/'counts.json',c);write(out/'manifest.json',m)
    diff=read(parent/'diff.json');diff.update(parent=read(parent/'manifest.json')['snapshot']['id'],current=m['snapshot']['id'],status='Private full-text RAG added; corpus metadata, citations, embeddings and abstract-based matrix unchanged.');write(out/'diff.json',diff)
    hashes=inventory(out);hashes.pop('FILES.sha256.json',None);write(out/'FILES.sha256.json',hashes)
    assert inventory(parent)==before
    for name in ('matrix.json','graph.json','papers-index.json'):assert (out/name).read_bytes()==(parent/name).read_bytes()
    if site_data:
        n=site_data.with_name('.fulltext-rag-next');old=site_data.with_name('.fulltext-rag-old')
        for p in (n,old):
            if p.exists():shutil.rmtree(p)
        shutil.copytree(out,n,copy_function=os.link)
        if site_data.exists():os.replace(site_data,old)
        os.replace(n,site_data)
        if old.exists():shutil.rmtree(old)
    return {k:public[k] for k in ('id','papers','passages','physical_pages','used_in_chat')}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--index',type=Path,required=True);p.add_argument('--site-data',type=Path);a=p.parse_args();print(json.dumps(build(a.parent,a.out,a.index,a.site_data)))
