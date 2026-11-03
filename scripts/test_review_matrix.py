import sqlite3,unittest,zlib
from review_matrix import candidate_spans
class MatrixEvidenceTests(unittest.TestCase):
 def test_columns_never_mix_and_offsets_match_source(self):
  source='The scope is valid for this user.                 An unrelated attack succeeds.\nOur deterministic executor applies updates.      Other work uses a classifier.\n'
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE chunks(chunk_id INTEGER,paper_id TEXT,page INTEGER,start_offset INTEGER,body BLOB)');db.execute('INSERT INTO chunks VALUES(1,?,?,?,?)',('paper',4,11,zlib.compress(source.encode())))
  caps=[{'id':'scoped_storage'},{'id':'deterministic_executor'}];spans=candidate_spans(db,'paper',caps);self.assertTrue(spans)
  for s in spans:
   self.assertNotIn('   ',s['quote']);self.assertNotIn('\n',s['quote']);self.assertLessEqual(len(s['quote'].split()),25);self.assertEqual(source[s['start']-11:s['end']-11],s['quote'])
  self.assertFalse(any('scope' in s['quote'].lower() and 'attack' in s['quote'].lower() for s in spans))
if __name__=='__main__':unittest.main()

class RawReadingOrderTests(unittest.TestCase):
 def test_complete_short_sentences_are_exact_page_substrings(self):
  from review_matrix_v3 import candidate_spans
  text='Our system stores memory within each context.\nIt has a deterministic executor for the proposed pipeline.\nThe unrelated statement has no relevant keywords.'
  pages=[{'page':7,'text':text}];caps=[{'id':'scoped_storage'},{'id':'deterministic_executor'}]
  spans=candidate_spans(pages,caps);self.assertTrue(spans)
  for s in spans:
   self.assertEqual(text[s['start']:s['end']],s['quote']);self.assertLessEqual(len(s['quote'].split()),25);self.assertIn(s['quote'][-1],'.!?')
