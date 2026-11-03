"""Check facet evidence offsets against the original private metadata snapshot."""
import argparse,json
from pathlib import Path

def audit(private, review):
    papers={p['id']:p for p in json.loads((private/'papers.private.json').read_text())}
    facets=json.loads((review/'facets/FACETS.private.json').read_text())
    count=0
    for row in facets['rows']:
        paper=papers[row['paper_id']]
        for tag in row['tags']:
            e=tag['evidence']; source=paper.get(e['field']) or ''
            assert (source==e['text'] if e['field']=='title' else source[e['start']:e['end']]==e['text'])
            count+=1
    return {'papers':len(facets['rows']),'source_spans_checked':count,'method':'Exact offsets in stored title or abstract; topical relevance is not validated by this check.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--review',type=Path,required=True);a=p.parse_args();print(json.dumps(audit(a.private,a.review),sort_keys=True))
