import unittest
import tempfile
import threading
import contextlib
import io
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch
from extract_final import validate_cells, validate_benchmarks, agreement_report, evidence_catalog, Extractor, enclosing_sentence, CAPABILITY_IDS, main as extract_main

CAPS = [{'id':'revoke','label':'Revoke','definition':'Explicit revocation'}]
PAPER = {'id':'p','title':'An unrelated title','abstract':'The system can revoke stored memories. Code is at https://example.org/code.','abstract_display_allowed':False}

class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.spans = evidence_catalog(PAPER, lambda p: [p['title'], 'The system can revoke stored memories.', 'Code is at https://example.org/code.'])
    def test_exact_quote_private_and_unknown(self):
        cells = validate_cells({'revoke':{'value':'yes','span_id':'s1'}}, CAPS, self.spans, PAPER, {'model':'test'})
        self.assertEqual(cells['revoke']['quote'], 'The system can revoke stored memories.')
        self.assertFalse(cells['revoke']['display_allowed'])
        unknown = validate_cells({}, CAPS, self.spans, PAPER, {'model':'test'})
        self.assertEqual(unknown['revoke']['value'], 'not stated')
    def test_two_batch_workers_share_model_preserve_prompts_and_cached_provenance(self):
        instances=[];rendezvous=threading.Barrier(2)
        class Model:
            def __init__(self):
                instances.append(self);self.rate_lock=threading.Lock();self.state_lock=threading.Lock();self.active=0;self.max_active=0;self.calls=[]
            def generate(self,system,payload,**kwargs):
                with self.rate_lock:self.calls.append((system,payload,kwargs))
                with self.state_lock:self.active+=1;self.max_active=max(self.max_active,self.active)
                rendezvous.wait(timeout=3)
                with self.state_lock:self.active-=1
                response={'papers':[{'paper_id':p['paper_id'],'cells':{'revoke':{'value':'yes','span_id':'s1'}},'benchmarks':[]} for p in payload['papers']]}
                return response,{'model':'test','response_sha256':payload['papers'][0]['paper_id'],'retrieved_at':'fixed-receipt'}
        papers=[{**PAPER,'id':'p'+str(i)} for i in range(12)]
        with tempfile.TemporaryDirectory() as directory:
            extractor=Extractor(directory,{'capabilities':CAPS},lambda p:[p['title'],'The system can revoke stored memories.'],Model)
            result=extractor.extract_many(papers)
            self.assertEqual(len(instances),1);self.assertEqual(instances[0].max_active,2)
            self.assertEqual(list(result),[p['id'] for p in papers])
            self.assertEqual(result,extractor.extract_many(papers))
            self.assertEqual(len(instances[0].calls),2)
            for system,payload,options in instances[0].calls:
                self.assertEqual(options['tag'],'batch-capabilities-benchmarks')
                self.assertEqual(options['max_tokens'],12000)
                self.assertTrue(system.startswith(extractor.prepare(papers[0])['prompt']))
                first=payload['papers'][0]['paper_id']
                for paper in payload['papers']:self.assertEqual(result[paper['paper_id']]['provenance']['response_sha256'],first)
    def test_failed_repair_preserves_valid_rows_from_same_batch(self):
        class Model:
            def generate(self,system,payload,**kwargs):
                if 'papers' not in payload:raise RuntimeError('Synthetic repair outage')
                return {'papers':[{'paper_id':p['paper_id'],'cells':{'revoke':{'value':'yes','span_id':'invented' if p['paper_id']=='p0' else 's1'}},'benchmarks':[]} for p in payload['papers']]},{'model':'test','response_sha256':'valid-batch-response'}
        papers=[{**PAPER,'id':'p'+str(i)} for i in range(6)]
        with tempfile.TemporaryDirectory() as directory:
            extractor=Extractor(directory,{'capabilities':CAPS},lambda p:[p['title'],'The system can revoke stored memories.'],Model)
            with self.assertRaises(RuntimeError):extractor.extract_many(papers)
            for paper in papers[1:]:
                path=extractor.prepare(paper)['path'];self.assertTrue(path.exists())
                self.assertEqual(json.loads(path.read_text())['provenance']['response_sha256'],'valid-batch-response')
    def test_failed_batch_does_not_discard_other_batch_cache(self):
        class Model:
            def generate(self,system,payload,**kwargs):
                if payload['papers'][0]['paper_id']=='p0':raise RuntimeError('Synthetic service failure')
                return {'papers':[{'paper_id':p['paper_id'],'cells':{'revoke':{'value':'not stated','span_id':None}},'benchmarks':[]} for p in payload['papers']]},{'model':'test','response_sha256':'valid-other-batch'}
        papers=[{**PAPER,'id':'p'+str(i)} for i in range(12)]
        with tempfile.TemporaryDirectory() as directory:
            extractor=Extractor(directory,{'capabilities':CAPS},lambda p:[p['title'],'The system can revoke stored memories.'],Model)
            with self.assertRaises(RuntimeError):extractor.extract_many(papers)
            for paper in papers[6:]:
                path=extractor.prepare(paper)['path'];self.assertTrue(path.exists())
                self.assertEqual(json.loads(path.read_text())['provenance']['response_sha256'],'valid-other-batch')
    def test_retry_exhaustion_withholds_invalid_cells_but_preserves_valid_evidence(self):
        capabilities=CAPS+[{'id':'clarification','label':'Clarification','definition':'Explicit clarification'}]
        class Model:
            def generate(self,system,payload,**kwargs):
                return {'cells':{'revoke':{'value':'yes','span_id':'s1'},'clarification':{'value':'yes','span_id':'invented'}},
                    'benchmarks':[{'code_url':{'value':'https://invented.org','span_id':'s1'}}]}, {'model':'test','response_sha256':'actual-response'}
        with tempfile.TemporaryDirectory() as directory:
            extractor=Extractor(directory,{'capabilities':capabilities},lambda p:[p['title'],'The system can revoke stored memories.'],Model)
            row=extractor.extract(PAPER)
            self.assertEqual(row['cells']['revoke']['value'],'yes')
            failed=row['cells']['clarification']
            self.assertEqual(failed['value'],'not stated')
            self.assertEqual(failed['validation_status'],'validation_failed')
            self.assertIn('extraction failed',failed['reason'].lower())
            self.assertIsNone(failed['quote'])
            self.assertEqual(failed['provenance']['response_sha256'],'actual-response')
            self.assertEqual(row['benchmarks'],[])
            self.assertEqual(len(row['validation_omissions']),2)
            self.assertEqual(row,extractor.extract(PAPER))
    def test_lossless_numeric_source_span_schema_variants(self):
        for item in [{'value':'yes','span_id':1},{'value':'yes','span_id':'1'},{'value':'yes','evidence_span':1},{'value':'yes','span_id':['s1']}]:
            cell=validate_cells({'revoke':item},CAPS,self.spans,PAPER,{})['revoke']
            self.assertEqual(cell['span_id'],'s1')
        for bad in [True,-1,{},['s1','s2']]:
            with self.assertRaises(ValueError):validate_cells({'revoke':{'value':'yes','span_id':bad}},CAPS,self.spans,PAPER,{})
    def test_title_and_missing_evidence_cannot_be_positive(self):
        for item in [{'value':'yes','span_id':'s0'},{'value':'partial'}, {'value':'no','span_id':'s1'}]:
            with self.assertRaises(ValueError): validate_cells({'revoke':item}, CAPS, self.spans, PAPER, {})
    def test_url_requires_exact_source(self):
        good = validate_benchmarks([{'code_url':{'value':'https://example.org/code','span_id':'s2'}}], self.spans, PAPER, {})
        self.assertEqual(good[0]['code_url']['value'],'https://example.org/code')
        with self.assertRaises(ValueError):
            validate_benchmarks([{'code_url':{'value':'https://invented.org','span_id':'s2'}}], self.spans, PAPER,{})
    def test_clean_cached_matrix_and_benchmarks_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            papers=[{**PAPER,'id':'core','tier':'CORE'},{**PAPER,'id':'adjacent','tier':'ADJACENT'}]
            (base/'papers.private.json').write_text(json.dumps(papers))
            config={'capabilities':[{'id':cid,'label':cid,'definition':'Synthetic definition'} for cid in CAPABILITY_IDS],
                'model':{'primary_model':'synthetic'},'analytics':{'random_seed':17}}
            class Model:
                def generate(self,system,payload,**kwargs):
                    return {'papers':[{'paper_id':p['paper_id'],'cells':{c['id']:{'value':'not stated','span_id':None} for c in p['capabilities']},'benchmarks':[]} for p in payload['papers']]},{'model':'synthetic','retrieved_at':'source-model-receipt'}
            common=types.ModuleType('final_common');common.settings=lambda:config;common.folder=lambda:base
            common.read_json=lambda path:json.loads(path.read_text())
            common.write_json=lambda path,value:path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
            common.source_spans=lambda paper:[paper['title'],paper.get('abstract') or ''];common.Model=Model
            with patch.dict(sys.modules,{'final_common':common}),contextlib.redirect_stdout(io.StringIO()):
                extract_main()
                paths=[base/'matrix.private.json',base/'benchmarks.private.json']
                first=[path.read_bytes() for path in paths]
                def forbidden():raise AssertionError('Cached rebuild must not instantiate a model')
                common.Model=forbidden
                for _ in range(2):
                    for path in paths:path.unlink()
                    extract_main(cache_only=True)
                    self.assertEqual(first,[path.read_bytes() for path in paths])
            matrix=json.loads(first[0]);benchmarks=json.loads(first[1])
            self.assertEqual(len(matrix['rows']),1)
            self.assertEqual(benchmarks['coverage']['papers_screened'],2)
            self.assertEqual(matrix['method']['compute_receipt'],benchmarks['method']['compute_receipt'])
    def test_repeated_spans_preserve_original_occurrence(self):
        paper={**PAPER,'abstract':'We revoke memories. We revoke memories.'}
        catalog=evidence_catalog(paper,lambda p:[p['title'],'We revoke memories.','We revoke memories.'])
        self.assertEqual(catalog['s1']['location']['char_start'],0)
        self.assertEqual(catalog['s2']['location']['char_start'],20)
    def test_full_sentence_preserves_qualifiers_and_exact_offsets(self):
        abstract='Prior work is limited. Although the system can revoke stored memories, it cannot automatically recover them. More work is needed.'
        span='can revoke stored memories,';start=abstract.index(span)
        quote,location=enclosing_sentence(abstract,start,start+len(span))
        self.assertEqual(quote,'Although the system can revoke stored memories, it cannot automatically recover them.')
        self.assertEqual(quote,abstract[location['char_start']:location['char_end']])
    def test_batch_cache_and_adjacent_without_matrix_cells(self):
        calls=[]
        class Model:
            def generate(self,system,payload,**kwargs):
                calls.append(payload)
                return {'papers':[{'paper_id':p['paper_id'],'cells':{c['id']:{'value':'not stated','span_id':None} for c in p['capabilities']},'benchmarks':[]} for p in payload['papers']]},{'model':'test'}
        papers=[{**PAPER,'id':'p'+str(i)} for i in range(6)]
        with tempfile.TemporaryDirectory() as directory:
            extractor=Extractor(directory,{'capabilities':CAPS},lambda p:[p['title'],'The system can revoke stored memories.'],Model)
            rows=extractor.extract_many(papers)
            self.assertEqual(len(rows),6)
            self.assertEqual(len(calls),1)
            self.assertEqual(rows,extractor.extract_many(papers))
            adjacent=extractor.extract_many(papers,benchmark_only=True)
            self.assertEqual(adjacent['p0']['cells'],{})
            self.assertEqual(len(calls),2)
    def test_cache_resume_and_independent_wording(self):
        calls=[]
        class Model:
            def generate(self,system,payload,**kwargs):
                calls.append(system)
                return {'cells':{'revoke':{'value':'yes','span_id':'s1'}},'benchmarks':[]},{'model':'test','response_sha256':'hash'}
        with tempfile.TemporaryDirectory() as directory:
            spans=lambda p:[p['title'],'The system can revoke stored memories.']
            extractor=Extractor(directory,{'capabilities':CAPS,'generation':{'model':'test'}},spans,Model)
            first=extractor.extract(PAPER)
            self.assertEqual(first,extractor.extract(PAPER))
            self.assertEqual(len(calls),1)
            extractor.extract(PAPER,second=True)
            self.assertEqual(len(calls),2)
            self.assertNotEqual(calls[0],calls[1])
            cached=Extractor(directory,{'capabilities':CAPS,'generation':{'model':'test'}},spans,Model,True)
            self.assertEqual(cached.extract(PAPER),first)
            with self.assertRaises(RuntimeError):cached.extract({**PAPER,'abstract':PAPER['abstract']+' Extra source.'})
            with self.assertRaises(RuntimeError):cached.extract({**PAPER,'abstract_display_allowed':True})
            changed=Extractor(directory,{'capabilities':CAPS,'model':{'primary_model':'different'}},spans,Model,True)
            with self.assertRaises(RuntimeError):changed.extract(PAPER)
    def test_empty_abstract_never_uses_title(self):
        with tempfile.TemporaryDirectory() as directory:
            def forbidden():raise AssertionError('Model must not run without abstract evidence')
            extractor=Extractor(directory,{'capabilities':CAPS},lambda p:[p['title']],forbidden)
            row=extractor.extract({**PAPER,'abstract':None})
            self.assertEqual(row['cells']['revoke']['value'],'not stated')
            self.assertIsNone(row['cells']['revoke']['quote'])
    def test_benchmark_paraphrase_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_benchmarks([{'task':{'value':'unsupported interpretation','span_id':'s1'}}],self.spans,PAPER,{})
    def test_agreement_denominators_and_differences(self):
        a={'p':{'cells':{'revoke':{'value':'yes'},'other':{'value':'not stated'}}}}
        b={'p':{'cells':{'revoke':{'value':'partial'},'other':{'value':'not stated'}}}}
        out=agreement_report(a,b,['p'],7)
        self.assertEqual(out['overall']['denominator'],2)
        self.assertEqual(out['positive_cells']['denominator'],1)
        self.assertEqual(len(out['differences']),1)

if __name__=='__main__': unittest.main()
