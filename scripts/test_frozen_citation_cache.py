"""A missing frozen response must never masquerade as a citation coverage gap."""
import ast
import os
from pathlib import Path
import unittest
from unittest.mock import patch


class FrozenCitationCacheTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse(Path(__file__).with_name('vectors_final.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='require_cache_hit')
        namespace=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='bind_snapshot_namespace')
        scope={'os':os,'read_json':lambda path:{'cache_namespace':'frozen-snapshot'}}
        exec(compile(ast.Module(body=[function,namespace],type_ignores=[]),'cache_gate','exec'),scope)
        self.check=scope['require_cache_hit']
        self.bind=scope['bind_snapshot_namespace']

    def test_offline_miss_fails_instead_of_publishing_partial_citations(self):
        with self.assertRaisesRegex(RuntimeError,'missing'):
            self.check({'status':0,'error':'cache_miss'},True)

    def test_archived_rate_limit_remains_a_real_acquisition_gap(self):
        self.check({'status':429,'error':None,'response_sha256':'synthetic'},True)
        self.check({'status':200,'data':[]},True)

    def test_unset_namespace_uses_acquisition_receipt(self):
        with patch.dict(os.environ,{},clear=True):
            self.bind(Path('synthetic'),True)
            self.assertEqual(os.environ['ATLAS_CACHE_NAMESPACE'],'frozen-snapshot')

    def test_wrong_namespace_fails_before_any_api_replay(self):
        with patch.dict(os.environ,{'ATLAS_CACHE_NAMESPACE':'wrong'},clear=True):
            with self.assertRaisesRegex(RuntimeError,'differs'):self.bind(Path('synthetic'),True)
