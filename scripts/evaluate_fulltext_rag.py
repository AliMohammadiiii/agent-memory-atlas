"""Private, predetermined functional evaluation. Never captures user questions."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'server'),str(ROOT/'scripts')]
from gateway import Gateway
from fulltext import FulltextIndex

def run(private,index,output,cases_path):
    assert ROOT not in output.resolve().parents and output.resolve()!=ROOT
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    fixture=json.loads(cases_path.read_text());(output/'FROZEN-CASES.json').write_bytes(cases_path.read_bytes())
    g=Gateway(private,fulltext=FulltextIndex(index));generate=g.generate;payloads=[]
    def observed(system,payload):
        result=generate(system,payload);payloads.append({'system':system,'payload':payload,'response':result});return result
    g.generate_fn=observed;rows=[]
    for case in fixture['cases']:
        paper=next(p for p in g.papers.values() if (p.get('display_short_name') or '').casefold()==case['alias'].casefold());pid=paper['id'];assert pid in g.fulltext.paper_ids
        payloads=[];start=time.monotonic();reply=g.ask(case['question'],paper_ids=[pid]);contract=True
        if reply['grounded']:
            contract=bool(reply['sources']) and all(s['id']==pid and s['evidence_level']=='fulltext' and type(s['page']) is int and s['page']>0 and not s['display_allowed'] and s['passage'] is None for s in reply['sources'])
            for record in payloads:
                if 'claims' not in record['payload']:continue
                for claim in record['payload']['claims']:
                    for support in claim['support']:
                        with g.fulltext.connect() as db:
                            import zlib
                            source=db.execute('SELECT body,paper_id FROM chunks WHERE chunk_id=?',(support.get('chunk_id'),)).fetchone()
                        contract=contract and bool(source) and source[1]==support['paper_id'] and support['span'] in zlib.decompress(source[0]).decode()
        expected=reply['grounded'] if case['expect']=='supported' else not reply['grounded']
        row={'id':case['id'],'paper_id':pid,'expected':case['expect'],'grounded':reply['grounded'],'contract_passed':contract,'expectation_passed':bool(expected),'seconds':round(time.monotonic()-start,3),'model':reply.get('model'),'verifier':reply.get('verification_model'),'diagnostics':reply.get('diagnostics'),'refusal_reason':reply.get('refusal_reason'),'source_pages':[s.get('page') for s in reply['sources']]}
        rows.append(row);(output/(case['id']+'.private.json')).write_text(json.dumps({'case':case,'reply':reply,'trace':payloads},ensure_ascii=False,indent=2)+'\n');print(json.dumps(row),flush=True)
    report={'fixture_id':fixture['id'],'fixture_sha256':hashlib.sha256(cases_path.read_bytes()).hexdigest(),'cases':len(rows),'supported_expected':sum(r['expected']=='supported' for r in rows),'refusals_expected':sum(r['expected']=='refusal' for r in rows),'expectations_passed':sum(r['expectation_passed'] for r in rows),'citation_contracts_passed':sum(r['contract_passed'] for r in rows),'human_accuracy_estimate':False,'rows':rows}
    (output/'REPORT.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--index',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--cases',type=Path,required=True);a=p.parse_args();run(a.private,a.index,a.out,a.cases)
