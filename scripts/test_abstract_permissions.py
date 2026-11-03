import unittest
from abstract_permissions import bind_permissions


class PermissionBindingTests(unittest.TestCase):
    def test_license_on_different_abstract_cannot_authorize_selected_text(self):
        paper={'source_ids':{'s2':['x'],'openalex':['y']},'abstract':'Selected text.'}
        events=[{'provider':'s2','source_id':'x','abstract':'Selected text.','content_license_observations':[],'provenance':{}},
                {'provider':'openalex','source_id':'y','abstract':'Different text.','content_license_observations':['cc-by'],'provenance':{}}]
        bind_permissions([paper],events)
        self.assertFalse(paper['abstract_display_allowed'])

    def test_identical_text_with_explicit_permission_is_allowed(self):
        paper={'source_ids':{'s2':['x']},'abstract':'Exact text.'}
        events=[{'provider':'s2','source_id':'x','abstract':'Exact text.','content_license_observations':['cc-by-4.0'],'provenance':{'response_sha256':'synthetic'}}]
        bind_permissions([paper],events)
        self.assertTrue(paper['abstract_display_allowed'])
        self.assertTrue(paper['content_license_observations'][0]['matches_selected_abstract'])

    def test_missing_abstract_stays_withheld(self):
        paper={'source_ids':{'s2':['x']},'abstract':None}
        events=[{'provider':'s2','source_id':'x','abstract':None,'content_license_observations':['cc0'],'provenance':{}}]
        bind_permissions([paper],events)
        self.assertFalse(paper['abstract_display_allowed'])
