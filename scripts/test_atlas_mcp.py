import io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from atlas_mcp import AtlasMCP,excerpt,response,TOOLS

class FakeIndex:
 paper_ids={'fixture-a'}
 def retrieve(self,query,selected,semantic_papers,rerank):
  if 'fixture-a' not in selected:return [],{'mode':'fulltext_hybrid'}
  return [{'paper_id':'fixture-a','title':'Synthetic paper','page':3,'span':' '.join('word'+str(i) for i in range(80))}],{'mode':'fulltext_hybrid'}
class FakeGateway:
 def __init__(self,*a,fulltext=None,**k):self.fulltext=fulltext;self.papers={'fixture-a':{'id':'fixture-a','title':'Synthetic paper','tier':'CORE','dois':[],'arxiv_ids':[]},'fixture-b':{'id':'fixture-b','title':'Second synthetic paper','tier':'ADJACENT','dois':[],'arxiv_ids':[]}}
 def search(self,q,limit=20,paper_ids=None,filters=None,mode=None):return {'results':[{'id':p,'score':1.0} for p in (paper_ids or ['fixture-a']) if p in self.papers][:limit],'mode':'lexical'}
 def rerank(self,*a):raise RuntimeError('fixture')
 def ask(self,*a,**k):return {'grounded':False,'sources':[],'answer':'No support.'}
class MCPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'papers-index.json').write_text(json.dumps([{'id':'fixture-a','title':'Synthetic paper','link':'https://example.org/a'},{'id':'fixture-b','title':'Second synthetic paper'}]));(self.root/'manifest.json').write_text(json.dumps({'atlas':{'researchFacets':[{'id':'scope','size':1}]}}));(self.root/'matrix.json').write_text(json.dumps({'rows':{'fixture-a':{'cells':{'scope':{'quote':' '.join('token'+str(i) for i in range(40))}}}}}));(self.root/'graph.json').write_text(json.dumps({'edges':[{'source':'fixture-a','target':'fixture-b','type':'citation','weight':2}]}))
  with patch('atlas_mcp.Gateway',FakeGateway):self.service=AtlasMCP(self.root,self.root,self.root,fulltext=FakeIndex())
 def tearDown(self):self.tmp.cleanup()
 def test_initialize_and_list_tools(self):
  x=response({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},self.service);self.assertEqual(x['result']['protocolVersion'],'2025-06-18');self.assertEqual(len(response({'id':2,'method':'tools/list'},self.service)['result']['tools']),len(TOOLS));self.assertIsNone(response({'method':'notifications/initialized'},self.service))
 def test_graph_and_facet_information(self):
  x=self.service.call('graph_neighbours',{'paper_id':'fixture-a'});self.assertEqual(x['neighbours'][0]['paper_id'],'fixture-b');self.assertEqual(self.service.call('list_research_facets',{})['facets'][0]['id'],'scope')
 def test_private_excerpts_and_matrix_quotes_are_bounded(self):
  self.service.allowed_fulltext={'fixture-a'}
  x=self.service.call('retrieve_fulltext',{'query':'word35','paper_id':'fixture-a','limit':1});self.assertEqual(x['results'][0]['page'],3);self.assertLessEqual(len(x['results'][0]['excerpt'].split()),25);self.assertIn('word35',x['results'][0]['excerpt']);self.assertLessEqual(len(self.service.call('paper_details',{'paper_id':'fixture-a'})['matrix']['cells']['scope']['quote'].split()),25)
 def test_private_text_fails_closed_without_permission(self):
  self.service.allowed_fulltext=set()
  self.assertEqual(self.service.call('retrieve_fulltext',{'query':'memory'})['results'],[])
  self.assertFalse(self.service.call('paper_details',{'paper_id':'fixture-a'})['fulltext_indexed'])
  self.assertFalse(self.service.call('ask_literature',{'question':'memory'})['grounded'])
 def test_unknown_paper_and_bad_limit_cannot_expand_scope(self):
  for args in ({'query':'memory','paper_id':'missing'},{'query':'memory','limit':6}):
   with self.assertRaises(ValueError):self.service.call('retrieve_fulltext',args)
 def test_protocol_tool_error_is_coarse_and_no_private_data_leaks(self):
  x=response({'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'retrieve_fulltext','arguments':{'query':'memory','paper_id':'not-real'}}},self.service);self.assertTrue(x['result']['isError']);self.assertNotIn('not-real',json.dumps(x))
if __name__=='__main__':unittest.main()
