import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from final_common import write_json
from evaluate_strict_facets import run

class Reviewer:
 def __init__(self):self.config={}
 def generate(self,system,payload,**kwargs):return {'reviews':[{'id':p['id'],'verdict':'supported','span':'t0','reason':'Explicit target.'} for p in payload['papers']]},{'model':'synthetic-independent'}
class StrictEvaluationTests(unittest.TestCase):
 def test_frozen_sample_and_withheld_evidence_are_reproducible(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);private=root/'private';review=root/'review';private.mkdir();review.mkdir()
   write_json(private/'papers.private.json',[{'id':'a','title':'A scoped memory paper','dois':[],'arxiv_ids':[],'abstract':None}])
   write_json(review/'facets/FACETS.private.json',{'rows':[{'paper_id':'a','tags':[{'facet':'scope','display_allowed':False,'evidence':{'id':'t0','field':'title','text':'A scoped memory paper'}}]}]})
   config={'name':'fixture','facet_ids':['scope'],'sample_size_per_facet':30,'seed':7,'labels':['supported','unsupported','uncertain'],'reviewer_route':'synthetic','uncertain_denominator_policy':'Model agreement only.'}
   write_json(root/'evaluation.json',config);write_json(root/'facets.json',{'facets':[{'id':'scope','definition':'Context-dependent memory.'}]})
   with patch('evaluate_strict_facets.Model',Reviewer):run(private,review,root/'evaluation.json',root/'facets.json')
   first=(review/'evaluation/FACET-EVALUATION.public.json').read_bytes()
   with patch('evaluate_strict_facets.Model',Reviewer):run(private,review,root/'evaluation.json',root/'facets.json')
   self.assertEqual(first,(review/'evaluation/FACET-EVALUATION.public.json').read_bytes());result=json.loads(first);self.assertEqual(result['counts']['scope']['sample'],1);self.assertEqual(result['counts']['scope']['confirmed_fraction'],1);self.assertIsNone(result['samples'][0]['records'][0]['classifier_quote'])
if __name__=='__main__':unittest.main()
