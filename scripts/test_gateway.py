"""Ten English contract evaluations use isolated synthetic evidence, never ship it."""
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from gateway import Gateway, Handler

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.span='The synthetic system stores scoped preferences and allows explicit deletion.'
        (self.root/'papers.private.json').write_text(json.dumps([{'id':'fixture-a','title':'Synthetic scoped memory','tier':'CORE','abstract':self.span,'abstract_display_allowed':False},{'id':'fixture-b','title':'Licensed memory example','tier':'ADJACENT','abstract':'The synthetic benchmark evaluates memory retrieval with test cases.','abstract_display_allowed':True}]))
        self.payloads=[]
    def tearDown(self): self.tmp.cleanup()
    def test_privacy_address_text_is_not_published_as_chat_evidence(self):
        address='.'.join(map(str,(127,0,0,1)))
        g=self.gateway([{'text':'A local interface is available.','span_ids':['s0']}])
        g.papers['fixture-b']['abstract']='The synthetic interface uses the network address '+address+'.'
        self.assertFalse(g.evidence(['fixture-b'])[0]['display_allowed'])
        reply=g.ask('What interface is available?',paper_ids=['fixture-b'])
        self.assertTrue(reply['grounded'])
        self.assertIsNone(reply['sources'][0]['passage'])
        self.assertTrue(reply['sources'][0]['quote_withheld'])
        self.assertNotIn(address,json.dumps(reply))
    def test_privacy_address_in_generated_claim_is_rejected(self):
        claim=self.claim(text='Use '+'.'.join(map(str,(127,0,0,1)))+' for access.')
        self.assertEqual(Gateway.claim_failure_reason([claim],[{'paper_id':'fixture-a','span':self.span}]),'privacy_withheld')
    def gateway(self,claims=None,verify=True):
        def gen(system,payload):
            self.payloads.append(payload)
            return ({'claims':[{'index':i,'supported':verify} for i in range(len(payload['claims']))]} if 'claims' in payload else {'claims':claims or []}),'fixture-model'
        return Gateway(self.root,generate=gen)
    def claim(self,**kwargs):
        c={'text':'Scoped preferences can be explicitly removed.','paper_ids':['fixture-a'],'support':[{'paper_id':'fixture-a','span':self.span}]}; c.update(kwargs); return c
    def test_01_what_can_scoped_memory_store(self):
        r=self.gateway([self.claim()]).ask('What can scoped memory store?'); self.assertTrue(r['grounded']); self.assertEqual(r['sources'][0]['id'],'fixture-a')
    def test_02_does_unlicensed_passage_stay_private(self):
        r=self.gateway([self.claim()]).ask('How is scoped memory deleted?'); self.assertIsNone(r['sources'][0]['passage']); self.assertTrue(r['sources'][0]['quote_withheld']); self.assertNotIn(self.span,json.dumps(r))
    def test_03_unknown_source_is_rejected(self):
        self.assertFalse(self.gateway([self.claim(paper_ids=['invented'])]).ask('What is scoped memory?')['grounded'])
    def test_04_invented_support_is_rejected(self):
        self.assertFalse(self.gateway([self.claim(support=[{'paper_id':'fixture-a','span':'The system achieves ninety percent.'}])]).ask('What is scoped memory?')['grounded'])
    def test_05_unsupported_question_refuses(self):
        self.assertFalse(self.gateway().ask('Which memory system cures disease?')['grounded'])
    def test_06_failed_entailment_refuses(self):
        self.assertFalse(self.gateway([self.claim()],False).ask('Does scoped memory guarantee success?')['grounded'])
    def test_07_only_last_four_messages(self):
        self.gateway([self.claim()]).ask('What is scoped memory?',[{'role':'user','content':str(i)} for i in range(8)]); self.assertEqual([m['content'] for m in self.payloads[0]['messages']],['4','5','6','7'])
    def test_08_licensed_exact_quote_is_displayable(self):
        span='The synthetic benchmark evaluates memory retrieval with test cases.'
        claim={'text':'The example tests memory retrieval.','paper_ids':['fixture-b'],'support':[{'paper_id':'fixture-b','span':span}]}
        r=self.gateway([claim]).ask('What does the benchmark evaluate?',paper_ids=['fixture-b']); self.assertTrue(r['grounded']); self.assertEqual(r['sources'][0]['passage'],span)
    def test_09_selection_limits_sources(self):
        r=self.gateway().search('scoped memory',paper_ids=['fixture-b']); self.assertTrue(all(x['id']=='fixture-b' for x in r['results'])); self.assertEqual(r['mode'],'lexical')
    def test_10_injected_bracket_citations_refuse(self):
        self.assertFalse(self.gateway([self.claim(text='A claim [invented]')]).ask('What is scoped memory?')['grounded'])
    def test_default_core_plus_seeds_and_explicit_adjacent_toggle(self):
        g=self.gateway(); default=g.search('memory',filters={'tier':'CORE+seeds','include_adjacent':False}); expanded=g.search('memory',filters={'tier':'CORE+ADJACENT','include_adjacent':True})
        self.assertEqual({r['id'] for r in default['results']},{'fixture-a'}); self.assertEqual({r['id'] for r in expanded['results']},{'fixture-a','fixture-b'})

    def test_semantic_query_honors_manifest_order_and_cosine(self):
        try:
            import numpy as np
        except ImportError: self.skipTest('NumPy unavailable')
        np.save(self.root/'vectors.float16.npy',np.asarray([[0,1],[1,0]],dtype='float16'))
        (self.root/'vector_manifest.json').write_text(json.dumps({'parameters':{'model':'pinned-test','dimensions':2},'documents':[{'id':'fixture-b'},{'id':'fixture-a'}]}))
        g=Gateway(self.root,embed=lambda q:[1,0]); result=g.search('memory')
        self.assertEqual(result['mode'],'semantic'); self.assertEqual(result['model'],'pinned-test'); self.assertEqual(result['results'][0],{'id':'fixture-a','score':1.0})

    def test_cx_request_omits_temperature_and_reports_actual_model_separately(self):
        g=Gateway(self.root); calls=[]
        def fake_post(url,body,key):
            calls.append(body)
            return {'model':'upstream-actual-fixture','choices':[{'message':{'content':'{"claims":[]}'}}]}
        with patch.dict(os.environ,{'ATLAS_NINEROUTER_API_KEY':'synthetic-test-credential','ATLAS_ROUTER_URL':'http://localhost:20128'}),patch('gateway.post',side_effect=fake_post):
            _,attribution=g.generate('system',{'question':'synthetic fixture'})
        self.assertNotIn('temperature',calls[0]); self.assertEqual(attribution,{'model':'upstream-actual-fixture','requested_route':g.primary,'gateway':g.primary_gateway})

    def test_answer_preserves_generation_and_verification_model_attribution(self):
        calls=[]
        def gen(system,payload):
            calls.append(payload)
            if 'claims' in payload:return {'claims':[{'index':i,'supported':True} for i in range(len(payload['claims']))]},{'model':'actual-verifier','requested_route':'cx/fixture-verifier'}
            return {'claims':[self.claim()]},{'model':'actual-generator','requested_route':'cx/fixture-generator'}
        g=Gateway(self.root,generate=gen); answer=g.ask('What is scoped memory?')
        self.assertTrue(answer['grounded']);self.assertEqual(answer['model'],'actual-generator');self.assertEqual(answer['requested_route'],'cx/fixture-generator');self.assertEqual(answer['verification_model'],'actual-verifier')

    def test_model_config_selects_gateway_and_runtime_url_without_source_change(self):
        config={'model':{'primary_gateway':'custom','primary_model':'configured-route','fallback_gateway':'custom','fallback_model':'configured-fallback','gateway_env':{'custom':{'url_env':'ATLAS_TEST_GATEWAY_URL','key_env':'ATLAS_TEST_GATEWAY_KEY','chat_path':'/completion'}}}}
        g=Gateway(self.root,config=config);calls=[]
        def fake_post(url,body,key):
            calls.append((url,body,key));return {'model':'actual-configured-model','choices':[{'message':{'content':'{"claims":[]}'}}]}
        with patch.dict(os.environ,{'ATLAS_TEST_GATEWAY_URL':'http://localhost:18090','ATLAS_TEST_GATEWAY_KEY':'synthetic-test-credential'}),patch('gateway.post',side_effect=fake_post):
            _,attribution=g.generate('system',{})
        self.assertEqual(calls[0][0],'http://localhost:18090/completion');self.assertEqual(calls[0][1]['model'],'configured-route');self.assertEqual(attribution['model'],'actual-configured-model');self.assertEqual(attribution['gateway'],'custom')

    def test_refusal_enum_is_coarse_and_contains_no_support_text(self):
        answer=self.gateway([self.claim(paper_ids=['invented'])]).ask('What is scoped memory?')
        self.assertEqual(answer['refusal_reason'],'unknown_citation');self.assertEqual(answer['diagnostics']['evidence_papers'],1);self.assertNotIn(self.span,json.dumps(answer))
        rejected=self.gateway([self.claim()],False).ask('What is scoped memory?')
        self.assertEqual(rejected['refusal_reason'],'entailment_rejected')

    def test_valid_claim_survives_another_claim_with_bad_support(self):
        bad=self.claim(support=[{'paper_id':'fixture-a','span':'Invented text is not source evidence.'}])
        result=self.gateway([self.claim(),bad]).ask('What is scoped memory?')
        self.assertTrue(result['grounded']);self.assertEqual(len(result['claims']),1);self.assertEqual(result['diagnostics']['valid_exact_claims'],1)
    def test_numbered_span_is_bound_to_exact_source_and_metadata_reaches_verifier(self):
        observed=[]
        def gen(system,payload):
            observed.append(payload)
            if 'claims' in payload:
                self.assertEqual(payload['source_metadata'][0]['title'],'Synthetic scoped memory')
                self.assertEqual(payload['claims'][0]['support'][0]['span'],self.span)
                return {'claims':[{'index':0,'supported':True}]},'fixture-model'
            return {'claims':[{'text':'The synthetic paper describes scoped preferences.','span_ids':[payload['sentences'][0]['span_id']]}]},'fixture-model'
        result=Gateway(self.root,generate=gen).ask('What is scoped memory?')
        self.assertTrue(result['grounded']);self.assertEqual(result['claims'][0]['paper_ids'],['fixture-a']);self.assertNotIn(self.span,json.dumps(result))
    def test_unsupported_or_duplicate_verifier_decisions_cannot_authorize_claim(self):
        claim=self.claim()
        self.assertEqual(Gateway.supported_claims([claim],{'claims':[{'index':0,'supported':False}]}),[])
        self.assertEqual(Gateway.supported_claims([claim],{'claims':[{'index':0,'supported':True},{'index':0,'supported':False}]}),[])
        self.assertEqual(Gateway.supported_claims([claim],{'supported':True}),[])

    def test_empty_restricted_scope_never_expands_to_default_or_calls_generation(self):
        def forbidden(*args):raise AssertionError('Empty scope must not call a model or embedder')
        g=Gateway(self.root,generate=forbidden,embed=forbidden)
        self.assertEqual(g.search('scoped memory',paper_ids=[])['results'],[])
        answer=g.ask('What is scoped memory?',paper_ids=[])
        self.assertFalse(answer['grounded']);self.assertEqual(answer['claims'],[]);self.assertEqual(answer['sources'],[])
        self.assertTrue(g.search('scoped memory')['results'])
        self.assertTrue(g.search('scoped memory',paper_ids=None)['results'])

    def test_semantic_library_limit_allows_two_hundred_and_clamps_larger_requests(self):
        papers=[{'id':'fixture-'+str(i),'title':'Memory transport fixture '+str(i),'tier':'CORE'} for i in range(250)]
        (self.root/'papers.private.json').write_text(json.dumps(papers));g=Gateway(self.root)
        self.assertEqual(len(g.search('memory',200,mode='lexical')['results']),200)
        self.assertEqual(len(g.search('memory',1000,mode='lexical')['results']),200)

    def test_filtered_corpus_id_payload_fits_same_bounded_limit_as_preview_proxy(self):
        Handler.gateway=self.gateway();server=ThreadingHTTPServer(('localhost',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            body=json.dumps({'query':'memory','paper_ids':['fixture-a']*16000}).encode();self.assertGreater(len(body),65536);self.assertLess(len(body),262144)
            request=urllib.request.Request('http://localhost:'+str(server.server_port)+'/search',data=body,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=5) as response:data=json.load(response)
            self.assertEqual(data['results'][0]['id'],'fixture-a')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
