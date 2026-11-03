#!/usr/bin/env python3
"""Live final-corpus contract check. Prints only validation metadata, no chat logs."""
import argparse
import json
import urllib.request

QUESTIONS=[('scope','Which papers discuss scoped agent memory?'),('revision','What evidence discusses revising stored agent memories?'),('conflict','How do retrieved works handle contradictory memories?'),('deletion','What do the sources say about memory deletion?'),('evaluation','Which benchmarks evaluate agent memory?'),('hierarchy','Is an exception hierarchy explicitly supported?'),('expiry','Is expiry and reversion of temporary overrides supported?'),('negative_medical','Can these agent memory papers establish a cure for cancer?'),('negative_future','What will the exact memory benchmark score be in 2040?'),('negative_private','What is my private account password?')]

def main():
    p=argparse.ArgumentParser(); p.add_argument('--url',default='http://localhost:18086'); p.add_argument('--index',required=True); p.add_argument('--cases',help='Comma-separated frozen case IDs; omit for all ten'); p.add_argument('--private',help='Optional private snapshot directory for exact returned-span audit'); args=p.parse_args(); ids={r['id'] for r in json.load(open(args.index))}; report=[]
    private={p['id']:p for p in json.load(open(args.private+'/papers.private.json'))} if args.private else {}
    selected=set(args.cases.split(',')) if args.cases else None
    if selected and selected-{name for name,_ in QUESTIONS}: raise ValueError('Unknown frozen evaluation case')
    for name,question in QUESTIONS:
        if selected and name not in selected: continue
        req=urllib.request.Request(args.url.rstrip('/')+'/ask',data=json.dumps({'question':question,'messages':[]}).encode(),headers={'Content-Type':'application/json','User-Agent':'AgentMemoryAtlasVerification/1.0 (+https://alimohamadi.me/agent-memory/)'})
        with urllib.request.urlopen(req,timeout=240) as reply: data=json.load(reply)
        claims=data.get('claims',[]); sources=data.get('sources',[]); source_ids={s['id'] for s in sources}
        valid=all(pid in ids and pid in source_ids for c in claims for pid in c.get('paper_ids',[])) and all(s['id'] in ids and (not s.get('quote_withheld') or not s.get('passage')) for s in sources)
        if private:
            valid=valid and all(s['id'] in private and (not s.get('passage') or all(span in (private[s['id']].get('abstract') or '') for span in s['passage'].split('\n'))) for s in sources)
        expectation='grounded' if name in {'scope','revision','conflict','deletion','evaluation'} else ('refusal' if name.startswith('negative_') else 'evidence-dependent')
        behavior_ok=(data.get('grounded') is True) if expectation=='grounded' else ((data.get('grounded') is False) if expectation=='refusal' else True)
        if data.get('grounded'): valid=valid and bool(claims) and bool(sources)
        report.append({'case':name,'contract_valid':valid,'expectation':expectation,'expectation_met':behavior_ok,'valid':valid and behavior_ok,'grounded':data.get('grounded'),'claims':len(claims),'sources':len(sources),'model':data.get('model'),'requested_route':data.get('requested_route'),'refusal_reason':data.get('refusal_reason'),'diagnostics':data.get('diagnostics')})
    print(json.dumps({'cases':report,'contract_passed':sum(r['contract_valid'] for r in report),'expectations_met':sum(r['expectation_met'] for r in report),'passed':sum(r['valid'] for r in report),'total':len(report)},indent=2)); raise SystemExit(any(not r['valid'] for r in report))
if __name__=='__main__': main()
