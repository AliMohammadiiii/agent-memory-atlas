"""Synthetic unit fixtures; these are never literature records."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.error
import io

from resolve_seeds import Cache, arxiv_from_record, select_candidate, stable_json


class ResolutionTests(unittest.TestCase):
    def test_retry_keeps_original_request_body(self):
        class Reply:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"ok":true}'
        transient = urllib.error.HTTPError('https://example.test', 429, 'rate limited', {}, io.BytesIO(b'{"error":"retry"}'))
        with tempfile.TemporaryDirectory() as directory:
            with patch('urllib.request.urlopen', side_effect=[transient, Reply()]) as network, patch('time.sleep'):
                result = Cache(Path(directory)).request('s2', '/paper/synthetic', {}, body={'ids': ['synthetic']})
                self.assertEqual(result['status'], 200)
                self.assertEqual(network.call_args_list[0].args[0].data, network.call_args_list[1].args[0].data)
    def test_arxiv_identifier_must_match(self):
        seed = {'arxiv_id': '2310.08560', 'input': 'MemGPT', 'group': 'C'}
        wrong = {'paperId': 'synthetic', 'title': 'MemGPT', 'externalIds': {'ArXiv': '0000.00000'}}
        self.assertIsNone(select_candidate([wrong], seed, 's2')[0])
        right = dict(wrong, externalIds={'ArXiv': '2310.08560v2'})
        self.assertEqual(arxiv_from_record(right, 's2'), '2310.08560')
        self.assertEqual(select_candidate([right], seed, 's2')[0], right)

    def test_title_search_never_accepts_approximate_hit(self):
        seed = {'arxiv_id': '', 'input': 'MemoryArena', 'group': 'C'}
        self.assertIsNone(select_candidate([{'title': 'An unrelated memory arena'}], seed, 's2')[0])
        ambiguous = [{'title': 'MemoryArena: synthetic one'}, {'title': 'MemoryArena: synthetic two'}]
        self.assertIsNone(select_candidate(ambiguous, seed, 's2')[0])

    def test_classic_title_prefix_is_explicitly_flagged(self):
        seed = {'arxiv_id': '', 'input': 'Reiter 1980 "A logic for default reasoning"', 'group': 'F'}
        record, note = select_candidate([{'title': 'A logic for default reasoning', 'year': 1980, 'authors': [{'name': 'Raymond Reiter'}]}], seed, 's2')
        self.assertIsNotNone(record)
        self.assertEqual(note, 'exact normalized title')

    def test_classic_author_and_year_constraints_reject_wrong_paper(self):
        seed = {'arxiv_id': '', 'input': 'Alchourron, Gardenfors, Makinson 1985 "On the Logic of Theory Change"', 'group': 'F'}
        wrong = {'title': 'On the Logic of Theory Change: Safe contraction', 'year': 1985, 'authors': [{'name': 'Alchourron'}, {'name': 'Makinson'}]}
        self.assertIsNone(select_candidate([wrong], seed, 's2')[0])
        right = {'title': 'On the Logic of Theory Change: Partial meet contraction and revision functions', 'year': 1985, 'authors': [{'name': 'Alchourron'}, {'name': 'Gardenfors'}, {'name': 'Makinson'}]}
        self.assertEqual(select_candidate([wrong, right], seed, 's2')[0], right)

    def test_provided_year_disambiguates_mquake_title_family(self):
        seed = {'arxiv_id': '', 'input': 'MQuAKE (Zhong et al., EMNLP 2023)', 'group': 'E'}
        wrong = {'title': 'MQUAKE multicast software', 'year': 2003, 'authors': []}
        right = {'title': 'MQuAKE: Assessing Knowledge Editing', 'year': 2023, 'authors': [{'name': 'Z Zhong'}]}
        self.assertEqual(select_candidate([wrong, right], seed, 's2')[0], right)

    def test_confirmed_shared_doi_retains_provider_identity_despite_year_difference(self):
        seed = {'arxiv_id': '', 'input': 'Reiter 1980 "A logic for default reasoning"', 'group': 'F'}
        record = {'title': 'A logic for default reasoning', 'year': 1981, 'externalIds': {'DOI': '10.synthetic/fixture'}}
        self.assertIsNone(select_candidate([record], seed, 's2')[0])
        self.assertEqual(select_candidate([record], seed, 's2', '10.synthetic/fixture')[0], record)

    def test_cache_only_never_calls_network(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                result = Cache(Path(folder), offline=True).request('s2', '/paper/synthetic', {'fields': 'title'})
                self.assertEqual(result['error'], 'cache_miss')

    def test_request_cache_contains_no_credentials(self):
        class Reply:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"paperId":"synthetic","title":"Synthetic test fixture"}'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.dict('os.environ', {'S2_API_KEY': 'synthetic-secret-do-not-store'}):
                with patch('urllib.request.urlopen', return_value=Reply()) as network:
                    first = Cache(root).request('s2', '/paper/synthetic', {'fields': 'title'})
                    second = Cache(root, offline=True).request('s2', '/paper/synthetic', {'fields': 'title'})
                    self.assertEqual(first, second)
                    self.assertEqual(network.call_count, 1)
            for file in root.rglob('*'):
                if file.is_file(): self.assertNotIn(b'synthetic-secret-do-not-store', file.read_bytes())
            manifests = [json.loads(p.read_text()) for p in (root / 'requests').glob('*.json')]
            self.assertEqual(manifests[0]['attempts'][0]['status'], 200)
            self.assertTrue(manifests[0]['attempts'][0]['retrieved_at'])
            self.assertEqual(stable_json(first), stable_json(second))


if __name__ == '__main__': unittest.main()
