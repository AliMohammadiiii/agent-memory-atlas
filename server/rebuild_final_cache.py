#!/usr/bin/env python3
"""Two clean scientific rebuilds from frozen caches; never model/network refresh.

Run only after the online final pipeline completes. Approved parents and raw,
model, vector, extraction and compute-receipt caches must remain byte-identical.
Frontend compilation is a separate local step when the server has no npm.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_site import build, load, write

DERIVED=('papers.private.json','redirects.json','resolved_edges.all.json','resolved_edges.json',
    'merge_events.json','duplicate_audit.json','suspected_duplicates.json','missing_arxiv_v1_dates.json',
    'DEDUPLICATION.json','TIER-REPORT.json','vector_manifest.json','vectors.float16.npy',
    'embedding_tier_agreement.json','analytics.private.json','matrix.private.json','benchmarks.private.json',
    's2_fix_report.json','deferred_resolution.json','citation_contexts.private.json','CITATION-CONTEXT-EDGES.json','ABSTRACT-PERMISSIONS.json','citation_enrichment.json')
REQUIRED=('COLLECTION.json','resolved_edges.json','candidate_events.json','citation_events.json','arxiv_dates.json','query_log.json',
    'acquisition_gaps.json','papers.private.json','analytics.private.json','matrix.private.json','benchmarks.private.json','citation_contexts.private.json')
STAGES=(('collect_final.py',()),('tiers_final.py',()),('vectors_final.py',()),
    ('citation_contexts_final.py',('--cache-only',)),('context_citation_edges.py',()),('analytics_final.py',('--cache-only',)),('extract_final.py',('--cache-only',)),('audit_final_inputs.py',()))


NETWORK_GUARD_SOURCE='import socket,os\ndef _record():\n with open(os.environ["ATLAS_NETWORK_GUARD_RECEIPT"],"a") as stream: stream.write("1\\n")\n_original_connect=socket.socket.connect\ndef _blocked(self,address):\n if self.family in (socket.AF_INET,socket.AF_INET6): _record(); raise RuntimeError("cache-only rebuild blocked network connection")\n return _original_connect(self,address)\nsocket.socket.connect=_blocked\nsocket.socket.connect_ex=_blocked\ndef _no_network(*args,**kwargs): _record(); raise RuntimeError("cache-only rebuild blocked network connection")\nsocket.create_connection=_no_network\n'

def write_network_guard(path):
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    (path/'sitecustomize.py').write_text(NETWORK_GUARD_SOURCE)
    return path


def digest_file(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def inventory(path):
    path=Path(path)
    if not path.exists():return {}
    if path.is_file():return {path.name:digest_file(path)}
    return {str(p.relative_to(path)):digest_file(p) for p in sorted(path.rglob('*')) if p.is_file()}


def receipt_inventory(value):
    return {'files':len(value),'inventory_sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()}


def move_derived(folder,destination):
    destination.mkdir(parents=True,exist_ok=True)
    for name in DERIVED:
        if (folder/name).exists():shutil.move(str(folder/name),str(destination/name))


def frozen_cache_namespace(folder):
    namespace=load(Path(folder)/'COLLECTION.json',{}).get('cache_namespace')
    if not isinstance(namespace,str) or not namespace.strip():
        raise RuntimeError('Frozen COLLECTION.json is missing cache_namespace')
    return namespace


def assert_frozen_citations(folder,expected):
    actual={tuple(edge) for edge in load(Path(folder)/'resolved_edges.json',[])}
    if actual!=expected:
        raise RuntimeError(f'Rebuilt frozen citation graph differs: {len(actual)} edges versus {len(expected)} expected')


def run(allow_ready=False,output=None,site_data=None):
    from final_common import settings
    from server_runtime import private_root
    from resolve_seeds import raw_root
    from run_final import parent_inventory
    config=settings(); private=private_root(); folder=private/config['snapshot']
    namespace=frozen_cache_namespace(folder)
    expected_citations={tuple(edge) for edge in load(folder/'resolved_edges.json',[])}
    missing=[name for name in REQUIRED if not (folder/name).exists()]
    if missing:raise RuntimeError('Final cache is incomplete; missing '+', '.join(missing))
    pipeline=load(folder/'PIPELINE.json',{})
    if pipeline and pipeline.get('status')!='complete' and not allow_ready:raise RuntimeError('Online pipeline is not complete; refusing to clear derived outputs')
    parents_before=parent_inventory()
    cache_paths=[raw_root(),private/'final-tier-cache',private/'final-model-cache',private/'embedding-cache']
    cache_paths.append(folder/'VECTOR-ACQUISITION.json')
    cache_paths += [folder/name for name in ('extraction-cache','cluster-label-cache','project-query-cache','compute-receipts','citation-context-cache')]
    caches_before={str(i):inventory(path) for i,path in enumerate(cache_paths)}
    frozen_inputs={name:digest_file(folder/name) for name in ('COLLECTION.json','candidate_events.json','citation_events.json','arxiv_dates.json','query_log.json','acquisition_gaps.json','gap_retries.json','seed_metadata.json') if (folder/name).exists()}
    initial={name:digest_file(folder/name) for name in DERIVED if (folder/name).exists()}
    work=Path(tempfile.mkdtemp(prefix='final-cache-rebuild-',dir=private));work.chmod(0o700)
    write(work/'CACHE-INVENTORIES.before.json',caches_before)
    # Guard the child process independently of each script's cache flags.
    guard=work/'network-guard'
    write_network_guard(guard)
    env=dict(os.environ,ATLAS_CACHE_NAMESPACE=namespace,ATLAS_CACHE_ONLY='1',ATLAS_RECOVER_KEYWORDS='0',ATLAS_NETWORK_GUARD_RECEIPT=str(work/'network-attempts.txt'),PYTHONPATH=str(guard)+(os.pathsep+os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else ''))
    move_derived(folder,work/'original-derived')
    runs=[]
    try:
        for iteration in (1,2):
            if iteration==2:move_derived(folder,work/'first-derived')
            for script,args in STAGES:
                command=[sys.executable,str(ROOT/'scripts'/script),*args]
                if script=='collect_final.py': command=[sys.executable,'-c','import sys; sys.path.insert(0,"scripts"); from collect_final import build_final_papers; build_final_papers()']
                subprocess.run(command,cwd=ROOT,env=env,check=True)
                if script=='context_citation_edges.py':assert_frozen_citations(folder,expected_citations)
                if frozen_inputs!={name:digest_file(folder/name) for name in frozen_inputs}:raise RuntimeError('A frozen acquisition input changed')
                if (work/'network-attempts.txt').exists():raise RuntimeError('A cache-only stage attempted a network connection')
                if parent_inventory()!=parents_before:raise RuntimeError('An approved parent changed during cache rebuild')
            public=work/('public-'+str(iteration)); static=work/('static-'+str(iteration))
            build(folder,public,config,ROOT/'data'/('snapshot-'+config['parent_snapshot']),static)
            subprocess.run([sys.executable,str(ROOT/'scripts/validate_final.py'),'--private',str(folder),'--public',str(public)],cwd=ROOT,env=env,check=True)
            shutil.rmtree(static)  # This is a duplicate static mirror; retain the compared public tree.
            runs.append({'derived':{name:digest_file(folder/name) for name in DERIVED if (folder/name).exists()},'public':inventory(public)})
        if runs[0]!=runs[1]:raise RuntimeError('Two clean scientific cache rebuilds differ')
        caches_after={str(i):inventory(path) for i,path in enumerate(cache_paths)}
        write(work/'CACHE-INVENTORIES.after.json',caches_after)
        if caches_before!=caches_after:raise RuntimeError('A frozen raw/model/vector/extraction/receipt cache changed')
        if parent_inventory()!=parents_before:raise RuntimeError('An approved parent changed during cache rebuild')
        output=Path(output or ROOT/'data'/('snapshot-'+config['snapshot']))
        site_data=Path(site_data or ROOT/'site/public/data')
        manifest=build(folder,output,config,ROOT/'data'/('snapshot-'+config['parent_snapshot']),site_data)
        result={'status':'passed','snapshot':config['snapshot'],'cache_namespace':namespace,'citation_edges':len(expected_citations),'frozen_citation_graph_unchanged':True,'scientific_builds':2,'network_guard':True,'network_attempts':0,
            'stages':[name for name,_ in STAGES]+['build_site.py','validate_final.py'],
            'parents_unchanged':True,'caches_unchanged':True,'acquisition_inputs_unchanged':True,'acquisition_replay':'Canonical deduplication from frozen acquisition-event/seed/arXiv caches; no rediscovery scheduling.','cache_inventories':{k:receipt_inventory(v) for k,v in caches_after.items()},
            'private_derived':receipt_inventory(runs[0]['derived']),'public':receipt_inventory(runs[0]['public']),
            'matches_frozen_derived_before':initial==runs[0]['derived'],'changed_derived_vs_before':sorted(k for k in set(initial)|set(runs[0]['derived']) if initial.get(k)!=runs[0]['derived'].get(k)),
            'counts':manifest['counts'],'frontend_build':'separate local make site step; not claimed by this receipt'}
        write(ROOT/'docs/FINAL-CACHE-REBUILD.json',result)
        shutil.rmtree(work)
        print(json.dumps(result,sort_keys=True));return result
    except BaseException:
        # Preserve failed derived artifacts privately, then restore prior final data.
        move_derived(folder,work/'failed-derived')
        for path in (work/'original-derived').iterdir():shutil.copy2(path,folder/path.name)
        write(work/'FAILURE.json',{'status':'failed','completed_builds':len(runs),'original_derived_restored':True,'parents_unchanged':parent_inventory()==parents_before})
        print(json.dumps({'status':'failed','original_derived_restored':True,'private_failure_directory':str(work)}),file=sys.stderr)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--allow-ready',action='store_true',help='Use only when final caches are complete and the online pipeline is stopped');parser.add_argument('--out');parser.add_argument('--site-data');args=parser.parse_args();run(args.allow_ready,args.out,args.site_data)
