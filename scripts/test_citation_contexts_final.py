import json
from pathlib import Path
import tempfile
import unittest
from citation_contexts_final import Collector, seed_scope

PAPERS=[{'id':'seed','title':'Synthetic seed','seed_ids':['A1'],'tier':'CORE','source_ids':{'s2':['seed-s2']}},
        {'id':'citing','title':'Synthetic citer','tier':'ADJACENT','source_ids':{'s2':['citer-s2']},'abstract_display_allowed':True,'abstract_license':'CC-BY'}]

class CitationContextTests(unittest.TestCase):
    def test_scope_never_invents_missing_seed_id(self):
        scope,missing=seed_scope(PAPERS+[{'id':'missing','title':'Missing source','seed_ids':['A2'],'source_ids':{}}])
        self.assertEqual(scope,{'seed-s2':'seed'});self.assertEqual(missing,['missing'])
    def test_exact_quotes_intents_and_license_version_withholding(self):
        def request(endpoint,params):
            data={'citationCount':1} if not endpoint.endswith('/citations') else {'offset':0,'data':[{'citingPaper':{'paperId':'citer-s2','title':'Synthetic citer','url':'https://example.org/citer'},'contexts':[' Exact source snippet. '], 'contextsWithIntent':[{'context':' Exact source snippet. ','intents':['methodology']}], 'intents':['background'],'isInfluential':False}]}
            return {'status':200,'data':data,'response_sha256':'actual-response','retrieved_at':'frozen-receipt','request_hash':'actual-request'}
        with tempfile.TemporaryDirectory() as directory:
            result=Collector(directory,PAPERS,request).run()
            record=result['papers']['seed']['citations'][0];context=record['contexts'][0]
            self.assertEqual(record['citing_id'],'citing');self.assertFalse(record['isInfluential'])
            self.assertEqual(context['quote'],' Exact source snippet. ')
            self.assertEqual(context['intents'],['methodology']);self.assertEqual(record['intents'],['background'])
            self.assertFalse(context['display_allowed']);self.assertIn('version',context['withheld_reason'])
            self.assertEqual(context['location']['field'],'contexts')
            self.assertEqual(len(context['source_locations']),2)
    def test_export_permission_filter_withholds_context_quote_but_keeps_count_link(self):
        from build_site import permission_filter
        record={'context_count':1,'source_url':'https://example.org/citer','contexts':[{'quote':'PRIVATE_CONTEXT_SENTINEL','display_allowed':False,'withheld_reason':'Exact source-version license unavailable','location':{'field':'contexts','index':0}}]}
        public=permission_filter(record)
        self.assertNotIn('PRIVATE_CONTEXT_SENTINEL',json.dumps(public))
        self.assertEqual(public['context_count'],1)
        self.assertEqual(public['source_url'],record['source_url'])
        self.assertTrue(public['contexts'][0]['quote_withheld'])
    def test_cap_pagination_reported_and_resume_are_deterministic(self):
        calls=[]
        def request(endpoint,params):
            calls.append((endpoint,params))
            if not endpoint.endswith('/citations'):data={'citationCount':9}
            else:
                offset=params['offset'];data={'offset':offset,'next':offset+2,'data':[{'citingPaper':{'paperId':'x'+str(offset+i)},'contexts':[]} for i in range(2)]}
            return {'status':200,'data':data,'response_sha256':'r','retrieved_at':'receipt','request_hash':'q'}
        with tempfile.TemporaryDirectory() as directory:
            first=Collector(directory,PAPERS,request,cap=3,page_size=2).run()
            acquired=first['papers']['seed']['acquisitions'][0]
            self.assertEqual(acquired['acquired'],3);self.assertEqual(acquired['reported_total'],9)
            self.assertTrue(acquired['capped']);self.assertEqual(acquired['pages'],2)
            before=len(calls)
            second=Collector(directory,PAPERS,lambda *args:(_ for _ in ()).throw(AssertionError('Resume must not call API')),cap=3,page_size=2).run()
            self.assertEqual(first,second);self.assertEqual(len(calls),before)
    def test_resolved_edges_use_existing_s2_identity_and_frozen_baseline_without_double_count(self):
        def request(endpoint,params):
            data={'citationCount':2} if not endpoint.endswith('/citations') else {'data':[{'citingPaper':{'paperId':'citer-s2'},'contexts':[]},{'citingPaper':{'paperId':'citer-s2'},'contexts':[]}]}
            return {'status':200,'data':data,'retrieved_at':'receipt'}
        with tempfile.TemporaryDirectory() as directory:
            first=Collector(directory,PAPERS,request,existing_edges=[]).run()
            self.assertEqual(first['resolved_citation_edges'],[['citing','seed']])
            self.assertEqual(first['coverage']['new_resolved_citation_edges'],1)
            self.assertEqual(first['coverage']['resolved_citation_edges_already_present'],0)
            second=Collector(directory,PAPERS,lambda *args:(_ for _ in ()).throw(AssertionError('Cached')),existing_edges=[['citing','seed']]).run()
            self.assertEqual(first,second)
        with tempfile.TemporaryDirectory() as directory:
            existing=Collector(directory,PAPERS,request,existing_edges=[['citing','seed']]).run()
            self.assertEqual(existing['coverage']['new_resolved_citation_edges'],0)
            self.assertEqual(existing['coverage']['resolved_citation_edges_already_present'],1)
    def test_cache_miss_is_hard_offline_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):Collector(directory,PAPERS,lambda *args:{'status':0,'error':'cache_miss'},cache_only=True).run()
    def test_malformed_context_schema_never_becomes_character_quotes(self):
        def request(endpoint,params):
            return {'status':200,'data':{'citationCount':1} if not endpoint.endswith('/citations') else {'data':[{'citingPaper':{'paperId':'citer-s2'},'contexts':'not an array','intents':'not an array'}]}}
        with tempfile.TemporaryDirectory() as directory:
            result=Collector(directory,PAPERS,request).run()
            citation=result['papers']['seed']['citations'][0]
            self.assertEqual(citation['contexts'],[]);self.assertEqual(citation['intents'],[])
            self.assertEqual(len(citation['gaps']),2)
    def test_rate_error_is_explicit_gap_not_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            result=Collector(directory,PAPERS,lambda *args:{'status':429,'error':None,'retrieved_at':'receipt','response_sha256':'r'}).run()
            record=result['papers']['seed']['acquisitions'][0]
            self.assertEqual(record['status'],'unavailable');self.assertEqual(record['acquired'],0)
            self.assertEqual(record['gaps'][0]['status'],429)

if __name__=='__main__':unittest.main()
