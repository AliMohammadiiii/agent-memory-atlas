#!/usr/bin/env python3
"""Select a fresh UTC snapshot, or explicitly resume unfinished work. Never publish."""
import argparse
from datetime import datetime, timezone, date
import json
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_site import load,write


def plan_refresh(private,public,config,snapshot=None,resume=False,previous=None,now=None):
    private,public=Path(private),Path(public)
    now=now or datetime.now(timezone.utc);today=now.astimezone(timezone.utc).date().isoformat()
    snapshot=snapshot or now.astimezone(timezone.utc).strftime('%Y-%m-%d-refresh-%H%M%S%f')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[A-Za-z0-9_-]+',snapshot):raise ValueError('Use a dated snapshot identifier without path separators')
    target=private/snapshot;frozen=set(config.get('parents',[]))
    pipeline=load(target/'PIPELINE.json',{})
    if snapshot in frozen or pipeline.get('status')=='complete':raise ValueError('Completed/approved snapshots are immutable; select a fresh identifier')
    if target.exists() and not resume:raise ValueError('Existing unfinished work requires explicit --resume')
    if resume and not target.exists():raise ValueError('Cannot resume a snapshot that does not exist')
    if (public/('snapshot-'+snapshot)).exists() and not resume:raise ValueError('Public snapshot already exists; select a fresh identifier')
    if (public/('snapshot-'+snapshot)/'manifest.json').exists() and not pipeline:raise ValueError('Public snapshot is frozen; cannot resume without unfinished private state')
    prior=load(target/'REFRESH-PLAN.json') if resume else None
    if prior:
        if previous and previous!=prior['previous_snapshot']:raise ValueError('Resume cannot change the recorded previous snapshot')
        cutoff=prior['cutoff'];previous=prior['previous_snapshot']
    else:
        completed=[]
        for path in public.glob('snapshot-*/manifest.json'):
            value=load(path,{});entry=value.get('snapshot',{})
            if isinstance(entry,dict) and entry.get('id')!=snapshot and entry.get('id'):completed.append((entry.get('date',''),entry['id']))
        previous=previous or (max(completed)[1] if completed else config.get('previous_snapshot') or config['parent_snapshot'])
        cutoff=(config.get('snapshot_cutoff',config['cutoff']) if snapshot==config.get('snapshot') else snapshot[:10]) if resume else today
    date.fromisoformat(cutoff)
    if previous==snapshot or not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[A-Za-z0-9_-]+',previous):raise ValueError('Invalid previous snapshot')
    return {'snapshot':snapshot,'cutoff':cutoff,'previous_snapshot':previous,'resume':resume,
        'acquisition_parent':config['parent_snapshot'],'seed_snapshot':config['seed_snapshot'],
        'scope':'Specialized original seed/gap/deferred contract is retained; previous snapshot is an additional frozen parent and diff baseline.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--snapshot');parser.add_argument('--previous');parser.add_argument('--resume',action='store_true');parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    from final_common import settings
    from server_runtime import private_root
    config=settings();private=private_root();plan=plan_refresh(private,ROOT/'data',config,args.snapshot,args.resume,args.previous)
    print(json.dumps(plan,sort_keys=True),flush=True)
    if args.dry_run:return
    folder=private/plan['snapshot'];folder.mkdir(exist_ok=True)
    if not args.resume:write(folder/'REFRESH-PLAN.json',plan)
    env=dict(os.environ,ATLAS_SNAPSHOT_ID=plan['snapshot'],ATLAS_SNAPSHOT_CUTOFF=plan['cutoff'],ATLAS_PREVIOUS_SNAPSHOT=plan['previous_snapshot'],ATLAS_FRESH_REFRESH='0' if args.resume else '1')
    subprocess.run([sys.executable,str(ROOT/'scripts/run_final.py')],cwd=ROOT,env=env,check=True)

if __name__=='__main__':main()
