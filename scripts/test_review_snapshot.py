import json,tempfile,unittest,sqlite3
from pathlib import Path
from build_pdf_receipt_update import write,inventory
from build_review_snapshot import build

class ReviewSnapshotTests(unittest.TestCase):
 def test_private_quote_withheld_and_rebuild_deterministic(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'parent';o=root/'out';v=root/'private';p.mkdir();v.mkdir()
   write(p/'manifest.json',{'snapshot':{'id':'old'},'atlas':{},'counts':{},'limitations':[],'files':{}})
   write(p/'papers-index.json',[{'id':'p','cluster_id':0}]);write(p/'graph.json',{'method':{},'clusters':[{'id':0,'label':'old','evidence_titles':['A','B','C','D','E'],'evidence_ids':['a','b','c','d','e']}],'nodes':[{'id':'p','cluster_id':0}]})
   write(p/'matrix.json',{'method':{},'coverage':{},'rows':{'p':{'cells':{}},'legacy':{'cells':{'other':{'value':'yes','quote':' '.join(['word']*26),'display_allowed':True}}}}});write(p/'fulltext-receipt.json',{});write(p/'fulltext-rag.json',{});write(p/'diff.json',{})
   write(v/'RIGHTS.private.json',[{'paper_id':'p','private_processing_allowed':True}]);idx=root/'fulltext-rag-2026-11-02';idx.mkdir();db=sqlite3.connect(idx/'index.sqlite');db.execute('create table papers (paper_id text)');db.execute("insert into papers values ('p')");db.commit();db.close()
   write(v/'facets/FACETS.private.json',{'facets':[{'id':'scope','label':'Scope','definition':'context'}],'counts':{'scope':1},'untagged':0,'rows':[{'paper_id':'p','tags':[{'facet':'scope','display_allowed':False,'evidence':{'field':'abstract','text':'private abstract'},'model':'model'}]}]})
   write(v/'facets/PLAIN-LABELS.private.json',{'labels':{'0':'Plain label'},'evidence':[{'id':0,'titles':['A','B','C','D','E'],'top_terms':['memory']}],'provenance':{'model':'fixture'}})
   write(v/'stability/STABILITY-REPORT.json',{'seeds':[1,2], 'pair_count':1,'comparison':[], 'interpretation':'Exploratory.'})
   cell={'value':'yes','quote':'private source quote','display_allowed':False,'location':{'page':1},'model':'model'}
   write(v/'matrix-v3/MATRIX.private.json',{'summary':{'assessed_core_papers':1,'eligible_core_papers':1},'rows':{'p':{'paper_id':'p','cells':{'scope':cell},'rights_evidence':['private rights text']}}})
   write(root/'overrides.json',{'exclusions':[]});before=inventory(p);build(p,o,v,overrides_path=root/'overrides.json');first=inventory(o);build(p,o,v,overrides_path=root/'overrides.json')
   self.assertEqual(first,inventory(o));self.assertEqual(before,inventory(p))
   paper=json.loads((o/'papers-index.json').read_text())[0];self.assertIsNone(paper['facet_evidence'][0]['quote'])
   matrix=json.loads((o/'matrix.json').read_text());self.assertIsNone(matrix['rows']['p']['cells']['scope']['quote']);self.assertTrue(matrix['rows']['p']['cells']['scope']['quote_withheld'])
   self.assertNotIn('private rights text',(o/'matrix.json').read_text());self.assertIsNone(matrix['rows']['legacy']['cells']['other']['quote'])

if __name__=='__main__':unittest.main()
