import json
import tempfile
import unittest
from pathlib import Path
from build_site import build, permission_filter, contains_ipv4, diagnostic_public, public_parentage, export_archives, verify_determinism, validate_final_coverage, metadata, citation_exports
import build_site
from unittest.mock import patch

class ExportTests(unittest.TestCase):
    def test_deterministic_default_deny_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); private=root/'private'; private.mkdir()
            rows=[{'id':'p1','title':'Test & metadata','tier':'CORE','abstract':'PRIVATE ABSTRACT MUST NOT SHIP','abstract_available':True,'open_access_urls':['https://example.org/paper.pdf'],'authors':[{'name':'A Writer'}],'first_public_year':2025,'first_public_date':'2025-05-08T08:9:00Z','seed_ids':['A1']},
                  {'id':'p2','title':'Other metadata','tier':'ADJACENT','abstract':'Licensed abstract.','abstract_display_allowed':True},
                  {'id':'p3','title':'Excluded title','tier':'EXCLUDE','abstract':'EXCLUDED PRIVATE ABSTRACT'}]
            for name,value in [('papers',rows),('analytics',{'nodes':[{'id':'p1','tier':'CORE','x':0,'y':0}],'edges':[]}),('matrix',{'columns':[],'rows':{'p1':{'cells':{'c':{'value':'yes','quote':'PRIVATE QUOTE','location':'abstract','display_allowed':False}}}}}),('benchmarks',{'papers':[]})]:
                (private/(name+'.private.json')).write_text(json.dumps(value))
            (private/'citation_contexts.private.json').write_text(json.dumps({'papers':{'p1':{'paper_id':'p1','citations':[{'citing_title':'Metadata only','contexts':[{'quote':'PRIVATE CONTEXT MUST NOT SHIP','display_allowed':False,'location':'citation context'}]}]}},'coverage':{'seed_papers':1},'method':{'scope':'Exact source-version permission unavailable'}}))
            config={'atlas':{'id':'fixture','title':'Fixture','server_secret':'never'},'snapshot':{'id':'test'},'limitations':['Fixture coverage limitation']}
            build(private,root/'a',config); build(private,root/'b',config)
            a={str(p.relative_to(root/'a')):p.read_bytes() for p in (root/'a').rglob('*') if p.is_file()}
            b={str(p.relative_to(root/'b')):p.read_bytes() for p in (root/'b').rglob('*') if p.is_file()}
            frozen={p.name:p.read_bytes() for p in private.iterdir()}
            with patch('socket.create_connection',side_effect=AssertionError('cache-only build attempted network')):
                verification=verify_determinism(private,config)
            self.assertTrue(verification['deterministic']); self.assertEqual(verification['independent_builds'],2)
            self.assertEqual(frozen,{p.name:p.read_bytes() for p in private.iterdir()})
            self.assertEqual(a,b); body=b''.join(a.values()); self.assertNotIn(b'PRIVATE ABSTRACT',body); self.assertNotIn(b'PRIVATE QUOTE',body); self.assertNotIn(b'PRIVATE CONTEXT',body); self.assertIn(b'Licensed abstract.',body); self.assertNotIn(b'server_secret',body)
            manifest=json.loads(a['manifest.json']); self.assertEqual(json.loads(a['counts.json']),manifest['counts']); self.assertEqual(manifest['files']['counts'],'counts.json'); self.assertEqual(manifest['limitations'],['Fixture coverage limitation']); self.assertEqual(manifest['counts']['limitations_count'],1); self.assertEqual(manifest['counts']['retained'],2); self.assertEqual(manifest['counts']['full_text_works'],0); self.assertEqual(manifest['counts']['full_text_stored'],0); self.assertEqual(manifest['counts']['default_core_plus_seeds'],1)
            detail=next(json.loads(a[bucket])['p1'] for bucket in manifest['files']['details'] if 'p1' in json.loads(a[bucket])); self.assertEqual(detail['first_public_date'],'2025-05-08'); self.assertEqual(detail['first_public_date_raw'],'2025-05-08T08:9:00Z')
            self.assertTrue(all((root/'a'/p).exists() for p in manifest['files']['details'])); context_file=manifest['files']['citationContexts']['p1']; context=json.loads(a[context_file]); self.assertIsNone(context['citations'][0]['contexts'][0]['quote']); self.assertTrue(context['citations'][0]['contexts'][0]['quote_withheld'])
    def test_licensed_ipv4_text_is_withheld_for_privacy(self):
        address='.'.join(map(str,(127,0,0,1)))
        for doi in ('10.46449/mjell.2025.02.30.1.47','10.53761/1.20.5.02','10.53761/1.20.02.07'):
            self.assertFalse(contains_ipv4(doi))
        self.assertTrue(contains_ipv4(address+'.'))
        source={'id':'p','title':'Licensed source','tier':'CORE','abstract':f'Browse http://{address}:8080 for details.','abstract_display_allowed':True}
        self.assertFalse(metadata(source)['abstract_display_allowed'])
        quote=permission_filter({'display_allowed':True,'quote':source['abstract']})
        self.assertIsNone(quote['quote']); self.assertFalse(quote['display_allowed'])
        self.assertEqual(quote['quote_withheld_reason'],'privacy_ipv4_address')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';private.mkdir()
            for name,value in [('papers',[source]),('analytics',{'nodes':[],'edges':[]}),('matrix',{'columns':[],'rows':{}}),('benchmarks',{'papers':[]})]:
                (private/(name+'.private.json')).write_text(json.dumps(value))
            frozen=(private/'papers.private.json').read_bytes()
            build(private,root/'public',{'atlas':{'id':'fixture'},'snapshot':{'id':'test'}})
            index=json.loads((root/'public/papers-index.json').read_text())
            detail=json.loads((root/'public'/index[0]['detail_bucket']).read_text())['p']
            self.assertIsNone(detail['abstract']); self.assertFalse(detail['abstract_display_allowed'])
            self.assertEqual(detail['abstract_withheld_reason'],'privacy_ipv4_address')
            self.assertIn('privacy',detail['abstract_status'])
            quality=json.loads((root/'public/quality.json').read_text())['coverage']
            self.assertEqual(quality['abstract_privacy_withheld'],1); self.assertEqual(quality['abstract_permission_withheld'],0)
            analytics=json.loads((root/'public/analytics.json').read_text())
            self.assertEqual(analytics['method']['privacy_withholding']['abstracts_withheld'],1)
            self.assertNotIn(address,b''.join(p.read_bytes() for p in (root/'public').rglob('*') if p.is_file()).decode())
            self.assertEqual((private/'papers.private.json').read_bytes(),frozen)
            source['link']='http://'+address
            (private/'papers.private.json').write_text(json.dumps([source]))
            with self.assertRaisesRegex(ValueError,'IPv4 privacy gate'):
                build(private,root/'blocked',{'atlas':{'id':'fixture'},'snapshot':{'id':'test'}})

    def test_nested_quote_permissions_do_not_inherit(self):
        value=permission_filter({'display_allowed':True,'quote':'permitted','nested':{'quote':'secret'}})
        self.assertEqual(value['quote'],'permitted'); self.assertIsNone(value['nested']['quote']); self.assertTrue(value['nested']['quote_withheld'])
    def test_first_public_day_preserves_date_without_inventing_time(self):
        row=metadata({'id':'p','first_public_date':'2023-05-08T08:9:00Z'})
        self.assertEqual(row['first_public_date'],'2023-05-08')
        self.assertEqual(row['first_public_date_precision'],'day')
        self.assertNotIn('first_public_date_raw',row)
        for raw in ('2023-02-29T08:9:00Z','2023-13-01','2023','20230508','2023-05-08 arbitrary'):
            row=metadata({'id':'p','first_public_date':raw})
            self.assertIsNone(row['first_public_date'])
            self.assertEqual(row['first_public_date_precision'],'unknown')
        self.assertEqual(metadata({'id':'p','first_public_date':'2024-02-29'})['first_public_date'],'2024-02-29')

    def test_diagnostics_default_deny_and_parent_inventory_minimization(self):
        result=diagnostic_public({'parent_request_hash':'abc','prior_status':429,'status':200,'needs_review':False,'final_ids':['p1'],'opaque_provider_payload':{'abstract':'PRIVATE ABSTRACT','data':{'title':'PRIVATE SOURCE BODY'}},'unknown_string':'PRIVATE UNKNOWN','mean_cosine_by_tier':{'CORE':0.75},'candidate_denominator':12})
        body=json.dumps(result); self.assertNotIn('PRIVATE',body); self.assertEqual(result['final_ids'],['p1']); self.assertEqual(result['mean_cosine_by_tier']['CORE'],0.75); self.assertEqual(result['prior_status'],429)
        parent=public_parentage({'snapshot':'final','parents':['parent'],'parent_files_sha256':{'parent/public':{'papers.json':'abc'},'parent/private':{'private-source-name.json':'def'}}})
        self.assertNotIn('private-source-name',json.dumps(parent)); self.assertEqual(parent['private_parent_inventories']['parent/private']['files'],1)

    def test_readable_archive_preserves_parent_and_withholds_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); parent=root/'data/snapshot-2020-parent'; parent.mkdir(parents=True)
            original=json.dumps([{'id':'p-old','title':'Historical title','abstract':'PRIVATE OLD ABSTRACT','year':2020,'dois':['10.example/old']}]); (parent/'papers.json').write_text(original)
            output=root/'output'
            with patch.object(build_site,'ROOT',root): archives=export_archives(output,{'parents':['2020-parent'],'parent_hashes':{}},'/agent-memory/')
            self.assertEqual((parent/'papers.json').read_text(),original)
            page=(output/'archives/2020-parent/index.html').read_text(); self.assertIn('Historical title',page); self.assertIn('Historical tier unavailable',page)
            self.assertNotIn('PRIVATE OLD ABSTRACT',''.join(p.read_text() for p in output.rglob('*') if p.is_file())); self.assertTrue(archives[0]['url'].endswith('/index.html'))

    def test_final_readiness_rejects_incomplete_coverage_and_invented_spans(self):
        papers=[{'id':'core','tier':'CORE','abstract':'The scoped memory supports explicit deletion.'},{'id':'adjacent','tier':'ADJACENT','abstract':None}]
        config={'id':'agent-memory','capabilities':[{'id':'scope'}]}
        analytics={'nodes':[{'id':'core'},{'id':'adjacent'}]}
        matrix={'columns':[{'id':'scope'}],'rows':{'core':{'cells':{'scope':{'value':'yes','quote':'The scoped memory supports explicit deletion.'}}}}}
        benchmarks={'papers':[{'paper_id':'core','benchmarks':[]},{'paper_id':'adjacent','benchmarks':[]}]}
        validate_final_coverage(papers,analytics,matrix,benchmarks,config)
        with self.assertRaisesRegex(ValueError,'analytics'): validate_final_coverage(papers,{'nodes':[{'id':'core'}]},matrix,benchmarks,config)
        with self.assertRaisesRegex(ValueError,'matrix'): validate_final_coverage(papers,analytics,{'columns':[{'id':'scope'}],'rows':{}},benchmarks,config)
        with self.assertRaisesRegex(ValueError,'benchmark screening'): validate_final_coverage(papers,analytics,matrix,{'papers':[benchmarks['papers'][0]]},config)
        matrix['rows']['core']['cells']['scope']['quote']='Invented support span.'
        with self.assertRaisesRegex(ValueError,'exact acquired abstract span'): validate_final_coverage(papers,analytics,matrix,benchmarks,config)

    def test_unknown_type_is_generic_and_explicit_types_map_narrowly(self):
        row=metadata({'id':'p','title':'A preprint title does not classify itself','year':2026,'arxiv_ids':['2601.00001'],'venue':'Observed container','authors':[]})
        bib,ris,csl=citation_exports(row);self.assertTrue(bib.startswith('@misc{'));self.assertIn('TY  - GEN',ris);self.assertEqual(csl['type'],'document');self.assertIn('howpublished = {Observed container}',bib)
        row=metadata({'id':'p','title':'Versioned work','first_public_year':1991,'venue_publication_year':1992,'publication_type':'book-chapter','venue':'Observed book','dois':['10.example/a','10.example/b'],'publication_versions':[{'source_id':'p','year':1992,'doi':'10.example/b'}]})
        bib,ris,csl=citation_exports(row);self.assertTrue(bib.startswith('@incollection{'));self.assertIn('TY  - CHAP',ris);self.assertEqual(csl['type'],'chapter');self.assertEqual(csl['issued']['date-parts'],[[1992]]);self.assertEqual(csl['DOI'],'10.example/b');self.assertEqual(row['year'],1991)
        generic_article=metadata({'id':'q','title':'No journal assertion','type':'article'})
        self.assertEqual(citation_exports(generic_article)[2]['type'],'document')

if __name__=='__main__': unittest.main()
