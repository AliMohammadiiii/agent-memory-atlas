import unittest
from context_citation_edges import merge


class ContextEdgeTests(unittest.TestCase):
    def test_resolved_overlap_deduplicates_and_replay_is_identical(self):
        papers=[{'id':'a','tier':'CORE'},{'id':'b','tier':'ADJACENT'},{'id':'c','tier':'CORE'}]
        contexts={'resolved_citation_edges':[['a','b'],['c','b'],['c','b']]}
        edges,receipt=merge([['a','b']],papers,contexts)
        self.assertEqual(edges,[('a','b'),('c','b')])
        self.assertEqual((edges,receipt),merge(edges,papers,contexts))

    def test_excluded_paper_cannot_enter_graph_via_context(self):
        with self.assertRaisesRegex(AssertionError,'identity'):
            merge([],[{'id':'a','tier':'CORE'},{'id':'b','tier':'EXCLUDE'}],{'resolved_citation_edges':[['a','b']]})
