import unittest
import tempfile
import contextlib
import io
import json
import os
import subprocess
from pathlib import Path
import sys
import types
from unittest.mock import patch
import analytics_final
import numpy as np
from analytics_final import relationship_edges, semantic_edges, first_date, project_ranking, query_embedding, frozen_compute_receipt, measured_report, authors_venues

class AnalyticsTests(unittest.TestCase):
    def test_exact_shared_counts_and_edge_types(self):
        ids=['a','b','c','d']; pairs=[['a','c'],['b','c'],['a','d'],['b','d']]
        edges, metadata=relationship_edges(ids,pairs,10)
        lookup={(e['source'],e['target'],e['type']):e['weight'] for e in edges}
        self.assertEqual(lookup[('a','b','bibliographic_coupling')],2)
        self.assertEqual(lookup[('c','d','cocitation')],2)
        self.assertEqual(metadata['citation']['retained_edges'],4)
    def test_duplicate_citations_do_not_inflate_counts(self):
        edges,_=relationship_edges(['a','b','c'],[['a','c'],['a','c'],['b','c']],10)
        self.assertEqual(next(e['weight'] for e in edges if e['type']=='bibliographic_coupling'),1)
    def test_semantic_and_ranking_determinism(self):
        v=np.array([[1.,0.],[0.,1.],[1.,0.]],dtype=np.float32)
        self.assertEqual(semantic_edges(['a','b','c'],v,1)[0],semantic_edges(['a','b','c'],v,1)[0])
        ranks=project_ranking(['a','b','c'],v,np.array([1.,0.]))
        self.assertEqual([r['id'] for r in ranks],['a','c','b'])
    def test_owner_reports_exclude_private_evidence_and_use_public_cluster_shape(self):
        from report_final import generate
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);private=base/'private';public=base/'public';docs=base/'docs'
            private.mkdir();public.mkdir()
            secret='PRIVATE_ABSTRACT_SENTENCE_DO_NOT_EXPORT'
            analytics={'nodes':[{'id':'p','tier':'CORE','cluster_id':0}], 'edges':[],
                'clusters':[{'id':0,'label':'Synthetic scope label','size':1}], 'method':{},'coverage':{'papers':1}}
            matrix={'columns':[{'id':'revoke'}],'rows':{'p':{'cells':{'revoke':{'value':'yes','quote':secret,'display_allowed':False}}}},
                'coverage':{'cells':1},'self_check':{'overall':{'numerator':1,'denominator':1,'agreement':1.},'positive_cells':{'numerator':1,'denominator':1,'agreement':1.},'second_extraction':{'quote':secret},'differences':[]}}
            for path,value in [(private/'analytics.private.json',analytics),(private/'matrix.private.json',matrix),(public/'analytics.json',analytics),
                (public/'counts.json',{'CORE':1}),(public/'manifest.json',{'snapshot':{'id':'synthetic'}})]:path.write_text(json.dumps(value))
            generate(private,public,docs)
            for path in docs.glob('*.md'):self.assertNotIn(secret,path.read_text())
            self.assertIn('| 0 | Synthetic scope label | 1 |',(docs/'CLUSTERS.md').read_text())
    def test_unresolved_author_names_are_paper_local_not_people_or_communities(self):
        papers=[{'id':'p1','authors':[{'id':None,'name':'Alex Same'}]},
            {'id':'p2','authors':[{'id':None,'name':'Alex Same'}]},
            {'id':'p3','authors':[{'id':'source-author','name':'Alex Same'},{'id':None,'name':'Alex Same'}]}]
        data,_=authors_venues(papers)
        unresolved=[a for a in data['items'] if a['identity_basis']=='paper_local_unresolved']
        self.assertEqual(len(unresolved),3)
        self.assertEqual(len({a['id'] for a in unresolved}),3)
        self.assertTrue(all(a['source_id'] is None and a['coauthorship_cluster'] is None for a in unresolved))
        self.assertEqual([a for c in data['clusters'] for a in c['author_ids']],['source-author'])
        self.assertEqual(data['coauthorship_edges'],[])
        self.assertEqual(data['coverage']['paper_local_unresolved_mentions'],3)
    def test_measured_report_does_not_invent_missing_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            report=measured_report(directory)
            self.assertEqual(report['analytics']['status'],'unavailable')
            self.assertEqual(report['matrix']['status'],'unavailable')
            self.assertNotIn('generated_at',report)
    def test_measured_report_reconciles_actual_cells_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            (base/'analytics.private.json').write_text(json.dumps({'nodes':[{'id':'a','tier':'CORE','cluster_id':-1}], 'edges':[], 'clusters':[], 'coverage':{'papers':1},'method':{}}))
            (base/'matrix.private.json').write_text(json.dumps({'columns':[{'id':'revoke'}],'rows':{'a':{'cells':{'revoke':{'value':'yes','quote':'private evidence must never enter aggregate report','display_allowed':False}}}},'coverage':{'cells':1},'self_check':{'overall':{'numerator':1,'denominator':1,'agreement':1.},'positive_cells':{'numerator':1,'denominator':1,'agreement':1.},'differences':[]}}))
            report=measured_report(base)
            self.assertEqual(report['matrix']['state_counts']['yes'],1)
            self.assertEqual(report['matrix']['displayable_evidence_cells'],0)
            self.assertTrue(report['checks']['matrix_core_row_count'])
            self.assertNotIn('private evidence',json.dumps(report))
    def test_author_clusters_are_stable_across_hash_seeds(self):
        script="""import json
from analytics_final import authors_venues
papers=[{'id':'p'+str(i),'authors':[{'id':a,'name':a},{'id':b,'name':b}],'venue':'synthetic'} for i,(a,b) in enumerate([('a','b'),('b','c'),('c','d'),('d','a'),('a','c')])]
print(json.dumps(authors_venues(papers),sort_keys=True))
"""
        outputs=[]
        for seed in ['1','999']:
            env={**os.environ,'PYTHONHASHSEED':seed}
            outputs.append(subprocess.check_output([sys.executable,'-c',script],cwd=Path(__file__).resolve().parent,env=env))
        self.assertEqual(outputs[0],outputs[1])
    def test_clean_cached_analytics_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            papers=[{'id':pid,'title':'Synthetic memory study '+pid,'abstract':'Synthetic evidence only.',
                'tier':'CORE' if pid!='c' else 'ADJACENT','first_public_date':'2024-01-01','authors':[{'id':'author','name':'Synthetic Author'}],'venue':'Synthetic Venue'} for pid in ['a','b','c']]
            (base/'papers.private.json').write_text(json.dumps(papers))
            (base/'vector_manifest.json').write_text(json.dumps({'documents':[{'id':p['id'],'representation':'title_abstract'} for p in papers]}))
            (base/'resolved_edges.json').write_text(json.dumps([['a','b'],['b','c']]))
            np.save(base/'vectors.float16.npy',np.array([[1.,0.],[0.,1.],[1.,1.]],dtype=np.float16),allow_pickle=False)
            project_path=base/'project.txt';project_path.write_text('Synthetic project scope.')
            config={'embeddings':{'model':'synthetic','query_task':'retrieval.query'},'analytics':{'random_seed':17},'model':{'primary_model':'synthetic'}}
            common=types.ModuleType('final_common');common.settings=lambda:config;common.folder=lambda:base
            common.read_json=lambda path:json.loads(path.read_text())
            common.write_json=lambda path,value:path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
            def forbidden(*args,**kwargs):raise AssertionError('This synthetic/cache-only test must not use external services')
            common.Model=forbidden;common.embed_query=lambda text:(np.array([1.,0.],dtype=np.float32),{'model':'synthetic','retrieved_at':'model-receipt'})
            def synthetic_projection(vectors,options):
                return np.array([[0.,0.],[1.,0.],[0.,1.]]),np.array([-1,-1,-1]),{'method':'Synthetic test stub; production UMAP/HDBSCAN not run locally'}
            with patch.dict(sys.modules,{'final_common':common}),patch.object(analytics_final,'PROJECT_ABSTRACT_PATH',project_path),patch.object(analytics_final,'cluster_vectors',synthetic_projection),patch.object(analytics_final.importlib.metadata,'version',lambda name:'synthetic'),contextlib.redirect_stdout(io.StringIO()):
                analytics_final.main()
                output_path=base/'analytics.private.json';first=output_path.read_bytes()
                common.embed_query=forbidden
                for _ in range(2):
                    output_path.unlink();analytics_final.main(cache_only=True)
                    self.assertEqual(first,output_path.read_bytes())
            parsed=json.loads(first)
            self.assertIn('first_completed_compute_at',parsed['method']['compute_receipt'])
            self.assertNotIn('generated_at',parsed)
    def test_compute_receipt_frozen_per_input_and_distinct_from_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            first=frozen_compute_receipt(directory,'analytics','same-input',lambda:'first-compute-time',libraries={'networkx':'3.7'})
            second=frozen_compute_receipt(directory,'analytics','same-input',lambda:'later-compute-time')
            changed=frozen_compute_receipt(directory,'analytics','changed-input',lambda:'changed-compute-time')
            self.assertEqual(first,second)
            self.assertEqual(first['first_completed_compute_at'],'first-compute-time')
            self.assertEqual(changed['first_completed_compute_at'],'changed-compute-time')
            self.assertNotIn('retrieved_at',first)
            self.assertEqual(first['libraries']['networkx'],'3.7')
    def test_query_cache_never_calls_network_in_cache_only(self):
        with tempfile.TemporaryDirectory() as directory:
            calls=[]
            def embed(text):calls.append(text);return np.array([1.,0.]),{'model':'test'}
            config={'embeddings':{'model':'test','query_task':'retrieval.query'}}
            query_embedding(directory,config,'project',embed)
            query_embedding(directory,config,'project',embed,True)
            self.assertEqual(calls,['project'])
            with self.assertRaises(RuntimeError):query_embedding(directory,config,'changed',embed,True)
    def test_date_prefers_first_public(self):
        self.assertEqual(first_date({'first_public_date':'2023-02-01','year':2025}),'2023-02-01')
        self.assertEqual(first_date({}),None)
        self.assertIsNone(first_date({'first_public_date':'2024-99-99'}))
    def test_timestamp_day_is_preserved_without_interpreting_time(self):
        paper={'first_public_date':'2023-05-08T08:09:00Z'}
        self.assertEqual(first_date(paper),'2023-05-08')
        self.assertEqual(paper['first_public_date'],'2023-05-08T08:09:00Z')
        self.assertEqual(first_date({'first_public_date':'2023-05-08T08:9:00Z'}),'2023-05-08')
        self.assertEqual(first_date({'first_public_date':'2024-02-29T23:59:59-04:00'}),'2024-02-29')
        self.assertIsNone(first_date({'first_public_date':'2023-02-29T08:09:00Z'}))
        self.assertIsNone(first_date({'first_public_date':'2023-99-08T08:09:00Z'}))
        self.assertIsNone(first_date({'first_public_date':'2023-05-08 arbitrary text'}))
    def test_cap_coverage_and_order(self):
        ids=['a','b','c','d','e'];pairs=[[source,target] for source in ['a','b','c'] for target in ['d','e']]
        edges,meta=relationship_edges(ids,pairs,1)
        self.assertEqual(meta['bibliographic_coupling']['candidate_edges'],3)
        self.assertEqual(meta['bibliographic_coupling']['retained_edges'],2)
        self.assertEqual(edges,relationship_edges(ids,list(reversed(pairs)),1)[0])
    def test_no_shared_pairs_and_no_citations(self):
        edges,meta=relationship_edges(['a','b'],[],10)
        self.assertEqual(edges,[])
        self.assertIsNone(meta['cocitation']['coverage'])

if __name__=='__main__': unittest.main()
