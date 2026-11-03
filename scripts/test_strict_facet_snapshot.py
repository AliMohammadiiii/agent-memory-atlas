import gzip,json,tempfile,unittest
from pathlib import Path
from build_pdf_receipt_update import write,inventory
from build_strict_facet_snapshot import build,public_facets

class StrictSnapshotTests(unittest.TestCase):
 def test_unconfirmed_sample_tags_are_removed_without_changing_audit(self):
  facets={'rows':[{'paper_id':'a','tags':[{'facet':'scope'},{'facet':'temporal'}]}]};evaluation={'samples':[{'facet':'scope','records':[{'paper_id':'a','verdict':'uncertain'}]}]}
  rows,counts,untagged,removed=public_facets(facets,evaluation)
  self.assertEqual(counts,{'temporal':1});self.assertEqual(removed,1);self.assertEqual(untagged,0);self.assertEqual(len(facets['rows'][0]['tags']),2)
 def test_warnings_are_preserved_and_rebuild_is_deterministic(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);parent=root/'parent';out=root/'out';private=root/'private';parent.mkdir();private.mkdir()
   write(parent/'manifest.json',{'snapshot':{'id':'prior'},'atlas':{},'counts':{},'limitations':['Exact prior warning.'],'files':{}});write(parent/'papers-index.json',[{'id':'a','facet_ids':['old']}]);write(parent/'graph.json',{'nodes':[],'edges':[]});write(parent/'diff.json',{})
   facet={'id':'scope','label':'Scope','definition':'Scoped memory.'};tag={'facet':'scope','display_allowed':False,'evidence':{'field':'abstract','text':'private source'}}
   write(private/'facets/FACETS.private.json',{'facets':[facet],'counts':{'scope':1},'untagged':0,'rows':[{'paper_id':'a','tags':[tag]}]})
   evaluation={'protocol':{'reviewer_route':'synthetic'},'counts':{'scope':{'positive_population':1,'sample':1,'supported':1,'unsupported':0,'uncertain':0}},'samples':[{'facet':'scope','records':[{'paper_id':'a','title':'<Unsafe title>','verdict':'supported','source_url':'https://example.org/p','classifier_quote':None}]}]};write(private/'evaluation/FACET-EVALUATION.public.json',evaluation);write(root/'strict-2026-11-02/evaluation/FACET-EVALUATION.public.json',evaluation)
   before=inventory(parent);build(parent,out,private);first=inventory(out);build(parent,out,private);self.assertEqual(before,inventory(parent));self.assertEqual(first,inventory(out));m=json.loads((out/'manifest.json').read_text());self.assertEqual(m['limitations'][0],'Exact prior warning.');p=json.loads((out/'papers-index.json').read_text());self.assertEqual(p[0]['facet_ids'],['scope']);self.assertIsNone(p[0]['facet_evidence'][0]['quote']);text=(out/'facet-evaluation.html').read_text();self.assertIn('&lt;Unsafe title&gt;',text);self.assertNotIn('private source',text)
   for key,original in (('index','papers-index.json'),('graph','graph.json')):
    d=json.loads((out/(key+'-sharded.json')).read_text());packed=b''.join((out/chunk).read_bytes() for chunk in d['chunks']);self.assertEqual(gzip.decompress(packed),(out/original).read_bytes())
if __name__=='__main__':unittest.main()
