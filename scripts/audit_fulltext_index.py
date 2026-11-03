"""Verify every private indexed span against the original extracted PDF page."""
import argparse,gzip,hashlib,json,sqlite3,zlib
from pathlib import Path

def audit(index,source):
    manifest=json.loads((index/'manifest.json').read_text());rows=[json.loads(p.read_text()) for p in (source/'records').glob('*.json')]
    accepted={r['paper_id']:r for r in rows if r['status']=='extracted' and r.get('identity_status') in manifest['parameters']['accepted_identity_statuses']}
    db=sqlite3.connect((index/'index.sqlite').as_uri()+'?mode=ro',uri=True)
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert set(p[0] for p in db.execute('SELECT paper_id FROM papers'))==set(accepted)
    total=0
    for pid,row in sorted(accepted.items()):
        with gzip.open(source/'pages'/(row['pdf_sha256']+'.json.gz'),'rt') as f:payload=json.load(f)
        assert payload['pdf_sha256']==row['pdf_sha256'];pages={p['page']:p['text'] for p in payload['pages']}
        count=0
        for page,start,end,body,sha in db.execute('SELECT page,start_offset,end_offset,body,span_sha256 FROM chunks WHERE paper_id=? ORDER BY chunk_id',(pid,)):
            span=zlib.decompress(body).decode();assert span==pages[page][start:end];assert hashlib.sha256(span.encode()).hexdigest()==sha;count+=1
        assert count==manifest['paper_chunks'][pid];total+=count
    assert total==manifest['passages'];db.close()
    receipt={'status':'passed','papers':len(accepted),'passages_checked':total,'all_spans_exact_page_substrings':True,'all_span_hashes_verified':True,'excluded_identity_files':len(rows)-len(accepted),'index_sha256':hashlib.sha256((index/'index.sqlite').read_bytes()).hexdigest(),'public_text_exported':False}
    assert receipt['index_sha256']==manifest['index_sha256'];(index/'SOURCE-AUDIT.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n');return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--index',type=Path,required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args();print(json.dumps(audit(a.index.resolve(),a.source.resolve())))
