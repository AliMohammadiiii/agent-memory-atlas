import io
import json
import os
from urllib.parse import urlsplit
from unittest.mock import patch
import unittest
import router_client


class RouterRestrictionTests(unittest.TestCase):
    def exercise(self,ignore_restriction=False,primary='cx/primary',connection='fixture-provider'):
        puts=[];access={};credential='synthetic-client-credential-00000000'
        class Opener:
            def open(self,request,timeout):
                path=urlsplit(request.full_url).path;method=request.get_method()
                body=json.loads(request.data) if request.data else None
                if path=='/api/auth/login':result={}
                elif path=='/api/providers':result={'connections':[{'provider':connection,'isActive':True}]}
                elif path=='/api/keys' and method=='GET':result={'keys':[{'id':'old','name':'agent-memory-atlas-research'},{'id':'other','name':'other-app'}]}
                elif path=='/api/keys' and method=='POST':
                    assert set(body)=={'name'}
                    result={'id':'new','key':credential}
                elif method=='PUT':
                    puts.append((path,body));access[path]=body['access'];result={}
                elif path=='/api/keys/new':result={'key':{'access':{} if ignore_restriction else access[path]}}
                else:raise AssertionError('Unexpected router request')
                return io.BytesIO(json.dumps(result).encode())
        container=[{'Config':{'Env':['INITIAL_PASSWORD=synthetic-test-only-password']}}]
        with patch.dict(os.environ,{'ATLAS_ROUTER_PROVIDER':'fixture-provider'},clear=True),patch.object(router_client.subprocess,'check_output',return_value=json.dumps(container).encode()),patch.object(router_client.urllib.request,'build_opener',return_value=Opener()):
            if connection != 'fixture-provider':
                with self.assertRaisesRegex(RuntimeError, 'no active router connection'):
                    router_client.prepare_router_key(primary, ['cx/fallback'])
                self.assertNotIn('ATLAS_NINEROUTER_API_KEY',os.environ)
                return puts
            if ignore_restriction:
                with self.assertRaisesRegex(RuntimeError,'restriction'):router_client.prepare_router_key('cx/primary',['cx/fallback'])
                self.assertNotIn('ATLAS_NINEROUTER_API_KEY',os.environ)
            else:
                router_client.prepare_router_key(primary,['cx/fallback'])
                self.assertEqual(os.environ['ATLAS_NINEROUTER_API_KEY'],credential)
        return puts

    def test_wrong_active_provider_is_rejected(self):
        self.assertEqual(self.exercise(connection='another-provider'), [])

    def test_provider_identity_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'provider identity'):
                router_client.prepare_router_key('cx/primary')

    def test_post_then_put_verifies_scope_and_preserves_other_app(self):
        puts=self.exercise()
        self.assertEqual([p for p,_ in puts],['/api/keys/old','/api/keys/new'])
        self.assertTrue(all(body['access']=={'restricted':True,'allow':['cx/primary','cx/fallback']} for _,body in puts))

    def test_unverified_scope_never_becomes_runtime_credential(self):
        self.exercise(ignore_restriction=True)

    def test_context_route_allows_its_canonical_capability_without_other_models(self):
        puts=self.exercise(primary='cx/primary[1m]')
        self.assertTrue(all(set(body['access']['allow'])=={'cx/primary[1m]','cx/primary','cx/fallback'} for _,body in puts))
