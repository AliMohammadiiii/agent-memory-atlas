#!/usr/bin/env python3
"""Load existing runtime credentials into memory and start private MCP stdio."""
import http.cookiejar,json,os,subprocess,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'server'),str(root/'scripts')]
raw=subprocess.check_output(['systemctl','show-environment'],text=True)
for line in raw.splitlines():
 if line.startswith('JINA_API_KEY='):os.environ['JINA_API_KEY']=line.split('=',1)[1]
container=json.loads(subprocess.check_output(['docker','inspect','9router-private']))[0];env=dict(x.split('=',1) for x in container['Config']['Env'] if '=' in x)
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path,body=None):
 req=urllib.request.Request('http://localhost:20128'+path,data=json.dumps(body).encode() if body else None,headers={'Content-Type':'application/json'})
 with opener.open(req,timeout=20) as response:return json.load(response)
call('/api/auth/login',{'password':env['INITIAL_PASSWORD']});keys=[r for r in call('/api/keys').get('keys',[]) if r.get('name')=='agent-memory-atlas-research' and isinstance(r.get('key'),str) and len(r['key'])>24]
if keys:os.environ['ATLAS_NINEROUTER_API_KEY']=keys[-1]['key']
os.environ.update(ATLAS_ROUTER_URL='http://localhost:20128',ATLAS_CONFIG_PATH=str(root/'config/gateway.yaml'),ATLAS_FULLTEXT_DIR='/var/lib/agent-memory-atlas/private/fulltext-rag-2026-11-02',ATLAS_FULLTEXT_RIGHTS='/var/lib/agent-memory-atlas/private/review-2026-11-02/RIGHTS.private.json')
# Prefer the published strict snapshot when it exists; explicit client overrides still win.
strict=Path('/opt/agent-memory-atlas-strict-20261102/data/snapshot-2026-11-02-strict-facets')
if strict.exists():os.environ.setdefault('ATLAS_MCP_SNAPSHOT',str(strict))
from atlas_mcp import main
main()
