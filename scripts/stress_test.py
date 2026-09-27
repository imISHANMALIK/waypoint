"""Bounded load test against an isolated local server. Never targets a live workspace."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import time

import httpx

ROOT=Path(__file__).resolve().parents[1]


async def exercise(base, requests, concurrency):
    timings={}; statuses={}; errors=[]
    async with httpx.AsyncClient(base_url=base,timeout=60,limits=httpx.Limits(max_connections=concurrency)) as client:
        wave=io.StringIO(); writer=csv.writer(wave);writer.writerow(['order_id','shelf','priority','due_minutes','units'])
        for i in range(250):
            writer.writerow([f'STRESS-{i:04}',f'{"ABCD"[i%4]}{1+(i//4)%4}','urgent' if i%5==0 else 'standard',15+i%80,1+i%4])
        uploaded=await client.post('/api/import',files={'file':('stress.csv',wave.getvalue())})
        uploaded.raise_for_status()
        gate=asyncio.Semaphore(concurrency)
        advances=0
        async def request(i):
            nonlocal advances
            if i%20==0:
                label,method,path,kwargs='plan','POST','/api/plans',{'json':{'objective':['throughput','on_time','distance'][i%3]}}
            elif i%4==0:
                label,method,path,kwargs='advance','POST','/api/advance',{'json':{'ticks':1}}
                advances+=1
            else:
                label,method,path,kwargs='read','GET','/api/workspace',{}
            async with gate:
                start=time.perf_counter()
                try:
                    res=await client.request(method,path,**kwargs)
                    statuses[str(res.status_code)]=statuses.get(str(res.status_code),0)+1
                    if res.status_code!=200:errors.append({'request':i,'status':res.status_code})
                except httpx.HTTPError as exc:
                    errors.append({'request':i,'error':type(exc).__name__})
                timings.setdefault(label,[]).append((time.perf_counter()-start)*1000)
        start=time.perf_counter()
        await asyncio.gather(*(request(i) for i in range(requests)))
        elapsed=time.perf_counter()-start
        state=(await client.get('/api/workspace')).json()
        assert state['tick']==advances, f'Lost update: {state["tick"]} != {advances}'
        ids=[r['order'] for r in state['robots'] if r['order']]
        assert len(ids)==len(set(ids)), 'Duplicate robot assignment'
        assert sum(o['status']==s for s in ['queued','picking','complete'] for o in state['orders'])==250
        plan=(await client.post('/api/plans',json={})).json()
        decisions=await asyncio.gather(*(client.post(f'/api/plans/{plan["id"]}/decision',json={'approved':True}) for _ in range(16)))
        decision_codes=[r.status_code for r in decisions]
        assert decision_codes.count(200)==1 and decision_codes.count(409)==15, decision_codes
        invalid=await client.post('/api/import',files={'file':('bad.csv','bad,header\n1,2')})
        assert invalid.status_code==422
        assert (await client.get('/api/workspace')).json()['metrics']['total']==250
        def summarize(values):
            ordered=sorted(values)
            return {'count':len(values),'median_ms':round(statistics.median(values),2),'p95_ms':round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],2),'max_ms':round(max(values),2)}
        return {'tested_at':datetime.now(timezone.utc).isoformat(),'environment':f'{platform.system()} {platform.machine()} / Python {platform.python_version()}',
                'scope':'isolated local API; deterministic mode; 250 orders; single worker','requests':requests,'concurrency':concurrency,
                'duration_seconds':round(elapsed,2),'requests_per_second':round(requests/elapsed,2),'status_counts':statuses,'errors':errors,
                'latency_by_operation':{k:summarize(v) for k,v in timings.items()},
                'invariants':{'no_lost_ticks':True,'unique_assignments':True,'order_count_preserved':True,
                              'approval_race':'1 applied / 15 rejected with HTTP 409','invalid_import_preserves_state':True},
                'limits':'Local synthetic load, not a production capacity guarantee. Excludes paid model latency, WAN latency and multi-worker deployments.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--requests',type=int,default=1000);parser.add_argument('--concurrency',type=int,default=32);parser.add_argument('--output',default='docs/stress-report.json');args=parser.parse_args()
    if not 1<=args.requests<=10000 or not 1<=args.concurrency<=128:parser.error('requests must be 1–10000 and concurrency 1–128')
    with tempfile.TemporaryDirectory(prefix='waypoint-stress-') as directory:
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        env={**os.environ,'WAYPOINT_DATA_DIR':directory,'WAYPOINT_MODEL':'','WAYPOINT_ACCESS_TOKEN':'','WAYPOINT_REQUIRE_AUTH':'0'}
        with open(Path(directory)/'server.log','w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                for _ in range(200):
                    try:
                        if httpx.get(base+'/api/health',timeout=.2).status_code==200:break
                    except httpx.HTTPError:time.sleep(.05)
                else:raise RuntimeError('Test server did not start')
                report=asyncio.run(exercise(base,args.requests,args.concurrency))
                path=ROOT/args.output;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(report,indent=2))
                if report['errors']:raise SystemExit(1)
            finally:server.terminate();server.wait(timeout=10)


if __name__=='__main__':main()
