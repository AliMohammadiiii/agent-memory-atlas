import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from final_common import write_json
from verify_strict_facets import run

class Verifier:
 def __init__(self):self.config={}
 def generate(self,system,payload,**kwargs):return {'papers':[{'id':p['id'],'decisions':[{'facet':x['facet'],'verdict':'supported' if x['facet']=='scope' else 'unsupported','span':'t0' if x['facet']=='scope' else None} for x in p['candidates']]} for p in payload['papers']]},{'model':'verifier-fixture'}
class StrictVerificationTests(unittest.TestCase):
 def test_only_supported_tag_survives_with_original_source_span(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source';original=root/'original';out=root/'verified';source.mkdir();original.mkdir()
   write_json(source/'papers.private.json',[{'id':'p','title':'A scoped memory system','dois':[],'arxiv_ids':[],'abstract':None}])
   tags=[{'facet':f,'evidence':{'id':'t0','field':'title','text':'A scoped memory system'},'model':'classifier-fixture'} for f in ('scope','temporal')]
   write_json(original/'facets/FACETS.private.json',{'rows':[{'paper_id':'p','tags':tags}]});write_json(original/'facets/PLAIN-LABELS.private.json',{})
   write_json(root/'config.json',{'batch_size':25,'verifier_route':'fixture','classifier_route':'fixture','interpretation':'model only'});write_json(root/'facets.json',{'facets':[{'id':'scope','definition':'Scoped memory'},{'id':'temporal','definition':'Expiry'}]})
   with patch('verify_strict_facets.Model',Verifier):run(source,original,out,root/'config.json',root/'facets.json')
   x=json.loads((out/'facets/FACETS.private.json').read_text());self.assertEqual(x['counts'],{'scope':1});self.assertEqual(x['verification_counts'],{'supported':1,'unsupported':1});self.assertEqual(x['rows'][0]['tags'][0]['evidence']['text'],'A scoped memory system');self.assertEqual(len(json.loads((original/'facets/FACETS.private.json').read_text())['rows'][0]['tags']),2)
if __name__=='__main__':unittest.main()
