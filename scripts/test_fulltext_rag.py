"""Synthetic contracts: scope, exclusion, exact page binding and private text."""
import gzip,json,os,sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from build_fulltext_rag import build,chunks
from fulltext import FulltextIndex
from gateway import Gateway

class FulltextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source';self.private=self.root/'private';self.out=self.root/'index'
        for p in (self.source/'records',self.source/'pages',self.private):p.mkdir(parents=True)
        self.first='A synthetic executor resolves preference conflicts by asking the person to choose an applicable scope.'
        self.second='The synthetic system revokes an expired temporary override and restores the previous scoped default.'
        papers=[{'id':'fixture-a','title':'Synthetic temporary memory','tier':'CORE','abstract':'The abstract describes a synthetic memory system.','abstract_display_allowed':True},{'id':'fixture-b','title':'Unresolved synthetic PDF','tier':'ADJACENT','abstract':'The abstract contains a memory example.'}]
        (self.private/'papers.private.json').write_text(json.dumps(papers))
        for index,(pid,status) in enumerate([('fixture-a','title_match'),('fixture-b','identity_review_required')]):
            sha=str(index)*64
            (self.source/'records'/(pid+'.json')).write_text(json.dumps({'paper_id':pid,'pdf_sha256':sha,'identity_status':status,'status':'extracted'}))
            with gzip.open(self.source/'pages'/(sha+'.json.gz'),'wt') as f:json.dump({'pdf_sha256':sha,'pages':[{'page':1,'text':self.first},{'page':2,'text':''},{'page':3,'text':self.second if index==0 else 'FORBIDDEN UNRESOLVED PDF TEXT'}]},f)
        cfg=json.loads((Path(__file__).resolve().parents[1]/'config/fulltext-rag-2026-11-02.json').read_text());cfg.update(expected_papers=1,expected_excluded_files=1)
        self.cfg=self.root/'config.json';self.cfg.write_text(json.dumps(cfg));self.manifest=build(self.source,self.private,self.out,self.cfg);self.index=FulltextIndex(self.out)
    def tearDown(self):self.temp.cleanup()
    def test_excluded_identity_never_enters_index(self):
        self.assertEqual(self.index.paper_ids,{'fixture-a'})
        with self.index.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM papers WHERE paper_id=?',('fixture-b',)).fetchone()[0],0)
    def test_page_numbers_survive_blank_pages(self):
        result,diag=self.index.retrieve('revoke expired override',{'fixture-a'})
        self.assertEqual(result[0]['page'],3);self.assertEqual(result[0]['span'],self.second);self.assertFalse(result[0]['display_allowed'])
    def test_empty_or_unresolved_scope_never_expands(self):
        for scope in (set(),{'fixture-b'}):self.assertEqual(self.index.retrieve('scope',scope)[0],[])
    def test_gateway_never_retrieves_pdf_without_processing_permission(self):
        rights=self.root/'rights-denied.json'
        rights.write_text(json.dumps([{'paper_id':'fixture-a','private_processing_allowed':False}]))
        with patch.dict(os.environ,{'ATLAS_FULLTEXT_RIGHTS':str(rights)}):
            gateway=Gateway(self.private,generate=lambda *args: ({},'fixture-model'),fulltext=self.index)
        with patch.object(self.index,'retrieve',wraps=self.index.retrieve) as retrieve:
            gateway.ask('expired override',paper_ids=['fixture-a'])
        self.assertEqual(retrieve.call_args.args[1],set())

    def test_reranker_failure_retains_fulltext_with_diagnostic(self):
        def fail(*args):raise RuntimeError('synthetic unavailable')
        result,diag=self.index.retrieve('expired override',{'fixture-a'},rerank=fail)
        self.assertTrue(result);self.assertEqual(diag['reranker'],'unavailable')
    def test_bad_reranker_indices_are_rejected(self):
        result,diag=self.index.retrieve('scope expired',{'fixture-a'},rerank=lambda *a:{'results':[{'index':999,'relevance_score':1}]})
        self.assertTrue(result);self.assertEqual(diag['reranker'],'unavailable')
    def test_fulltext_claim_uses_actual_page_and_withholds_quote_even_when_abstract_licensed(self):
        def generate(system,payload):
            if 'claims' in payload:return {'claims':[{'index':0,'supported':True}]},'fixture-model'
            passage=next(x for x in payload['sentences'] if 'revokes' in x['text'])
            return {'claims':[{'text':'Expired overrides revert in this synthetic example.','span_ids':[passage['span_id']]}]},'fixture-model'
        g=Gateway(self.private,generate=generate,fulltext=self.index)
        g.rerank=lambda *a:(_ for _ in ()).throw(RuntimeError('synthetic disabled'))
        result=g.ask('What happens to an expired override?',paper_ids=['fixture-a'])
        self.assertTrue(result['grounded']);self.assertEqual(result['sources'][0]['page'],3);self.assertEqual(result['sources'][0]['location'],'PDF p. 3')
        self.assertEqual(result['sources'][0]['evidence_level'],'fulltext');self.assertFalse(result['sources'][0]['display_allowed']);self.assertIsNone(result['sources'][0]['passage']);self.assertNotIn(self.second,json.dumps(result))
    def test_multiple_passages_same_paper_do_not_overwrite_support(self):
        evidence=[{'paper_id':'fixture-a','span':self.first,'chunk_id':1},{'paper_id':'fixture-a','span':self.second,'chunk_id':2}]
        claim={'text':'A paraphrase.','paper_ids':['fixture-a'],'support':[{'paper_id':'fixture-a','span':self.first,'chunk_id':1}]}
        self.assertIsNone(Gateway.claim_failure_reason([claim],evidence));claim['support'][0]['chunk_id']=2
        self.assertEqual(Gateway.claim_failure_reason([claim],evidence),'invalid_exact_support')
    def test_chunk_offsets_are_exact_and_cover_body(self):
        text=('A sentence with exact source spacing.\n'*120)
        result=list(chunks(text,2800,300,40))
        for start,end,span in result:self.assertEqual(text[start:end],span)
        covered=set(i for start,end,_ in result for i in range(start,end))
        self.assertTrue(all(i in covered for i,c in enumerate(text) if not c.isspace()))
    def test_only_direct_license_not_unverified_provider_url_releases_short_quote(self):
        rights=self.root/'rights.json'
        def generate(system,payload):
            if 'claims' in payload:return {'claims':[{'index':0,'supported':True}]},'fixture-model'
            passage=next(x for x in payload['sentences'] if 'revokes' in x['text'])
            return {'claims':[{'text':'Expired overrides revert in this synthetic example.','span_ids':[passage['span_id']]}]},'fixture-model'
        for status,expected in [('explicit_license',True),('provider_license_exact_url',False)]:
            rights.write_text(json.dumps([{'paper_id':'fixture-a','status':status,'public_short_quote_allowed':True,'private_processing_allowed':True}]))
            with patch.dict(os.environ,{'ATLAS_FULLTEXT_RIGHTS':str(rights)}):g=Gateway(self.private,generate=generate,fulltext=self.index)
            g.rerank=lambda *a:(_ for _ in ()).throw(RuntimeError('synthetic disabled'))
            result=g.ask('What happens to an expired override?',paper_ids=['fixture-a'])
            self.assertTrue(result['grounded']);self.assertEqual(result['sources'][0]['display_allowed'],expected)
            if expected:self.assertLessEqual(len(result['sources'][0]['passage'].split()),25)
            else:self.assertIsNone(result['sources'][0]['passage'])
    def test_catalogue_never_offers_more_than_25_words(self):
        text=' '.join('word'+str(i) for i in range(80))+'.'
        result=Gateway.sentence_catalogue([{'paper_id':'fixture-a','span':text,'location':'PDF p. 3','display_allowed':True}])
        self.assertTrue(result);self.assertTrue(all(len(s['text'].split())<=25 and s['text'] in text for s in result))
        long={'text':'A synthetic claim.','paper_ids':['fixture-a'],'support':[{'paper_id':'fixture-a','span':text}]}
        self.assertEqual(Gateway.claim_failure_reason([long],[{'paper_id':'fixture-a','span':text}]),'invalid_exact_support')
    def test_readonly_retrieval_does_not_store_question(self):
        before=(self.out/'index.sqlite').read_bytes();self.index.retrieve('private temporary question',{'fixture-a'})
        self.assertEqual(before,(self.out/'index.sqlite').read_bytes());self.assertEqual({p.name for p in self.out.iterdir()},{'index.sqlite','manifest.json'})

if __name__=='__main__':unittest.main()
