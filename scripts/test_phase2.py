import unittest
from phase2_merge import deduplicate, build_papers, retain_prior_seed_ids


def record(provider, source_id, doi=None, arxiv=None, year=2025, **extra):
    return dict(provider=provider, source_id=source_id, doi=doi, arxiv_id=arxiv, title='Synthetic paper fixture', year=year,
        venue=None, is_repository=True, authors=[], publication_date=None, abstract=None, provenance={}, discovery={}, open_access_urls=[], **extra)


class Phase2Tests(unittest.TestCase):
    def test_prior_verified_identifier_survives_detail_failure_without_changing_embedding_input(self):
        paper = {'id': 'canonical-fixture', 'title': 'Memory fixture', 'abstract': 'Stored memory.',
            'seed_ids': ['A03'], 'source_ids': {'openalex': ['fixture-oa'], 's2': []}, 'publication_versions': []}
        prior = {'seed_id': 'A03', 'source_records': {'s2': {'id': 'fixture-s2', 'title': 'Memory fixture', 'year': 2026}},
            'provenance': [{'provider': 's2', 'status': 200, 'response_sha256': 'fixture-hash', 'retrieved_at': 'fixture-date'}]}
        before = (paper['id'], paper['title'], paper['abstract'])
        retain_prior_seed_ids([paper], [prior])
        self.assertEqual((paper['id'], paper['title'], paper['abstract']), before)
        self.assertEqual(paper['source_ids']['s2'], ['fixture-s2'])
        self.assertEqual(paper['publication_versions'][0]['provenance']['response_sha256'], 'fixture-hash')

    def test_shared_arxiv_merges_proceedings_and_preprint_dois(self):
        _,_,groups,merges,_=deduplicate([record('openalex','OA',doi='10.synthetic/proceedings',arxiv='synthetic-id'), record('s2','S2',doi='10.synthetic/preprint',arxiv='synthetic-id')])
        self.assertEqual(len(groups),1);self.assertEqual(merges[0]['reason'],'shared_arxiv_id')

    def test_conflicting_identifiers_are_held_for_review(self):
        _,_,groups,_,suspected=deduplicate([record('openalex','A',doi='10.synthetic/a'),record('openalex','B',doi='10.synthetic/b')])
        self.assertEqual(len(groups),2);self.assertEqual(len(suspected),1)

    def test_arxiv_date_and_venue_year_remain_separate(self):
        a=record('openalex','OA',arxiv='synthetic',year=2026);a.update(venue='Synthetic venue',is_repository=False,discovery={'method':'seed','seed_id':'C07'})
        p=build_papers([a],{'C07':{'group':'C','display_short_name':'HaluMem'}},{'synthetic':{'first_public_date':'2025-11-05T00:00:00Z'}})[0][0]
        self.assertEqual(p['first_public_year'],2025);self.assertEqual(p['venue_publication_year'],2026);self.assertEqual(p['display_short_name'],'HaluMem')

    def test_missing_arxiv_v1_date_is_not_guessed_from_venue_year(self):
        p=build_papers([record('openalex','OA',arxiv='synthetic',year=2026)],{}, {})[0][0]
        self.assertIsNone(p['first_public_date']);self.assertIsNone(p['first_public_year'])
