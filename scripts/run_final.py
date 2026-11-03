"""Resumable server pipeline. Never publishes or commits."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from final_common import folder, settings, read_json, write_json
from resolve_seeds import ROOT
from server_runtime import private_root


def parent_inventory():
    config=settings();result={}
    for name in config['parents']:
        for label,base in [('public',ROOT/'data'/('snapshot-'+name)),('private',private_root()/name)]:
            if base.exists():
                result[name+'/'+label]={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(base.rglob('*')) if p.is_file()}
    return result


def main():
    f=folder();parent_path=f/'parentage.json'
    if parent_path.exists():before=read_json(parent_path)['parent_files_sha256']
    else:
        before=parent_inventory();write_json(parent_path,{'snapshot':settings()['snapshot'],'parents':settings()['parents'],'parent_files_sha256':before})
    if parent_inventory()!=before:raise RuntimeError('Approved parent snapshot changed before final run')
    stages=['collect_final.py','tiers_final.py','vectors_final.py','citation_contexts_final.py','context_citation_edges.py','analytics_final.py','extract_final.py','build_site.py']
    for script in stages:
        while not (ROOT/'scripts'/script).exists():time.sleep(2)
        write_json(f/'PIPELINE.json',{'stage':script,'status':'running'})
        command=[sys.executable,str(ROOT/'scripts'/script)]
        if script=='build_site.py':command+=['--private',str(f),'--config',os.environ.get('ATLAS_FINAL_CONFIG',str(ROOT/'config/final.yaml'))]
        print(json.dumps({'stage':script,'status':'started'}),flush=True)
        subprocess.run(command,check=True,cwd=ROOT)
        if parent_inventory()!=before:raise RuntimeError('A parent snapshot changed during final processing')
        print(json.dumps({'stage':script,'status':'complete'}),flush=True)
    write_json(f/'PIPELINE.json',{'stage':'public_export','status':'complete','publication_performed':False})


if __name__=='__main__':main()
