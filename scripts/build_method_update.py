"""Fork immutable public metadata for a dated method update, using atomic writes."""
import argparse,hashlib,html,json,os,shutil
from collections import Counter
from pathlib import Path
import numpy as np

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.new');tmp.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n');os.replace(tmp,path)
def inventory(root):return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}

def build(private,study,parent,out,site_data=None):
    before=inventory(parent);report=read(study/'comparison.json');protocol=read(study/'PROTOCOL-FROZEN.json')
    assert report['input_provenance']==protocol and report['baseline_reproduced_ari']==1
    assert all(len(r['subsamples'])==3 for r in report['runs'])
    if not out.exists():shutil.copytree(parent,out,copy_function=os.link)
    else:
        current=read(out/'manifest.json')['snapshot']
        assert current['parents']==['2026-11-01-final'] or inventory(out)==before,'Unrecognized existing method output'
    ids=read(study/'paper-order.json');assignments=read(study/'assignments.private.json');selected=report['selected_pipeline'];labels=np.array(assignments[selected]);density=np.array(assignments['umap10-density']);baseline=np.array(assignments['baseline'])
    documents=read(private/'vector_manifest.json')['documents'];original=[d['id'] if isinstance(d,dict) else d for d in documents];order={pid:i for i,pid in enumerate(original)}
    vectors=np.load(private/'vectors.float16.npy').astype(np.float32)[[order[i] for i in ids]];vectors/=np.linalg.norm(vectors,axis=1,keepdims=True)
    by_id={p['id']:p for p in read(private/'papers.private.json')};papers=[by_id[i] for i in ids]
    from analytics_final import label_clusters
    from final_common import Model,settings
    selected_labels=label_clusters(papers,vectors,labels,study,settings(),Model,cache_only=os.environ.get('ATLAS_CACHE_ONLY')=='1')
    density_clusters=[]
    for c in sorted(set(density)):
        members=[ids[i] for i in np.where(density==c)[0]]
        density_clusters.append({'id':int(c),'label':'Unclustered (UMAP10/HDBSCAN noise)' if c==-1 else 'Density group '+str(c+1),'size':len(members),'paper_ids':members,'top_terms':[],'evidence_ids':[],'evidence_titles':[],'model':None,'method':'Numerical density-group identifier; no topic label inferred'})
    graph=read(parent/'graph.json');old_clusters=graph['clusters'];old_names={int(c['id']):c['label'] for c in old_clusters};names={int(c['id']):c['label'] for c in selected_labels};density_names={int(c['id']):c['label'] for c in density_clusters}
    maps={pid:{'cluster_id':int(labels[i]),'cluster_label':names[int(labels[i])],'baseline_cluster_id':int(baseline[i]),'baseline_cluster_label':old_names[int(baseline[i])],'density_cluster_id':int(density[i]),'density_cluster_label':density_names[int(density[i])]} for i,pid in enumerate(ids)}
    for node in graph['nodes']:node.update(maps[node['id']])
    selection=next(r for r in report['runs'] if r['id']==selected)
    graph.update(clusters=selected_labels,baseline_clusters=old_clusters,density_clusters=density_clusters)
    graph['study']={'id':report['id'],'papers':len(ids),'selected_pipeline':selected,'baseline_unassigned':int((baseline<0).sum()),'assignment_semantics':selection['full']['assignment_semantics']+'; not a calibrated probability or human validation.','human_validation':report['human_validation']}
    method=graph.setdefault('method',{});method['clustering']=selection['parameters'];method['clustering_comparison']={'protocol_sha256':protocol['protocol_sha256'],'vectors_sha256':protocol['vectors_sha256'],'analysis_date':'2026-11-02','selected':selected,'coverage':selection['full'],'stability':selection['subsamples'],'selection_rule':report['selection_rule'],'density_baseline_preserved':True,'source':'clustering-comparison.json','sources':report['sources']}
    write(out/'graph.json',graph)
    index=read(parent/'papers-index.json')
    assert isinstance(index,list)
    for paper in index:paper.update(maps[paper['id']])
    write(out/'papers-index.json',index)
    analytics=read(parent/'analytics.json');analytics['clusters']=selected_labels
    for node in analytics.get('nodes',[]):node.update(maps[node['id']])
    for point in analytics.get('timeline',[]):point.update(cluster_id=maps[point['id']]['cluster_id'])
    analytics.setdefault('methods',{})['clustering_comparison']=method['clustering_comparison'];write(out/'analytics.json',analytics)
    report['baseline']=next(r['full'] for r in report['runs'] if r['id']=='baseline');report['cluster_labels']=selected_labels;report['analysis_date']='2026-11-02';write(out/'clustering-comparison.json',report)
    for source in (study/'downloads').glob('*'):
        target=out/'downloads'/source.name;target.parent.mkdir(exist_ok=True)
        if target.exists():target.unlink()
        shutil.copyfile(source,target)
    shutil.copyfile(study/'owner-cluster-review.csv',out/'owner-cluster-review.csv')
    manifest=read(parent/'manifest.json');manifest['snapshot']={**manifest['snapshot'],'id':'2026-11-02-methods','date':'2026-11-01','analysis_date':'2026-11-02','parents':['2026-11-01-final'],'method_update':'Clustering comparison and metadata-only full-text checklist; corpus, embeddings, citations and capability cells unchanged.'}
    manifest['files'].update(fulltextDownloads='downloads/fulltext-downloads.json',fulltextChecklist='downloads/fulltext-download-checklist.csv',fulltextFirstBatch='downloads/fulltext-first-batch.csv',clusteringStudy='clustering-comparison.json')
    extra=read(study/'downloads/fulltext-downloads.json')['counts'];manifest['counts'].update(download_checklist_records=extra['records'],download_first_batch=extra['first_batch'],download_links=extra['with_download_or_oa_link'],selected_topic_groups=selection['full']['clusters'],baseline_unclustered=int((baseline<0).sum()),umap_density_unclustered=int((density<0).sum()))
    for key in ('received_pdf_files','first_batch_received','first_batch_identity_consistent','first_batch_identity_review_required'):
        if key in extra:manifest['counts'][key]=extra[key]
    manifest['limitations'].append({'title':'Exploratory grouping and new PDF acquisition','detail':'The method comparison uses unsupervised proxies and a prespecified browsing-coverage constraint, with three 80% subsample fits per pipeline. Partitions are not confidence estimates. Newly received private PDFs are pending evidence/rights assessment and are not used in this snapshot’s answers or capability matrix.'})
    manifest['counts']['limitations_count']=len(manifest['limitations'])
    write(out/'counts.json',manifest['counts']);write(out/'manifest.json',manifest)
    # Existing papers and evidence are unchanged; a method update is not new literature.
    diff={'parent':'2026-11-01-final','current':'2026-11-02-methods','added':[],'removed':[],'version_changes':[],'citation_count_changes':[],'status':'Method update only; no paper metadata, citations, embeddings or full-text evidence changed.','method_update':manifest['snapshot']['method_update']};write(out/'diff.json',diff)
    archive=out/'archives/2026-11-01-final';archive.mkdir(parents=True,exist_ok=True)
    write(archive/'manifest.json',read(parent/'manifest.json'));write(archive/'papers-index.json',read(parent/'papers-index.json'))
    lines=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Frozen atlas metadata · 2026-11-01-final</title><style>body{font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:0 20px}li{margin:14px 0}a{color:#176573}</style><h1>Frozen corpus metadata</h1><p>Snapshot 2026-11-01-final. '+str(len(index))+' retained records. Abstracts and full texts are not included in this archive. The original density grouping remains available in the live atlas.</p><a href="/agent-memory/?clustering=baseline">Inspect the original HDBSCAN grouping</a><ol>']
    for paper in read(parent/'papers-index.json'):
        lines.append('<li>'+html.escape(paper['title'])+' · '+html.escape(str(paper.get('year') or 'year not recorded'))+' · '+html.escape(paper['tier'])+'</li>')
    tmp=archive/'index.html.new';tmp.write_text(''.join(lines)+'</ol></html>');os.replace(tmp,archive/'index.html')
    manifest['snapshot']['archives']=[*manifest['snapshot'].get('archives',[]),{'id':'2026-11-01-final','label':'Original final corpus metadata','url':'/agent-memory/data/archives/2026-11-01-final/index.html'}]
    write(out/'manifest.json',manifest)
    hashes=inventory(out);hashes.pop('FILES.sha256.json',None);write(out/'FILES.sha256.json',hashes)
    assert before==inventory(parent),'Parent snapshot changed'
    assert len(maps)==len(graph['nodes'])==len(index)==3660
    receipt={'status':'passed','parent_unchanged':True,'parent_inventory_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),'derived_snapshot':'2026-11-02-methods','corpus_snapshot':'2026-11-01-final','selected':selected,'papers':len(ids),'full_texts_assessed':manifest['counts']['full_text_works'],'citation_edges':sum(e.get('type')=='citation' for e in graph['edges']),'matrix_sha256_unchanged':sha(parent/'matrix.json')==sha(out/'matrix.json'),'input_vectors_sha256_unchanged':sha(private/'vectors.float16.npy')==protocol['vectors_sha256'],'public_files':len(hashes)+1}
    write(study/'METHOD-UPDATE-VERIFICATION.json',receipt);print(json.dumps(receipt),flush=True)
    if site_data:
        assert site_data.resolve()!=out.resolve() and site_data.name=='data'
        next_data=site_data.with_name('.method-data-next');previous_data=site_data.with_name('.method-data-previous')
        if next_data.exists():shutil.rmtree(next_data)
        if previous_data.exists():shutil.rmtree(previous_data)
        shutil.copytree(out,next_data,copy_function=os.link)
        if site_data.exists():os.replace(site_data,previous_data)
        os.replace(next_data,site_data)
        if previous_data.exists():shutil.rmtree(previous_data)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--study',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--site-data',type=Path);a=p.parse_args();build(a.private,a.study,a.parent,a.out,a.site_data)
