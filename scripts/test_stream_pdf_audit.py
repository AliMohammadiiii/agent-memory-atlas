import unittest
from stream_pdf_audit import identity

class IdentityTests(unittest.TestCase):
    def test_frontmatter_title(self):
        r=identity({'title':'Scoped revision of agent memory'},['Scoped revision of agent memory\nAbstract\nUnrelated body'])
        self.assertEqual(r['identity_status'],'title_match')
    def test_wrong_document_stays_unresolved(self):
        r=identity({'title':'Scoped revision of agent memory','arxiv_id':'2401.01234'},['A different article\narXiv:2401.99999\nAbstract'])
        self.assertEqual(r['identity_status'],'identity_review_required')
    def test_correct_identifier_is_not_enough(self):
        r=identity({'title':'Scoped revision of agent memory','arxiv_id':'2401.01234'},['Wrong title\narXiv:2401.01234\nAbstract'])
        self.assertEqual(r['identity_status'],'identity_review_required')
    def test_smallcaps_spacing_and_line_hyphen(self):
        r=identity({'title':'Memory Revision'},['M E M O R Y R E V I-\nS I O N\nAbstract'])
        self.assertEqual(r['identity_status'],'title_match')
    def test_title_in_body_does_not_establish_identity(self):
        r=identity({'title':'Scoped revision of agent memory'},['A different article\nAbstract\nScoped revision of agent memory'])
        self.assertEqual(r['identity_status'],'identity_review_required')
