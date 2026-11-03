"""Five predeclared full-data seeds; preserve the selected method and corpus."""
import argparse,json,os,itertools
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score
from compare_clustering import fit,metrics,write,digest

def run(private,out,protocol):
 cfg=json.loads(protocol.read_text());base=json.loads((Path(__file__).resolve().parents[1]/'config/clustering-study-2026-11-02.json').read_text());out.mkdir(parents=True,exist_ok=True)
 frozen={'protocol_sha256':digest(protocol),'vectors_sha256':digest(private/'vectors.float16.npy'),'seeds':cfg['stability_seeds'],'selection_unchanged':'leiden15-r1'}
 if (out/'STABILITY-FROZEN.json').exists():assert json.loads((out/'STABILITY-FROZEN.json').read_text())==frozen
 else:write(out/'STABILITY-FROZEN.json',frozen)
 vm=json.loads((private/'vector_manifest.json').read_text());ids=[d['id'] if isinstance(d,dict) else d for d in vm['documents']];order=np.argsort(ids);ids=[ids[i] for i in order];x=np.load(private/'vectors.float16.npy').astype(np.float32)[order];x/=np.linalg.norm(x,axis=1,keepdims=True)
 results=[];assignments={}
 for seed in cfg['stability_seeds']:
  cache={}
  for spec in base['pipelines']:
   path=out/(spec['id']+'-'+str(seed)+'.json')
   if path.exists():row=json.loads(path.read_text());labels=np.array(row['labels'])
   else:
    labels=fit(x,ids,spec,seed,cache,base);m=metrics(x,labels,cache,{**base,'_family':spec['family']});row={'id':spec['id'],'seed':seed,'labels':labels.tolist(),'metrics':m};write(path,row)
   assignments[(spec['id'],seed)]=labels;print(json.dumps({'pipeline':spec['id'],'seed':seed}),flush=True)
 for spec in base['pipelines']:
  pairs=[]
  for a,b in itertools.combinations(cfg['stability_seeds'],2):
   la,lb=assignments[(spec['id'],a)],assignments[(spec['id'],b)];joint=(la>=0)&(lb>=0)
   pairs.append({'seeds':[a,b],'all_ari_including_noise':float(adjusted_rand_score(la,lb)),'jointly_assigned':int(joint.sum()),'joint_ari':float(adjusted_rand_score(la[joint],lb[joint])) if joint.sum()>1 else None})
  first=json.loads((out/(spec['id']+'-'+str(cfg['stability_seeds'][0])+'.json')).read_text());scores=[p['joint_ari'] for p in pairs if p['joint_ari'] is not None]
  results.append({'id':spec['id'],'parameters':spec,'reference':first['metrics'],'seeds':cfg['stability_seeds'],'pairs':pairs,'mean_joint_ari':float(np.mean(scores)),'min_joint_ari':min(scores),'max_joint_ari':max(scores),'mean_all_ari':float(np.mean([p['all_ari_including_noise'] for p in pairs]))})
 report={'selected_unchanged':'leiden15-r1','papers':len(ids),'seeds':cfg['stability_seeds'],'pair_count':10,'comparison':results,'interpretation':'Stability across random seeds is not human topic validity; deterministic density algorithms can have ARI=1 without broad coverage.'};write(out/'STABILITY-REPORT.json',report);print(json.dumps({'stability_complete':True,'pipelines':len(results)}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);a=p.parse_args();run(a.private,a.out,a.protocol)
