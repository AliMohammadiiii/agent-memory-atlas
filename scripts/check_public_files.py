#!/usr/bin/env python3
"""Build gate: private addresses, configured host and credentials must not ship."""
import ipaddress
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = re.compile(rb'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
KEY_TOKEN = re.compile(rb'(?:jina_[A-Za-z0-9_-]{24,}|s2k-[A-Za-z0-9_-]{20,}|sk-or-v1-[a-fA-F0-9]{32,})')
SKIP = {'__pycache__', '.git', 'node_modules'}


def violations(root, host=None):
    failures = []; checked = 0
    host = host or os.environ.get('ATLAS_SERVER_HOST', '')
    host_values = {host, host.rsplit('@', 1)[-1]} - {''}
    keys = [v.encode() for k in ('JINA_API_KEY', 'S2_API_KEY', 'OPENALEX_API_KEY',
        'OPENROUTER_API_KEY', 'ATLAS_NINEROUTER_API_KEY') if (v := os.environ.get(k))]
    for file in sorted(Path(root).rglob('*')):
        rel = file.relative_to(root)
        if any(part in SKIP for part in rel.parts) or not file.is_file(): continue
        checked += 1; body = file.read_bytes()
        forbidden_address = False
        for token in ADDRESS.findall(body):
            try: ipaddress.IPv4Address(token.decode()); forbidden_address = True
            except ipaddress.AddressValueError: pass
        reasons = []
        if 'downloaded-fulltexts' in rel.parts:
            reasons.append('private full-text download copied inside engine')
        if len(rel.parts) >= 2 and rel.parts[:2] in (('data', 'raw'), ('data', 'private')): reasons.append('private archive copied inside engine')
        if forbidden_address: reasons.append('IPv4 address')
        if any(h.encode().lower() in body.lower() for h in host_values): reasons.append('configured private host')
        if any(key in body for key in keys): reasons.append('configured API credential')
        if KEY_TOKEN.search(body): reasons.append('API credential-shaped token')
        if reasons: failures.append({'file': str(rel), 'reasons': reasons})
    return checked, failures


if __name__ == '__main__':
    if not os.environ.get('ATLAS_SERVER_HOST'):
        raise SystemExit('ATLAS_SERVER_HOST is required for public-file validation')
    checked, failures = violations(ROOT)
    print(json.dumps({'files_checked': checked, 'violations': failures}, sort_keys=True))
    raise SystemExit(bool(failures))
