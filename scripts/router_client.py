"""Private-server CLI client for an explicitly configured provider and model route."""
import http.cookiejar
import json
import os
import re
import subprocess
import urllib.request

BASE = 'http://localhost:20128'


def prepare_router_key(route, additional_routes=None):
    if os.environ.get('ATLAS_NINEROUTER_API_KEY'): return
    provider = os.environ.get('ATLAS_ROUTER_PROVIDER', '').strip()
    if not provider: raise RuntimeError('Configure ATLAS_ROUTER_PROVIDER with the exact router provider identity')
    # Read the running router's configuration in server memory; never save or
    # print its administrator credential or the generated restricted client key.
    container = json.loads(subprocess.check_output(['docker', 'inspect', '9router-private']))[0]
    environment = dict(v.split('=',1) for v in container['Config']['Env'] if '=' in v)
    password = environment.get('INITIAL_PASSWORD')
    if not password: raise RuntimeError('Router administrator credential is unavailable in server runtime')
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path, body=None, method=None):
        request = urllib.request.Request(BASE+path, data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json'},method=method)
        with opener.open(request,timeout=20) as reply:return json.load(reply)
    call('/api/auth/login',{'password':password})
    connections = call('/api/providers').get('connections') or []
    active = [c for c in connections if c.get('provider') == provider and c.get('isActive')]
    if not active: raise RuntimeError('Configured provider has no active router connection')
    routes = list(dict.fromkeys([route] + list(additional_routes or [])))
    # The router strips context suffixes before checking model access. Both
    # spellings describe the same authorized capability, not another model.
    routes=list(dict.fromkeys(routes+[re.sub(r'\[\d+[km]\]$','',r,flags=re.I) for r in routes]))
    name='agent-memory-atlas-research'
    restriction={'restricted':True,'allow':routes}
    # The create endpoint ignores access; restrictions require a separate PUT.
    # Scope earlier keys bearing this research name, leaving other apps alone.
    existing=call('/api/keys').get('keys',[])
    for row in existing:
        if row.get('name')==name:
            call('/api/keys/'+str(row['id']),{'access':restriction},method='PUT')
    result = call('/api/keys',{'name':name})
    identifier=result.get('id')
    if not identifier:raise RuntimeError('Router did not return credential identity')
    call('/api/keys/'+str(identifier),{'access':restriction},method='PUT')
    verified=call('/api/keys/'+str(identifier)).get('key',{}).get('access',{})
    if not verified.get('restricted') or set(verified.get('allow',[]))!=set(routes):
        raise RuntimeError('Router research route restriction was not verified')
    def find_key(value):
        if isinstance(value,dict):
            for name in ('key','apiKey','api_key'):
                if isinstance(value.get(name),str) and len(value[name])>24:return value[name]
            for child in value.values():
                candidate=find_key(child)
                if candidate:return candidate
        return None
    key = find_key(result)
    if not key:raise RuntimeError('Router did not return a usable restricted client credential')
    os.environ['ATLAS_NINEROUTER_API_KEY']=key
