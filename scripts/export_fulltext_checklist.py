"""Export metadata-only download requests; never fetch or publish paper text."""
import argparse,csv,hashlib,html,io,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from build_site import metadata,contains_ipv4

def export(private,out,receipt_report=None,identity_summary=None):
    papers=[p for p in json.loads((private/'papers.private.json').read_text()) if p.get('tier') in ('CORE','ADJACENT')]
    rows=[]
    for p in papers:
        groups=p.get('seed_groups',[]);priority=1 if any(g in ('A','B') for g in groups) else 2 if groups else 3 if p['tier']=='CORE' else 4
        urls=[u for u in p.get('open_access_urls',[]) if isinstance(u,str) and urlparse(u).scheme in ('http','https')]
        arxiv=next(iter(p.get('arxiv_ids',[])),None)
        observed_pdf=next((u for u in urls if urlparse(u).path.lower().endswith('.pdf') or '/pdf/' in urlparse(u).path.lower()),None)
        pdf=observed_pdf or ('https://arxiv.org/pdf/'+arxiv if arxiv else '')
        link=pdf or next(iter(urls),'')
        doi=next(iter(p.get('dois',[])),'')
        source=metadata(p)['link']
        if urlparse(source or '').scheme not in ('http','https') or contains_ipv4(source):source=''
        urls=[u for u in urls if not contains_ipv4(u)]
        if contains_ipv4(link):link=''
        provenance=p.get('abstract_provenance') or {}
        rows.append({'priority':priority,'paper_id':p['id'],'short_name':p.get('display_short_name') or '', 'title':p['title'],'tier':p['tier'],'seed_groups':';'.join(groups),'first_public_year':p.get('first_public_year') or '', 'venue_publication_year':p.get('venue_publication_year') or '', 'arxiv_id':arxiv or '', 'doi':doi,'download_url':link,'link_basis':'API-recorded PDF URL' if observed_pdf else 'PDF URL derived from API-verified arXiv identifier; not fetched' if arxiv else 'API-recorded OA landing link; not fetched' if link else 'No OA download link recorded; consult source', 'other_open_access_links':';'.join(urls),'source_url':source,'metadata_snapshot':'2026-11-01-final','abstract_record_retrieved_at':provenance.get('retrieved_at',''),'full_text_assessed':p.get('evidence_level')=='fulltext'})
    rows.sort(key=lambda r:(r['priority'],r['short_name'] or r['title'],r['paper_id']))
    out.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0])
    for name,subset in [('fulltext-download-checklist',rows),('fulltext-first-batch',[r for r in rows if r['priority']==1])]:
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(subset);(out/(name+'.csv')).write_text(stream.getvalue())
        items=[]
        for r in subset:
            url=r['download_url'] or r['source_url'];items.append('<tr><td>'+str(r['priority'])+'</td><td>'+html.escape(r['short_name'])+'</td><td>'+html.escape(r['title'])+'</td><td>'+html.escape(r['tier'])+'</td><td><a rel="noopener" href="'+html.escape(url,quote=True)+'">'+('Download / open copy' if r['download_url'] else 'Find a copy at source')+'</a><br><small>'+html.escape(r['link_basis'])+'</small></td></tr>')
        (out/(name+'.html')).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agent Memory Atlas · Full-text download checklist</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:48px auto;padding:0 20px;color:#182e36;background:#fbfaf6}table{border-collapse:collapse;width:100%}td,th{text-align:left;vertical-align:top;border-bottom:1px solid #d7dede;padding:12px}a{color:#176573}small{font-size:12px}h1{font:36px Georgia,serif}</style><h1>Full-text download checklist</h1><p>'+str(len(subset))+' records. Priority 1: scoped/revised-memory and lifecycle seeds (groups A and B). Priority 2: remaining seeds. Priority 3: remaining CORE. Priority 4: remaining ADJACENT.</p><p>Full-text works counts papers already assessed from full text, not the availability of a download link. These URLs come from the frozen API snapshot or verified arXiv identifiers. Links have not been fetched or checked for current availability. Source access does not imply permission to redistribute a PDF. No paper text is included here.</p><p>Metadata snapshot: 2026-11-01-final · Checklist generated 2026-11-02</p><table><thead><tr><th>Priority</th><th>Alias</th><th>Paper</th><th>Tier</th><th>Link</th></tr></thead><tbody>'+''.join(items)+'</tbody></table></html>')
    counts={'records':len(rows),'first_batch':sum(r['priority']==1 for r in rows),'with_download_or_oa_link':sum(bool(r['download_url']) for r in rows),'source_link_only':sum(not r['download_url'] for r in rows),'full_text_assessed':sum(r['full_text_assessed'] for r in rows),'by_priority':dict(Counter(str(r['priority']) for r in rows))}
    if receipt_report and receipt_report.exists():
        acquired=list(csv.DictReader(receipt_report.open()));statuses=Counter(r.get('status') for r in acquired)
        counts.update(received_pdf_files=statuses['downloaded'],download_failures=statuses['failed'],reported_without_url=statuses['no_url'],receipt_report_sha256=hashlib.sha256(receipt_report.read_bytes()).hexdigest())
    if identity_summary and identity_summary.exists():
        summary=json.loads(identity_summary.read_text());counts.update(first_batch_received=summary['received_first_batch'],first_batch_identity_consistent=summary['identity_consistent'],first_batch_identity_review_required=summary['review_required'],first_batch_automated_identity_matches=summary.get('automated_identity_consistent',summary['identity_consistent']),first_batch_visual_title_matches=summary.get('assistant_visual_title_matches',0))
    (out/'fulltext-downloads.json').write_text(json.dumps({'counts':counts,'records':rows,'method':'Checklist generated from frozen API-derived metadata; this exporter does not fetch PDFs. Receipt counts describe separately supplied private downloads. arXiv PDF addresses derive only from verified identifiers.','metadata_snapshot':'2026-11-01-final'},sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps(counts))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt-report',type=Path);p.add_argument('--identity-summary',type=Path);a=p.parse_args();export(a.private,a.out,a.receipt_report,a.identity_summary)
