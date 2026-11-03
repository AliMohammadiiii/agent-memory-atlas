"""Frozen, server-side exploratory clustering comparison; never re-embed."""
import argparse,hashlib,importlib.metadata,json,os,time
from collections import Counter
from pathlib import Path
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score,silhouette_score
from sklearn.neighbors import NearestNeighbors

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');os.replace(temporary,path)

def canonical(labels,ids):
    sizes=Counter(int(x) for x in labels if x>=0)
    order=sorted(sizes,key=lambda c:(-sizes[c],min(ids[i] for i in np.where(labels==c)[0])))
    remap={c:i for i,c in enumerate(order)}
    return np.array([remap.get(int(c),-1) for c in labels],dtype=np.int32)

def neighbors(x,cache):
    if 'knn' not in cache:
        nn=NearestNeighbors(n_neighbors=min(31,len(x)),metric='cosine',algorithm='brute',n_jobs=1).fit(x)
        distances,indices=nn.kneighbors(x)
        rows=[];scores=[]
        for i in range(len(x)):
            keep=[j for j in range(indices.shape[1]) if indices[i,j]!=i][:30]
            rows.append(indices[i,keep]);scores.append(1-distances[i,keep])
        cache['knn']=(np.array(rows),np.array(scores))
    return cache['knn']

def fit(x,ids,spec,seed,cache,protocol):
    if spec['family']=='hdbscan':
        import hdbscan
        space=spec['space']
        if space=='original':z=x
        elif space in cache:z=cache[space]
        elif space=='pca50':
            z=PCA(n_components=min(50,x.shape[1],len(x)-1),random_state=seed,svd_solver='full').fit_transform(x);cache[space]=z
        else:
            import umap
            z=umap.UMAP(**protocol['umap'],random_state=seed,transform_seed=seed).fit_transform(x);cache[space]=z
        labels=hdbscan.HDBSCAN(min_cluster_size=spec['min_cluster_size'],min_samples=spec['min_samples'],metric='euclidean',cluster_selection_method=spec['selection'],core_dist_n_jobs=1,approx_min_span_tree=False).fit_predict(z.astype(np.float64))
    elif spec['family']=='kmeans':
        labels=KMeans(n_clusters=spec['clusters'],n_init=10,random_state=seed).fit_predict(x)
    else:
        import igraph as ig
        import leidenalg as la
        indices,scores=neighbors(x,cache);pairs={}
        for i in range(len(x)):
            for j,score in zip(indices[i,:spec['neighbors']],scores[i,:spec['neighbors']]):
                if score<=0:continue
                a,b=sorted((i,int(j)));pairs[(a,b)]=float(score)**2
        keys=sorted(pairs);graph=ig.Graph(n=len(x),edges=keys,directed=False)
        partition=la.find_partition(graph,la.RBConfigurationVertexPartition,weights=[pairs[e] for e in keys],resolution_parameter=spec['resolution'],seed=seed,n_iterations=-1)
        labels=np.array(partition.membership);labels[np.array(graph.degree())==0]=-1
    return canonical(labels,ids)

def metrics(x,labels,cache,protocol):
    assigned=labels>=0;sizes=Counter(int(c) for c in labels if c>=0);n=int(assigned.sum())
    silhouette=None
    if len(sizes)>1 and n>len(sizes):
        silhouette=float(silhouette_score(x[assigned],labels[assigned],metric='cosine',sample_size=min(protocol['silhouette_sample_size'],n),random_state=protocol['random_seed']))
    indices,_=neighbors(x,cache);k=min(15,indices.shape[1])
    agreement=float(np.mean(labels[indices[assigned,:k]]==labels[assigned,None])) if n else 0.0
    return {'papers':len(x),'assigned':n,'unassigned':len(x)-n,'coverage':n/len(x),'clusters':len(sizes),'cluster_sizes':dict(sorted(sizes.items())),'largest_cluster_fraction':max(sizes.values(),default=0)/len(x),'original_cosine_silhouette':silhouette,'original_15nn_label_agreement':agreement,'assignment_semantics':'Density confidence / noise' if protocol.get('_family')=='hdbscan' else 'Partition assignment; not a confidence estimate'}

def main(private,out,protocol_path):
    protocol=json.loads(protocol_path.read_text());out.mkdir(parents=True,exist_ok=True)
    frozen={'protocol_sha256':digest(protocol_path),'vectors_sha256':digest(private/'vectors.float16.npy'),'vector_manifest_sha256':digest(private/'vector_manifest.json'),'papers_sha256':digest(private/'papers.private.json'),'analytics_sha256':digest(private/'analytics.private.json')}
    freeze=out/'PROTOCOL-FROZEN.json'
    if freeze.exists():assert json.loads(freeze.read_text())==frozen,'Frozen inputs changed'
    else:write(freeze,frozen)
    manifest=json.loads((private/'vector_manifest.json').read_text());ids=[r['id'] if isinstance(r,dict) else r for r in manifest['documents']]
    order=np.argsort(ids);ids=[ids[i] for i in order];x=np.load(private/'vectors.float16.npy').astype(np.float32)[order];x/=np.linalg.norm(x,axis=1,keepdims=True)
    papers={p['id']:p for p in json.loads((private/'papers.private.json').read_text())};full_cache={};runs=[];assignments={}
    for spec in protocol['pipelines']:
        start=time.monotonic();labels=fit(x,ids,spec,protocol['random_seed'],full_cache,protocol);assignments[spec['id']]=labels.tolist()
        m=metrics(x,labels,full_cache,{**protocol,'_family':spec['family']});runs.append({'id':spec['id'],'parameters':spec,'full':m,'subsamples':[],'full_fit_seconds':time.monotonic()-start})
        write(out/'full-results.json',runs);write(out/'assignments.private.json',assignments);print(json.dumps({'stage':'full','id':spec['id'],'metrics':m}),flush=True)
    original=json.loads((private/'analytics.private.json').read_text());old={n['id']:n['cluster_id'] for n in original['nodes']};baseline_check=float(adjusted_rand_score([old[i] for i in ids],assignments['baseline']))
    assert baseline_check==1.0,'Baseline could not be reproduced exactly'
    for seed in protocol['subsample_seeds']:
        rng=np.random.default_rng(seed);subset=np.sort(rng.choice(len(ids),int(len(ids)*protocol['subsample_fraction']),replace=False));subx=x[subset];subids=[ids[i] for i in subset];cache={}
        for run in runs:
            labels=fit(subx,subids,run['parameters'],protocol['random_seed'],cache,protocol);reference=np.array(assignments[run['id']])[subset];joint=(labels>=0)&(reference>=0)
            both_score=float(adjusted_rand_score(reference[joint],labels[joint])) if joint.sum()>1 else None
            run['subsamples'].append({'seed':seed,'papers':len(subset),'all_ari_including_noise':float(adjusted_rand_score(reference,labels)),'joint_assigned_papers':int(joint.sum()),'joint_assignment_fraction':float(joint.mean()),'joint_assigned_ari':both_score})
            write(out/'results-progress.json',runs);print(json.dumps({'stage':'subsample','pipeline':run['id'],'seed':seed,'ari':both_score}),flush=True)
    eligible=[];policy=protocol['selection']
    for run in runs:
        full=run['full'];joint=[r['joint_assigned_ari'] for r in run['subsamples'] if r['joint_assigned_ari'] is not None];stability=float(np.median(joint)) if joint else 0.0
        run['median_joint_assigned_ari']=stability;run['median_all_ari_including_noise']=float(np.median([r['all_ari_including_noise'] for r in run['subsamples']]))
        reasons=[]
        if full['coverage']<policy['minimum_coverage']:reasons.append('coverage below prespecified exploratory usability threshold')
        if not policy['minimum_clusters']<=full['clusters']<=policy['maximum_clusters']:reasons.append('cluster count outside prespecified range')
        if full['largest_cluster_fraction']>policy['maximum_cluster_fraction']:reasons.append('giant cluster')
        if full['original_cosine_silhouette'] is None or full['original_cosine_silhouette']<policy['minimum_original_cosine_silhouette']:reasons.append('nonpositive separation in original embedding space')
        if min(r['joint_assignment_fraction'] for r in run['subsamples'])<policy['minimum_joint_assignment_fraction']:reasons.append('insufficient common assigned support for stability estimate')
        run['eligibility_failures']=reasons;run['selection_score']=0.5*stability+0.25*full['original_15nn_label_agreement']+0.25*((full['original_cosine_silhouette'] or 0)+1)/2
        if not reasons:eligible.append(run)
    selected=sorted(eligible,key=lambda r:(-r['selection_score'],r['id']))[0]['id'] if eligible else 'baseline'
    # Diagnostics are measured in the original representation, not the 2-D display.
    rng=np.random.default_rng(protocol['random_seed']);a=rng.integers(0,len(x),10000);b=rng.integers(0,len(x),10000);valid=a!=b;distance=1-np.sum(x[a[valid]]*x[b[valid]],axis=1)
    selected_labels=np.array(assignments[selected]);idx,_=neighbors(x,full_cache);purity=np.mean(selected_labels[idx[:,:15]]==selected_labels[:,None],axis=1)
    row_ids=rng.choice(len(ids),min(100,len(ids)),replace=False)
    import csv
    with (out/'owner-cluster-review.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['paper_id','title','cluster','neighbor_paper_id','neighbor_title','owner_same_topic','notes'])
        for i in row_ids:
            j=int(idx[i,0]);writer.writerow([ids[i],papers[ids[i]]['title'],int(selected_labels[i]),ids[j],papers[ids[j]]['title'],'',''])
    report={'id':protocol['id'],'selected_pipeline':selected,'selection_rule':policy,'runs':runs,'baseline_reproduced_ari':baseline_check,'input_provenance':frozen,'embedding_parameters':manifest.get('parameters'), 'papers':len(ids),'tier_counts':dict(Counter(papers[i]['tier'] for i in ids)),'random_pair_cosine_distance':{'pairs':int(valid.sum()),'mean':float(distance.mean()),'sd':float(distance.std()),'coefficient_of_variation':float(distance.std()/distance.mean())},'selected_local_15nn_agreement':{'mean':float(purity.mean()),'below_half':int((purity<0.5).sum()),'interpretation':'Neighbour label agreement is an exploratory consistency diagnostic, not a calibrated confidence or human accuracy estimate.'},'interpretation':protocol['interpretation'],'sources':protocol['sources'],'human_validation':'pending owner cluster review','libraries':{name:importlib.metadata.version(name) for name in ['numpy','scikit-learn','umap-learn','hdbscan','igraph','leidenalg']}}
    write(out/'comparison.json',report);write(out/'paper-order.json',ids);write(out/'assignments.private.json',assignments)
    assert frozen['vectors_sha256']==digest(private/'vectors.float16.npy') and frozen['analytics_sha256']==digest(private/'analytics.private.json')
    print(json.dumps({'stage':'complete','selected':selected,'eligible':[r['id'] for r in eligible]}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);a=p.parse_args();main(a.private,a.out,a.protocol)
