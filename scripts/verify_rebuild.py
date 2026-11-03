#!/usr/bin/env python3
"""Run required checks and compare two complete cache-only checkpoint builds."""
import hashlib
import json
import re
import subprocess
import sys

from resolve_seeds import ROOT, stable_json
from server_runtime import phase2_config


def run(command):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    print(result.stdout, end='', flush=True)
    print(result.stderr, end='', file=sys.stderr, flush=True)
    result.check_returncode()
    return result


def main():
    config = phase2_config()
    tests = run(['make', 'test', 'PYTHON='+sys.executable])
    number = re.search(r'Ran (\d+) tests?', tests.stderr)
    run(['make', 'build', 'PYTHON='+sys.executable])
    manifest = ROOT/'data'/('snapshot-'+config['snapshot'])/'FILES.sha256.json'
    first = manifest.read_bytes()
    run(['make', 'build', 'PYTHON='+sys.executable])
    second = manifest.read_bytes()
    if first != second:
        raise RuntimeError('Same snapshot did not produce byte-identical exported files')
    result = {'snapshot': config['snapshot'], 'tests_passed': int(number[1]) if number else None,
        'cache_only_builds': 2, 'byte_identical_export': True,
        'artifact_manifest_sha256': hashlib.sha256(second).hexdigest(),
        'publication_performed': False}
    (ROOT/'docs/CHECKPOINT2-VERIFICATION.json').write_bytes(stable_json(result))
    run([sys.executable, 'scripts/check_public_files.py'])
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
