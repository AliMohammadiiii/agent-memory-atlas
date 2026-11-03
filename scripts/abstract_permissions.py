"""Bind public abstract permission to the exact selected source text."""
from collections import defaultdict

PERMITTED={'cc0','cc-by','cc-by-sa','cc0-1.0','cc-by-4.0','cc-by-sa-4.0'}


def bind_permissions(papers,events):
    observations=defaultdict(list)
    for event in events:observations[(event['provider'],event['source_id'])].append(event)
    for paper in papers:
        evidence=[]
        for provider,ids in paper['source_ids'].items():
            for ident in ids:
                for row in observations[(provider,ident)]:
                    for license_id in row.get('content_license_observations') or []:
                        evidence.append({'license':license_id,'source_id':ident,'provenance':row['provenance'],
                            'matches_selected_abstract':bool(paper.get('abstract')) and row.get('abstract')==paper.get('abstract')})
        allowed=[r for r in evidence if r['matches_selected_abstract'] and str(r['license']).lower().replace('_','-') in PERMITTED]
        paper['content_license_observations']=evidence
        paper['abstract_display_allowed']=bool(allowed)
        paper['abstract_license']=allowed[0]['license'] if allowed else None
    return papers


def refresh():
    from final_common import folder,read_json,write_json
    f=folder();papers=read_json(f/'papers.private.json')
    bind_permissions(papers,read_json(f/'candidate_events.json'))
    write_json(f/'papers.private.json',papers)
    receipt={'candidates':len(papers),'abstracts_available':sum(bool(p.get('abstract')) for p in papers),
        'abstract_display_allowed':sum(bool(p.get('abstract_display_allowed')) for p in papers),
        'policy':'Explicit permitted content license on an observation with the exact selected abstract text.'}
    write_json(f/'ABSTRACT-PERMISSIONS.json',receipt)
    if (f/'DEDUPLICATION.json').exists():
        dedup=read_json(f/'DEDUPLICATION.json');dedup['abstract_display_allowed']=receipt['abstract_display_allowed']
        write_json(f/'DEDUPLICATION.json',dedup)


if __name__=='__main__':refresh()
