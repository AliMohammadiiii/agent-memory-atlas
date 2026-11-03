"""Rebuild the strict-facet snapshot from private, cached model artifacts."""
import argparse,collections,gzip,hashlib,html,json,os,shutil
from pathlib import Path
from urllib.parse import urlparse
from build_pdf_receipt_update import read,write,inventory
from build_site import contains_ipv4



def public_facets(facets,evaluation):
    # The audit sample was drawn from the second-model results before these
    # conservative sample corrections. Preserve its denominator and record.
    excluded={(group['facet'],r['paper_id']) for group in evaluation['samples'] for r in group['records'] if r['verdict']!='supported'}
    removed=set();rows=[];counts=collections.Counter()
    for row in facets['rows']:
        kept=[]
        for tag in row['tags']:
            key=(tag['facet'],row['paper_id'])
            if key in excluded:removed.add(key)
            else:kept.append(tag);counts[tag['facet']]+=1
        rows.append({**row,'tags':kept})
    assert removed==excluded
    return rows,dict(counts),sum(not row['tags'] for row in rows),len(removed)

def evaluation_html(evaluation,definitions):
    labels={d['id']:d['label'] for d in definitions}; esc=lambda x:html.escape(str(x),quote=True)
    reviewer=evaluation['protocol']['reviewer_route'];classifier=evaluation['protocol'].get('classifier_route');same_family=reviewer==classifier
    review_note='The reviewer shares a model family with the original classifier; the confirmed fraction is correlated model agreement, not human-verified precision.' if same_family else 'The reviewer differs from the original classifier; the confirmed fraction is model agreement, not human-verified precision.'
    correction_note='Sampled unsupported or uncertain entries were removed from navigation after this sample was reviewed; the fractions describe the pre-correction sample.' if same_family else 'This initial sample was reviewed before the second-model validation pass.'
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Facet spot checks · Agent Memory Atlas</title><style>body{font:16px/1.55 system-ui,sans-serif;color:#17313b;background:#fbfaf6;max-width:960px;margin:auto;padding:24px}a{color:#246777}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #cbd9d9;text-align:left;padding:8px}details{margin:1em 0;border-top:1px solid #cbd9d9;padding:12px 0}li{margin:12px 0}small{color:#4d6067}blockquote{margin:6px 0;padding-left:12px;border-left:2px solid #78999f}</style></head><body><p><a href="../">← Back to the atlas</a></p><h1>Facet spot checks</h1><p>Each row samples predicted positive tags. ' + review_note + ' Uncertain judgments remain in the denominator. ' + correction_note + '</p><table><thead><tr><th>Facet</th><th>Predicted tags</th><th>Sample</th><th>Confirmed</th><th>Unsupported</th><th>Uncertain</th></tr></thead><tbody>']
    for fid,c in evaluation['counts'].items():
        parts.append('<tr><th>'+esc(labels[fid])+'</th><td>'+str(c['positive_population'])+'</td><td>'+str(c['sample'])+'</td><td>'+str(c['supported'])+' / '+str(c['sample'])+'</td><td>'+str(c['unsupported'])+'</td><td>'+str(c['uncertain'])+'</td></tr>')
    parts.append('</tbody></table><p>Reviewer: '+esc(evaluation['protocol']['reviewer_route'])+'. Samples were selected using the frozen seed and protocol, without replacement within each facet.</p>')
    for group in evaluation['samples']:
        parts.append('<details><summary>'+esc(labels[group['facet']])+' — '+str(len(group['records']))+' sampled papers</summary><ol>')
        for record in group['records']:
            u=record.get('source_url') or '';parsed=urlparse(u);title=esc(record['title']);name='<a href="'+esc(u)+'" rel="noreferrer">'+title+'</a>' if parsed.scheme in ('http','https') else title
            parts.append('<li>'+name+' — <strong>'+esc(record['verdict'])+'</strong><br><small>'+esc(record['paper_id'])+'</small>')
            if record.get('classifier_quote'):parts.append('<blockquote>'+esc(record['classifier_quote'])+'</blockquote>')
            else:parts.append('<br><small>Evidence quote withheld because its display permission or length does not meet the public rule.</small>')
            if record.get('reviewer_quote') and record['reviewer_quote']!=record.get('classifier_quote'):parts.append('<small>Independent reviewer source:</small><blockquote>'+esc(record['reviewer_quote'])+'</blockquote>')
            parts.append('</li>')
        parts.append('</ol></details>')
    return ''.join(parts)+'</body></html>\n'

def build(parent,out,private,site_data=None):
    assert parent.resolve()!=out.resolve();before=inventory(parent)
    facets=read(private/'facets/FACETS.private.json');evaluation=read(private/'evaluation/FACET-EVALUATION.public.json');initial=read(private.parent/'strict-2026-11-02/evaluation/FACET-EVALUATION.public.json')
    assert all(v['sample']==min(30,v['positive_population']) for v in evaluation['counts'].values())
    public_rows,public_counts,untagged,removed=public_facets(facets,evaluation)
    manifest=read(parent/'manifest.json');papers=read(parent/'papers-index.json');rows={r['paper_id']:r for r in public_rows};assert set(rows)=={p['id'] for p in papers}
    if not out.exists():shutil.copytree(parent,out,copy_function=os.link)
    definitions=[{k:f[k] for k in ('id','label','definition')}|{'size':public_counts.get(f['id'],0)} for f in facets['facets']]
    for p in papers:
        tags=rows[p['id']]['tags'];p['facet_ids']=[t['facet'] for t in tags];p['facet_primary']=p['facet_ids'][0] if tags else 'untagged';p['facet_evidence']=[]
        for tag in tags:
            e=tag['evidence'];q=e['text'];allowed=tag['display_allowed'] and len(q.split())<=25 and not contains_ipv4(q)
            p['facet_evidence'].append({'facet':tag['facet'],'quote':q if allowed else None,'location':e['field'],'model':tag.get('model'),'source_url':tag.get('source_url')})
    manifest['atlas']['researchFacets']=definitions;manifest['atlas']['facetEvaluation']=evaluation['counts'];manifest['atlas']['facetEvaluationInitial']=initial['counts'];counts=manifest['counts'];counts['research_facet_untagged']=untagged;counts['facet_sample_unconfirmed_removed']=removed
    previous=manifest['snapshot']['id'];manifest['snapshot'].update(id='2026-11-02-strict-facets',parents=[previous],method_update='Main-contribution research facets with independent model spot checks; other snapshot evidence is unchanged.')
    # The public index and graph are transferred as small parts of a single
    # deterministic gzip stream. This avoids long stalled large responses while
    # preserving the original JSON as a compatibility fallback and for MCP.
    shard_dir=out/'shards'
    if shard_dir.exists():shutil.rmtree(shard_dir)
    shard_dir.mkdir(parents=True)
    for key,filename in (('index','papers-index.json'),('graph','graph.json')):
        raw=(out/filename).read_bytes() if key=='graph' else (json.dumps(papers,sort_keys=True,separators=(',',':')).encode()+b'\n')
        compressed=gzip.compress(raw,compresslevel=6,mtime=0);paths=[]
        for number,offset in enumerate(range(0,len(compressed),65536)):
            name=f'{key}-{number:04d}.bin';(shard_dir/name).write_bytes(compressed[offset:offset+65536]);paths.append('shards/'+name)
        descriptor=key+'-sharded.json';write(out/descriptor,{'format':'atlas-gzip-shards-v1','fallback':filename,'sha256':hashlib.sha256(compressed).hexdigest(),'chunks':paths})
        manifest['files'][key]=descriptor
    manifest['files']['facetEvaluation']='facet-evaluation.json';manifest['files']['facetEvaluationReport']='facet-evaluation.html';manifest['files']['facetEvaluationInitial']='facet-evaluation-initial.json'
    manifest['limitations'].append('Facet spot-check fractions compare model judgments on sampled positive tags before excluding the unconfirmed sample entries. The reviewer shares a model family with the initial classifier; these are not precision against human-verified ground truth.')
    counts['limitations_count']=len(manifest['limitations'])
    for name,data in [('papers-index.json',papers),('counts.json',counts),('manifest.json',manifest),('facet-evaluation.json',evaluation),('facet-evaluation-initial.json',initial)]:write(out/name,data)
    for name,result in (('facet-evaluation.html',evaluation),('facet-evaluation-initial.html',initial)):
        html_path=out/name;tmp=html_path.with_suffix('.html.new');tmp.write_text(evaluation_html(result,definitions));os.replace(tmp,html_path)
    diff=read(parent/'diff.json');diff.update(parent=previous,current=manifest['snapshot']['id'],status='Research-facet definitions and model-assisted spot checks updated; papers, citation edges and matrix evidence unchanged.');write(out/'diff.json',diff)
    hashes=inventory(out);hashes.pop('FILES.sha256.json',None);write(out/'FILES.sha256.json',hashes);assert inventory(parent)==before
    if site_data:
        candidate=site_data.with_name('.strict-next');old=site_data.with_name('.strict-old')
        assert not candidate.exists() and not old.exists();shutil.copytree(out,candidate,copy_function=os.link)
        if site_data.exists():os.replace(site_data,old)
        os.replace(candidate,site_data)
        if old.exists():shutil.rmtree(old)
    return {'papers':len(papers),'facet_sizes':public_counts,'untagged':untagged,'sample_unconfirmed_removed':removed,'sample_counts':evaluation['counts']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--site-data',type=Path);a=p.parse_args();print(build(a.parent,a.out,a.private,a.site_data))
