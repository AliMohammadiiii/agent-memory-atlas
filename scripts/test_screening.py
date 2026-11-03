import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from phase2_screen import Judge, agreement, select_threshold, threshold_metrics, validate_manual_labels


class ScreeningTests(unittest.TestCase):
    def test_invalid_quote_retries_only_invalid_item_and_preserves_valid_provenance(self):
        papers = [{'id': 'synthetic-a', 'title': 'Memory alpha', 'abstract': 'Persistent memory.'},
                  {'id': 'synthetic-b', 'title': 'Memory beta', 'abstract': 'Stored facts via ℬ.'}]
        good = {'id': 'synthetic-a', 'label': 'include', 'reason': 'Direct storage.', 'evidence_quote': 'Persistent memory.'}
        bad = {'id': 'synthetic-b', 'label': 'include', 'reason': 'Direct storage.', 'evidence_quote': 'Invented sentence.'}
        fixed = {**bad, 'evidence_span': 1, 'evidence_quote': 'Stored facts via ℂ.'}
        def reply(rows, digest):
            return {'status': 200, 'data': {'model': 'synthetic-model', 'choices': [
                {'message': {'content': json.dumps({'decisions': rows})}}]},
                'response_sha256': digest, 'retrieved_at': 'synthetic-date'}
        judge = Judge.__new__(Judge)
        judge.config = {'inclusion_definition': 'Persistent agent memory'}
        judge.settings = {'abstract_input_max_chars': 12000, 'primary_gateway': '9router',
            'primary_model': 'synthetic-model', 'fallback_gateway': 'none', 'fallback_model': 'none',
            'minimum_seconds_between_requests': 0, 'batch_output_tokens': 500}
        judge.last = 0
        judge.cache = Mock()
        judge.cache.request.side_effect = [reply([good,bad], 'first-response'), reply([fixed], 'repair-response')]
        with tempfile.TemporaryDirectory() as directory:
            judge.cache_dir = Path(directory)
            output = judge.batch(papers)
            self.assertEqual(output['synthetic-a']['response_sha256'], 'first-response')
            self.assertEqual(output['synthetic-b']['response_sha256'], 'repair-response')
            self.assertEqual(output['synthetic-b']['evidence_quote'], 'Stored facts via ℬ.')
            self.assertTrue((judge.cache_dir/(judge.key(papers[0])+'.json')).exists())
        second = judge.cache.request.call_args_list[1].kwargs['body']['messages'][1]['content']
        self.assertEqual([r['id'] for r in json.loads(second)], ['synthetic-b'])

    def test_threshold_uses_recall_constraint_and_precision_then_highest_tie(self):
        threshold, metrics = select_threshold([.1, .3, .4, .8], ['exclude', 'include', 'exclude', 'include'])
        self.assertEqual(threshold, .3)
        self.assertEqual(metrics['recall'], 1)
        self.assertAlmostEqual(metrics['precision'], 2/3)

    def test_uncertain_is_not_a_negative(self):
        result = threshold_metrics([.9, .1, .2], ['include', 'exclude', 'uncertain'], .5)
        self.assertEqual(result['decidable_items'], 2)
        self.assertEqual((result['tp'], result['tn'], result['fp'], result['fn']), (1, 1, 0, 0))

    def test_three_class_agreement_and_kappa(self):
        result = agreement(['include', 'exclude', 'uncertain'], ['include', 'uncertain', 'uncertain'])
        self.assertAlmostEqual(result['agreement'], 2/3)
        self.assertAlmostEqual(result['cohen_kappa'], .5)

    def test_manual_quote_cannot_be_fabricated(self):
        paper = {'id': 'synthetic', 'title': 'Agent memory', 'abstract': 'Persistent storage.'}
        row = {'id': 'synthetic', 'label': 'include', 'rationale': 'Direct memory method.',
               'evidence_quote': 'Persistent storage.',
               'source_text_sha256': hashlib.sha256(b'Agent memory\n\nPersistent storage.').hexdigest()}
        validate_manual_labels([row], [paper])
        with self.assertRaises(ValueError):
            validate_manual_labels([{**row, 'evidence_quote': 'Invented evidence.'}], [paper])

    def test_cache_key_changes_with_source_text_or_model(self):
        judge = Judge.__new__(Judge)
        judge.config = {'inclusion_definition': 'Persistent agent memory'}
        judge.settings = {'abstract_input_max_chars': 12000, 'primary_gateway': '9router',
                          'primary_model': 'synthetic-model', 'fallback_gateway': 'none', 'fallback_model': 'none'}
        paper = {'id': 'synthetic', 'title': 'Memory', 'abstract': 'Storage.'}
        initial = judge.key(paper)
        self.assertNotEqual(initial, judge.key({**paper, 'abstract': 'Revised storage.'}))
        judge.settings['primary_model'] = 'other-synthetic-model'
        self.assertNotEqual(initial, judge.key(paper))


if __name__ == '__main__':
    unittest.main()
