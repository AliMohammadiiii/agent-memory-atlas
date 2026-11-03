import tempfile
import unittest
from pathlib import Path
from check_public_files import violations


class PublicFileTests(unittest.TestCase):
    def test_private_downloaded_pdfs_cannot_enter_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'data/downloads-test/downloaded-fulltexts';folder.mkdir(parents=True)
            (folder/'fixture.pdf').write_bytes(b'%PDF-synthetic')
            self.assertIn('private full-text download copied inside engine',violations(root)[1][0]['reasons'])
    def test_secret_shape_is_rejected_without_environment_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'site.js').write_text('jina_' + 'x'*48)
            self.assertTrue(violations(root)[1])

    def test_ipv4_is_rejected_in_source_and_built_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); address = '.'.join(map(str, (203, 0, 113, 9)))
            (root / 'README.md').write_text(address)
            (root / 'site/dist').mkdir(parents=True)
            (root / 'site/dist/index.html').write_text(address)
            self.assertEqual(len(violations(root)[1]), 2)

    def test_configured_dns_host_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); hostname = 'private-' + 'fixture.example'
            (root / 'config.yaml').write_text(hostname)
            self.assertTrue(violations(root, 'worker@' + hostname)[1])

    def test_environment_reference_and_private_server_label_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('ATLAS_SERVER_HOST selects the private server.')
            self.assertFalse(violations(root)[1])

    def test_private_archive_is_forbidden_inside_engine_even_if_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data/raw').mkdir(parents=True)
            (root/'data/raw/fixture.body').write_text('Synthetic private response')
            self.assertTrue(violations(root)[1])
