import json,tempfile,unittest
from pathlib import Path
from build_pdf_receipt_update import build,inventory

class ReceiptTests(unittest.TestCase):
    def test_acquisition_does_not_inflate_assessed_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);parent=root/'parent';parent.mkdir();(parent/'downloads').mkdir()
            counts={'received_pdf_files':3,'full_text_works':0}
            values={'manifest.json':{'snapshot':{'id':'previous'},'counts':counts,'files':{}},'counts.json':counts,'downloads/fulltext-downloads.json':{'counts':{}},'diff.json':{},'matrix.json':{'cells':'unchanged'},'papers-index.json':[],'graph.json':{'nodes':[]}}
            for name,value in values.items():(parent/name).write_text(json.dumps(value))
            summary={'protocol':'private-pdf-stream-v1','processed_files':3,'extracted_files':2,'failed_files':1,'identity_consistent_files':1,'identity_review_required':1,'unique_identity_consistent_papers':1,'physical_pages':12,'assessed_full_text_evidence':0,'used_in_chat':False,'public_pdf_or_text_exported':False}
            source=root/'private-summary.json';source.write_text(json.dumps(summary));before=inventory(parent)
            build(parent,root/'a',source);build(parent,root/'b',source)
            actual=json.loads((root/'a/counts.json').read_text())
            self.assertEqual(actual['received_pdf_files'],3);self.assertEqual(actual['collection_extracted_files'],2);self.assertEqual(actual['full_text_works'],0)
            self.assertEqual(before,inventory(parent));self.assertEqual(inventory(root/'a'),inventory(root/'b'))
            self.assertNotIn('pages',json.loads((root/'a/fulltext-receipt.json').read_text()))

if __name__=='__main__':unittest.main()
