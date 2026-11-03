"""Build a private, page-bound FTS index only from accepted PDF identities."""
import argparse,gzip,hashlib,json,os,shutil,sqlite3,zlib
from collections import Counter
from pathlib import Path

def chunks(text,maximum,overlap,minimum):
    start=0
    while start<len(text):
        end=min(start+maximum,len(text))
        if end<len(text):
            boundary=text.rfind('\n',max(start+maximum//2,end-700),end)
            if boundary>start:end=boundary+1
        left=start
        while left<end and text[left].isspace():left+=1
        right=end
        while right>left and text[right-1].isspace():right-=1
        if right-left>=minimum:yield left,right,text[left:right]
        if end==len(text):break
        start=max(start+1,end-overlap)

def build(source,private,out,config_path):
    root=Path(__file__).resolve().parents[1]
    for folder in (source,out):
        assert folder.resolve()!=root and root not in folder.resolve().parents,'Private paths must be outside source tree'
    cfg=json.loads(config_path.read_text());rows=[json.loads(p.read_text()) for p in sorted((source/'records').glob('*.json'))]
    papers={p['id']:p for p in json.loads((private/'papers.private.json').read_text()) if p.get('tier') in ('CORE','ADJACENT')}
    accepted=sorted([r for r in rows if r['status']=='extracted' and r.get('identity_status') in cfg['accepted_identity_statuses']],key=lambda r:(r['paper_id'],r['pdf_sha256']))
    assert len(accepted)==len({r['paper_id'] for r in accepted})==cfg['expected_papers']
    assert len(rows)-len(accepted)==cfg['expected_excluded_files']
    assert all(r['paper_id'] in papers for r in accepted)
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    configuration_hash=hashlib.sha256(config_path.read_bytes()).hexdigest()
    if (out/'manifest.json').exists():
        existing=json.loads((out/'manifest.json').read_text());assert existing['config_sha256']==configuration_hash
        assert hashlib.sha256((out/'index.sqlite').read_bytes()).hexdigest()==existing['index_sha256'];return existing
    target=out/'index.building.sqlite';target.unlink(missing_ok=True)
    db=sqlite3.connect(target)
    db.executescript("""PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY;
    CREATE TABLE papers(paper_id TEXT PRIMARY KEY,title TEXT NOT NULL,pdf_sha256 TEXT NOT NULL,identity_status TEXT NOT NULL);
    CREATE TABLE chunks(chunk_id INTEGER PRIMARY KEY,paper_id TEXT NOT NULL,page INTEGER NOT NULL,start_offset INTEGER NOT NULL,end_offset INTEGER NOT NULL,body BLOB NOT NULL,span_sha256 TEXT NOT NULL);
    CREATE INDEX chunks_paper ON chunks(paper_id);
    CREATE VIRTUAL TABLE passages USING fts5(title,body,content='',tokenize='unicode61');""")
    total=0;pages=0;characters=0;per_paper={}
    for i,row in enumerate(accepted):
        pid=row['paper_id'];title=papers[pid]['title'];db.execute('INSERT INTO papers VALUES(?,?,?,?)',(pid,title,row['pdf_sha256'],row['identity_status']))
        with gzip.open(source/'pages'/(row['pdf_sha256']+'.json.gz'),'rt',encoding='utf8') as f:payload=json.load(f)
        assert payload['pdf_sha256']==row['pdf_sha256']
        count=0
        for page in payload['pages']:
            assert isinstance(page['page'],int) and page['page']>0
            pages+=1
            for start,end,span in chunks(page['text'],cfg['chunk_characters'],cfg['chunk_overlap_characters'],cfg['minimum_chunk_characters']):
                total+=1;count+=1;characters+=len(span)
                db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)',(total,pid,page['page'],start,end,zlib.compress(span.encode(),3),hashlib.sha256(span.encode()).hexdigest()))
                db.execute('INSERT INTO passages(rowid,title,body) VALUES(?,?,?)',(total,title,span))
        assert count>0;per_paper[pid]=count
        if (i+1)%100==0:
            db.commit();assert shutil.disk_usage(out).free>120_000_000,'Insufficient private-index reserve'
            print(json.dumps({'papers':i+1,'total_papers':len(accepted),'chunks':total}),flush=True)
    db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('SELECT count(DISTINCT paper_id) FROM chunks').fetchone()[0]==len(accepted)
    db.close();os.replace(target,out/'index.sqlite')
    manifest={'id':cfg['id'],'papers':len(accepted),'excluded_identity_files':len(rows)-len(accepted),'passages':total,'physical_pages':pages,'indexed_characters_with_overlap':characters,'config_sha256':configuration_hash,'index_sha256':hashlib.sha256((out/'index.sqlite').read_bytes()).hexdigest(),'index_bytes':(out/'index.sqlite').stat().st_size,'paper_chunks':per_paper,'parameters':cfg,'public_text_exported':False,'index_build_model_calls':False}
    (out/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--config',type=Path,required=True);a=p.parse_args();m=build(a.source,a.private,a.out,a.config);print(json.dumps({k:m[k] for k in ('id','papers','excluded_identity_files','passages','physical_pages','index_bytes','index_sha256')}))
