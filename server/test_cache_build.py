import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parent))
from refresh_snapshot import plan_refresh
from rebuild_final_cache import move_derived,write_network_guard,frozen_cache_namespace,assert_frozen_citations

class CacheBuildTests(unittest.TestCase):
    def test_network_guard_records_attempts_without_addresses_and_preserves_pythonpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);guard=write_network_guard(root/'guard');receipt=root/'attempts';vendor=root/'vendor';vendor.mkdir();(vendor/'vendor_marker.py').write_text('present=True\n')
            code='import socket,vendor_marker\nfor f in [lambda:socket.socket().connect(("localhost",1)),lambda:socket.socket().connect_ex(("localhost",1)),lambda:socket.create_connection(("localhost",1))]:\n try:f()\n except RuntimeError:pass\nassert vendor_marker.present\n'
            result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(guard)+os.pathsep+str(vendor),ATLAS_NETWORK_GUARD_RECEIPT=str(receipt)),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(receipt.read_text(),'1\n1\n1\n')
            self.assertNotIn('localhost',receipt.read_text())
    def test_cleaning_moves_derived_but_preserves_acquisition_and_receipt_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'papers.private.json').write_text('derived');(root/'candidate_events.json').write_text('raw metadata');(root/'compute-receipts').mkdir();(root/'compute-receipts/a.json').write_text('frozen');backup=root/'backup';move_derived(root,backup)
            self.assertFalse((root/'papers.private.json').exists());self.assertEqual((backup/'papers.private.json').read_text(),'derived');self.assertEqual((root/'candidate_events.json').read_text(),'raw metadata');self.assertEqual((root/'compute-receipts/a.json').read_text(),'frozen')
    def test_refresh_default_uses_utc_fresh_id_and_never_changes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';public=root/'data';private.mkdir();public.mkdir();config={'snapshot':'2026-11-01-final','parent_snapshot':'2026-11-01-phase2','seed_snapshot':'2026-11-01-checkpoint-1','parents':['2026-11-01-phase2'],'cutoff':'2026-11-01'}
            now=datetime(2026,11,3,8,9,10,tzinfo=timezone.utc);plan=plan_refresh(private,public,config,now=now)
            self.assertTrue(plan['snapshot'].startswith('2026-11-03-refresh-'));self.assertEqual(plan['cutoff'],'2026-11-03');self.assertEqual(list(private.iterdir()),[])
            frozen=private/'2026-11-01-final';frozen.mkdir();(frozen/'PIPELINE.json').write_text('{"status":"complete"}')
            with self.assertRaisesRegex(ValueError,'immutable'):plan_refresh(private,public,config,'2026-11-01-final',resume=True,now=now)
    def test_refresh_resume_preserves_recorded_cutoff_and_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';public=root/'data';private.mkdir();public.mkdir();config={'snapshot':'2026-11-01-final','parent_snapshot':'2026-11-01-phase2','seed_snapshot':'2026-11-01-checkpoint-1','parents':[],'cutoff':'2026-11-01'}
            target=private/'2026-11-02-refresh-test';target.mkdir();(target/'REFRESH-PLAN.json').write_text(json.dumps({'cutoff':'2026-11-02','previous_snapshot':'2026-11-01-final'}))
            with self.assertRaisesRegex(ValueError,'explicit --resume'):plan_refresh(private,public,config,target.name)
            plan=plan_refresh(private,public,config,target.name,resume=True,now=datetime(2026,11,5,tzinfo=timezone.utc));self.assertEqual(plan['cutoff'],'2026-11-02');self.assertEqual(plan['previous_snapshot'],'2026-11-01-final')
            with self.assertRaisesRegex(ValueError,'cannot change'):plan_refresh(private,public,config,target.name,resume=True,previous='2026-11-03-other')
class FrozenReplayContractTests(unittest.TestCase):
    def test_namespace_uses_recorded_acquisition_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            with self.assertRaisesRegex(RuntimeError,'namespace'):frozen_cache_namespace(folder)
            (folder/'COLLECTION.json').write_text(json.dumps({'cache_namespace':'frozen-acquisition'}))
            self.assertEqual(frozen_cache_namespace(folder),'frozen-acquisition')

    def test_partial_or_substituted_citation_graph_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path=folder/'resolved_edges.json';expected={('a','b'),('a','c')}
            path.write_text(json.dumps([['a','b'],['a','c']]))
            assert_frozen_citations(folder,expected)
            for edges in ([['a','b']],[['a','b'],['b','c']]):
                path.write_text(json.dumps(edges))
                with self.assertRaisesRegex(RuntimeError,'frozen citation graph'):assert_frozen_citations(folder,expected)

if __name__=='__main__':unittest.main()
