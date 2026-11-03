import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from report_phase2 import evidence_counts, public_paper
from server_runtime import phase2_config
from resolve_seeds import Cache


class Phase2ExportTests(unittest.TestCase):
    def test_refresh_cache_namespace_preserves_older_request_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'ATLAS_CACHE_NAMESPACE': '2026-11-01-fixture'}):
                first = Cache(Path(directory), offline=True).request('openalex', '/fixture', {})
            with patch.dict(os.environ, {'ATLAS_CACHE_NAMESPACE': '2026-11-02-fixture'}):
                second = Cache(Path(directory), offline=True).request('openalex', '/fixture', {})
            self.assertNotEqual(first['request_hash'], second['request_hash'])

    def test_abstract_text_cannot_enter_metadata_export(self):
        secret_text = 'PRIVATE ABSTRACT FIXTURE'
        result = public_paper({'id': 'synthetic', 'title': 'Synthetic title',
            'abstract': secret_text, 'abstract_available': True, 'abstract_display_allowed': True,
            'seed_ids': ['A03']})
        self.assertNotIn(secret_text, json.dumps(result))
        self.assertFalse(result['abstract_display_allowed'])
        self.assertEqual(result['owner_approved_alias_flags'], ['A03'])

    def test_evidence_counts_partition_the_records(self):
        result = evidence_counts([{'evidence_level': 'abstract'}, {'evidence_level': 'metadata_only'}])
        self.assertEqual(sum(result.values()), 2)

    def test_snapshot_selection_does_not_edit_shared_config(self):
        with patch.dict(os.environ, {'ATLAS_SNAPSHOT_ID': '2026-11-02-phase2-fixture',
                'ATLAS_SNAPSHOT_CUTOFF': '2026-11-02'}):
            config = phase2_config()
            self.assertEqual(config['snapshot'], '2026-11-02-phase2-fixture')
            self.assertEqual(config['cutoff'], '2026-11-02')
        with patch.dict(os.environ, {'ATLAS_SNAPSHOT_ID': '../escape'}):
            with self.assertRaises(ValueError):
                phase2_config()

    def test_refresh_refuses_to_overwrite_existing_snapshot_before_requests(self):
        import refresh_phase2
        snapshot = '2026-11-01-phase2-fixture'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/snapshot).mkdir()
            with patch.dict(os.environ, {'ATLAS_SNAPSHOT_ID': snapshot}), \
                 patch('refresh_phase2.private_root', return_value=folder), \
                 patch('refresh_phase2.subprocess.run') as request:
                with self.assertRaises(RuntimeError):
                    refresh_phase2.main()
                request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
