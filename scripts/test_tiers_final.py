"""Tier schema regression tests; no model or credential use."""
import ast
from pathlib import Path
import unittest


class TierSchemaTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse(Path(__file__).with_name('tiers_final.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='valid_decision')
        namespace={'source_spans':lambda paper:['Exact supplied scope span.']}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'tiers_schema','exec'),namespace)
        self.validate=namespace['valid_decision']

    def test_missing_optional_quote_preserves_model_judgment(self):
        row=self.validate({'tier':'CORE','reason':'Persistent memory is the contribution.','evidence_span':None},{})
        self.assertEqual(row['tier'],'CORE')
        self.assertEqual(row['evidence_quote'],'')
        self.assertEqual(row['evidence_quote_status'],'not_supplied')

    def test_invalid_pointer_is_withheld_never_invented(self):
        row=self.validate({'tier':'ADJACENT','reason':'Direct method anchor.','evidence_span':999},{})
        self.assertEqual(row['evidence_quote'],'')
        self.assertEqual(row['evidence_quote_status'],'invalid_span_withheld')

    def test_verified_pointer_uses_exact_source(self):
        row=self.validate({'tier':'CORE','reason':'Persistent memory.','evidence_span':0},{})
        self.assertEqual(row['evidence_quote'],'Exact supplied scope span.')
        self.assertEqual(row['evidence_quote_status'],'verified_span')

    def test_required_tier_and_reason_remain_required(self):
        self.assertIsNone(self.validate({'tier':'UNCERTAIN','reason':'Unknown'},{}))
        self.assertIsNone(self.validate({'tier':'CORE'},{}))


if __name__=='__main__':unittest.main()
