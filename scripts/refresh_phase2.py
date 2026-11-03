#!/usr/bin/env python3
"""Acquire a new dated snapshot; never overwrite a prior private snapshot."""
import os
import subprocess
import sys
from datetime import datetime, timezone

from resolve_seeds import ROOT
from server_runtime import private_root


def main():
    timestamp = datetime.now(timezone.utc)
    snapshot = os.environ.get('ATLAS_SNAPSHOT_ID') or timestamp.strftime('%Y-%m-%d-phase2-%H%M%S')
    from server_runtime import phase2_config
    environment = dict(os.environ, ATLAS_SNAPSHOT_ID=snapshot, ATLAS_CACHE_NAMESPACE=snapshot,
        ATLAS_SNAPSHOT_CUTOFF=os.environ.get('ATLAS_SNAPSHOT_CUTOFF', timestamp.date().isoformat()))
    os.environ['ATLAS_SNAPSHOT_ID'] = snapshot
    phase2_config()  # Validate before using the id as a path.
    if (private_root()/snapshot).exists() or (ROOT/'data'/('snapshot-'+snapshot)).exists():
        raise RuntimeError('Snapshot already exists; select a new dated ATLAS_SNAPSHOT_ID')
    subprocess.run([sys.executable, str(ROOT/'scripts/phase2_collect.py'), '--prepare-screening'],
        env=environment, check=True, cwd=ROOT)
    print('New private snapshot: '+snapshot)
    print('Acquisition and vectors complete. Label and review its new frozen sample before screening or export.')


if __name__ == '__main__':
    main()
