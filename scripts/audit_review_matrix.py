"""Audit private matrix quotes against raw PDF page offsets; no source text is exported."""
import argparse, gzip, json
from pathlib import Path

def audit(review):
    matrix=json.loads((review/'matrix-v3/MATRIX.private.json').read_text())
    checked=0
    for row in matrix['rows'].values():
        with gzip.open(review/'raw-pages'/(row['source_sha256']+'.json.gz'),'rt',encoding='utf8') as fh:
            raw=json.load(fh)
        assert raw['paper_id']==row['paper_id'] and raw['pdf_sha256']==row['source_sha256']
        pages={p['page']:p['text'] for p in raw['pages']}
        for cell in row['cells'].values():
            quote=cell.get('quote')
            if cell.get('value') in ('yes','partial'):
                assert quote and len(quote.split())<=25
                location=cell['location']
                assert pages[location['page']][location['char_start']:location['char_end']]==quote
                checked+=1
            else:
                assert cell.get('value')=='not stated' and not quote
    return {'papers':len(matrix['rows']),'supported_cells_checked':checked,'validation':'Exact raw-text page offsets and quote length; visual and semantic verification remain necessary.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--review',type=Path,required=True);args=parser.parse_args();print(json.dumps(audit(args.review),sort_keys=True))
