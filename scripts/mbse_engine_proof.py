#!/usr/bin/env python3
"""Rebuild MBSE metadata with the identical engine in the isolated proof branch.

Prepare a no-checkout worktree on research/agent-memory-mbse-proof, then pass
--worktree. This script never edits the live MBSE corpus or main checkout.
It strips every abstract/full-text/chunk; metadata retains source links.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from build_site import ROOT, build, write


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(worktree,db):
    worktree=Path(worktree).resolve(); db=Path(db).resolve()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=worktree,text=True).strip()
    if branch!='research/agent-memory-mbse-proof': raise ValueError('Expected isolated proof branch')
    engine=worktree/'atlas-shared-engine-proof'; engine.mkdir(exist_ok=True)
    subprocess.run(['npm','run','build'],cwd=ROOT/'site',env=dict(os.environ,ATLAS_BASE='/agent-memory/'),check=True)
    primary_build_files={str(p.relative_to(ROOT/'site/dist')):digest(p) for p in sorted((ROOT/'site/dist').rglob('*')) if p.is_file()}
    for generated_source in ('site/src','site/scripts'):
        if (engine/generated_source).exists(): shutil.rmtree(engine/generated_source)
    copy_files=[ROOT/'scripts/build_site.py',ROOT/'site/package.json',ROOT/'site/package-lock.json',ROOT/'site/vite.config.js',ROOT/'site/index.html']
    copy_files += [p for p in (ROOT/'site/src').rglob('*') if p.is_file()]
    copy_files += [p for p in (ROOT/'site/scripts').rglob('*') if p.is_file()]
    hashes={}
    for src in copy_files:
        relative=src.relative_to(ROOT); dest=engine/relative; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dest)
        hashes[str(relative)]={'original':digest(src),'proof':digest(dest)}
    if any(v['original']!=v['proof'] for v in hashes.values()): raise AssertionError('Engine source differs')
    # Immutable read-only connection. No abstract or source text is selected.
    database_before=digest(db)
    connection=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True); connection.row_factory=sqlite3.Row
    records=[]
    for r in connection.execute('select id,title,doi,year,authors,url,evidence_level,is_seed,group_name,source_providers,metadata_json, CASE WHEN abstract IS NOT NULL AND length(trim(abstract))>0 THEN 1 ELSE 0 END AS abstract_available from papers order by id'):
        r=dict(r); meta=json.loads(r['metadata_json'] or '{}')
        records.append({'id':r['id'],'title':r['title'],'dois':[r['doi']] if r['doi'] else [],'first_public_year':r['year'],'authors':[{'name':a.strip()} for a in (r['authors'] or '').split(';') if a.strip()],
            'link':r['url'],'venue':meta.get('venue'),'evidence_level':r['evidence_level'],'tier':'CORE','tier_reason':'MBSE proof preserves its own existing corpus; no agent-memory relevance screening applied.',
            'is_seed':bool(r['is_seed']),'seed_groups':[r['group_name']] if r['group_name'] else [],'source_ids':{'openalex':[meta['openalex_id']] if meta.get('openalex_id') else [],'s2':[meta['semantic_scholar_id']] if meta.get('semantic_scholar_id') else []},
            'abstract_available':bool(r['abstract_available']),'abstract_display_allowed':False,'citations_total':int(meta['citation_count']) if str(meta.get('citation_count','')).isdigit() else None})
    ids={p['id'] for p in records}; edges=[]
    for e in connection.execute('select source,target,kind,relation from edges order by id'):
        if e['source'] in ids and e['target'] in ids: edges.append({'source':e['source'],'target':e['target'],'type':'citation' if e['kind']=='citation' else e['kind'],'weight':1,'relation':e['relation']})
    connection_edge_count=connection.execute('select count(*) from edges').fetchone()[0]
    connection.close()
    # Layout for proof only: explicitly labeled deterministic circle, no claimed scientific clusters.
    nodes=[{'id':p['id'],'x':math.cos(i*2*math.pi/max(len(records),1)),'y':math.sin(i*2*math.pi/max(len(records),1)),'cluster_id':None,'tier':'CORE'} for i,p in enumerate(records)]
    config={'atlas':{'id':'mbse','title':'MBSE Research Atlas','headline':['Model-based','systems engineering.'],'description':'Shared-engine proof built from the existing MBSE corpus metadata. Source text withheld.','route':'/mbse/','language':'en','defaultView':'citation','graphIntro':'Explore the recorded relationships in the existing MBSE literature corpus. This isolated proof uses metadata only and a circular overview layout.','scopeDescription':'This proof preserves the existing MBSE corpus as CORE without applying agent-memory screening.','seedGroups':[], 'themes':[], 'capabilities':[], 'projectAbstract':{'status':'not supplied','text':'No project abstract supplied for MBSE proof.'}},'snapshot':{'id':'mbse-shared-engine-proof-2026-11-01','date':'2026-11-01','parents':[]}}
    write(engine/'mbse-config.json',config)
    with tempfile.TemporaryDirectory(prefix='mbse-metadata-private-') as tmp:
        folder=Path(tmp)
        for name,value in [('papers',records),('analytics',{'nodes':nodes,'edges':edges,'methods':{'layout':'deterministic circle for isolated engine proof; no scientific clusters'}}),('matrix',{'columns':[],'rows':{},'coverage':{'status':'not extracted for MBSE proof'}}),('benchmarks',{'papers':[],'coverage':{'status':'not extracted for MBSE proof'}})]: write(folder/(name+'.private.json'),value)
        # Execute the copied build adapter, not the original process function.
        subprocess.run([os.environ.get('PYTHON','python3'),str(engine/'scripts/build_site.py'),'--private',tmp,'--config',str(engine/'mbse-config.json'),'--out',str(engine/'data/mbse-proof'),'--site-data',str(engine/'site/public/data'),'--previous',str(engine/'no-parent')],check=True)
    modules=ROOT.parent/'node_modules'
    if not modules.exists(): raise ValueError('Install standalone site dependencies before proof')
    target=engine/'site/node_modules'
    if not target.exists(): target.symlink_to(modules,target_is_directory=True)
    subprocess.run(['npm','run','build'],cwd=engine/'site',env=dict(os.environ,ATLAS_BASE='/mbse/'),check=True)
    manifest=json.loads((engine/'data/mbse-proof/manifest.json').read_text()); text=(engine/'site/dist/index.html').read_text()
    if manifest['atlas']['id']!='mbse' or manifest['counts']['retained']!=len(records) or '/mbse/assets/' not in text: raise AssertionError('MBSE rebuild did not use own config/data')
    proof_build_files={str(p.relative_to(engine/'site/dist')):digest(p) for p in sorted((engine/'site/dist').rglob('*')) if p.is_file()}
    if digest(db)!=database_before: raise AssertionError('Source MBSE database changed during proof')
    for relative,entry in hashes.items():
        if digest(ROOT/relative)!=entry['original']: raise AssertionError('Engine source changed during proof')
    report={'primary_build_succeeded':True,'primary_build_file_count':len(primary_build_files),'primary_build_files_sha256':primary_build_files,'proof_build_file_count':len(proof_build_files),'proof_build_files_sha256':proof_build_files,'source_database_unchanged':True,'branch':branch,'commits_created':False,'live_mbse_modified':False,'source_database_sha256':digest(db),'metadata_only':True,'abstracts_or_full_text_exported':False,'database_edges_total':connection_edge_count,'unmatched_endpoint_edges_excluded':connection_edge_count-len(edges),'engine_files':hashes,'identical_engine_source':True,'config_sha256':digest(engine/'mbse-config.json'),'counts':manifest['counts'],'build_succeeded':True,'build_base':'/mbse/','proof_manifest':str(engine/'data/mbse-proof/manifest.json'),'proof_dist':str(engine/'site/dist')}
    write(engine/'PROOF.json',report); print(json.dumps(report,indent=2)); return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--worktree',required=True); parser.add_argument('--db',default=str(ROOT.parent/'mbse/data/corpus.db')); args=parser.parse_args(); run(args.worktree,args.db)
