"""Hash-checked bounded stream; extract raw PDF reading order privately."""
import argparse,gzip,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path

def serve(folder):
 folder.mkdir(parents=True,exist_ok=True,mode=0o700);(folder/'raw-pages').mkdir(exist_ok=True,mode=0o700);(folder/'raw-records').mkdir(exist_ok=True,mode=0o700);(folder/'spool').mkdir(exist_ok=True,mode=0o700)
 while line:=sys.stdin.buffer.readline(65536):
  h=json.loads(line);size=h['bytes'];sha=h['pdf_sha256'];assert isinstance(size,int) and 0<size<100_000_000 and re.fullmatch('[a-f0-9]{64}',sha)
  assert shutil.disk_usage(folder).free>120_000_000+size
  target=folder/'raw-pages'/(sha+'.json.gz');record=folder/'raw-records'/(sha+'.json')
  with tempfile.TemporaryDirectory(dir=folder/'spool') as tmp:
   pdf=Path(tmp)/'source.pdf';digest=hashlib.sha256();left=size
   with pdf.open('wb') as output:
    while left:
     chunk=sys.stdin.buffer.read(min(left,1048576))
     if not chunk:raise EOFError('Incomplete transfer')
     output.write(chunk);digest.update(chunk);left-=len(chunk)
   assert digest.hexdigest()==sha
   if not target.exists():
    text=Path(tmp)/'raw.txt';r=subprocess.run(['pdftotext','-raw','-enc','UTF-8',str(pdf),str(text)],capture_output=True,timeout=90);assert r.returncode==0 and text.stat().st_size<25_000_000
    body=text.read_text(errors='replace');pages=body.split('\f')
    if pages and not pages[-1].strip():pages.pop()
    with gzip.open(str(target)+'.new','wt',encoding='utf8') as f:json.dump({'paper_id':h['paper_id'],'pdf_sha256':sha,'method':'pdftotext -raw','pages':[{'page':i+1,'text':p} for i,p in enumerate(pages)]},f,ensure_ascii=False)
    os.replace(str(target)+'.new',target);record.write_text(json.dumps({'paper_id':h['paper_id'],'pdf_sha256':sha,'pages':len(pages),'characters':len(body)})+'\n')
  print(json.dumps({'paper_id':h['paper_id'],'processed':True}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);a=p.parse_args();serve(a.folder)
