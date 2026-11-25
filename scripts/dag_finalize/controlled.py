"""Controlled Executor + KV API harness compared against independent arithmetic.

This does not replace original-CLI PD/MoE regressions or constitute E2E accuracy.
"""
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'vidur-alibabacloud')]
from scripts.dag_finalize.common import read,save,digest
from scripts.dag_finalize.cpu_reference import predict


def execute(case,costs):
    from schemas.dag.v1.contracts import CostEstimate,GraphContext,GraphFragment,Placement,ResourceDemand,TaskSpec,Lease
    from vidur.dag.resources import CapacityResourceManager,ResourceCapacity
    from vidur.dag.executor import DagExecutor
    from vidur.dag.runner import DagRunner
    from vidur.dag.trace import write_results
    from vidur.dag.expanded_trace import write_expanded_results
    capacities={name:ResourceCapacity(1,'permits') for name in ['gpu:p0','gpu:p1','gpu:d0','gpu:d1','link:fabric','link:p','link:d','link:pd']}
    capacities.update({'kv:p':ResourceCapacity(16*case['requests'],'bytes'),'kv:d':ResourceCapacity(16*case['kv_slots'],'bytes')})
    descriptions={};patches=[]
    # Build application TaskSpecs independently; never consume reference operations/times.
    for request in range(case['requests']):
        gid=f'r{request:02d}';nodes={};edges=[]
        def node(name,duration=0,resources=(),after=(),**metadata):
            demands=tuple(ResourceDemand(resource,amount,'bytes' if resource.startswith('kv:') else 'permits') for resource,amount in resources)
            component='sync' if duration==0 else ('pd' if name=='22.transfer' else 'ep' if '.e' in name and (name.endswith('dispatch') or name.endswith('combine')) else 'tp' if name.endswith('.tp') else 'pp' if name.endswith('.pp') else 'compute')
            nodes[name]=TaskSpec(name,'sync' if duration==0 else ('comm' if any(r.startswith('link:') for r,_ in resources) else 'compute'),
                Placement(),demands,CostEstimate(float(duration),'synthetic_finalize',float(duration),'s',1,'Frozen controlled workflow constants',(component,)),metadata)
            edges.extend((p,name) for p in after);return name
        def equipment(side,rank=0):return 'gpu:'+side+str(rank)
        def connection(side):return 'link:fabric' if case['shared_link'] else 'link:'+side
        separated=case['scenario'] in ('pd','joint');mixture=case['scenario'] in ('moe','joint')
        previous=node('00.arrival',costs['arrival_gap_s']*request)
        if separated:previous=node('01.source_reserve',resources=[('kv:p',16)],after=[previous],hold=['kv:p',16,'source'])
        for iteration in range(case['rounds']):
            side='d' if separated and iteration else 'p';prefix=f'{iteration+10:02d}.'
            previous=node(prefix+'attention',costs['compute_s'],[(equipment(side,k),1) for k in range(case['tp'])],[previous])
            if case['tp']>1:
                previous=node(prefix+'tp',costs['comm_s'],[(equipment(side,k),1) for k in range(case['tp'])]+[(connection(side),1)],[previous])
            if mixture:
                routing=node(prefix+'route',costs['route_s'],[(equipment(side),1)],[previous]);ends=[]
                strategy=case['routing']
                if strategy=='alternating':strategy=('balanced','hotspot')[iteration%2]
                assignments={i:[] for i in range(4)}
                for token in range(4):assignments[token%4 if strategy=='balanced' else 0].append(token)
                for expert,tokens in assignments.items():
                    if not tokens:continue
                    count=len(tokens);rank=0 if case['colocated'] else expert//2;device=equipment(side,rank);end=routing
                    net=[(connection(side),1)]
                    if not case['independent_comm']:net += [(equipment(side),1),(device,1)]
                    if rank:end=node(prefix+f'e{expert}.dispatch',costs['comm_s']*count,net,[end])
                    end=node(prefix+f'e{expert}.up',costs['expert_s']*count,[(device,1)],[end],assignments=count)
                    end=node(prefix+f'e{expert}.down',costs['expert_s']*count,[(device,1)],[end],assignments=count)
                    if rank:end=node(prefix+f'e{expert}.combine',costs['comm_s']*count,net,[end])
                    ends.append(end)
                previous=node(prefix+'join',after=ends)
            if case['pp']>1:
                previous=node(prefix+'pp',costs['comm_s'],[(connection(side),1),(equipment(side),1),(equipment(side,1),1)],[previous])
                previous=node(prefix+'pp_compute',costs['compute_s'],[(equipment(side,1),1)],[previous])
            previous=node(prefix+'residual',costs['residual_s'],[(equipment(side),1)],[previous])
            if separated and iteration==0:
                pin=node('20.pin',after=[previous],pin='source')
                reserve=node('21.destination_reserve',resources=[('kv:d',16)],after=[previous],hold=['kv:d',16,'destination'])
                moved=node('22.transfer',0 if case['zero_transfer'] else costs['transfer_s'],
                    [(connection('pd'),1),(equipment('p'),1),(equipment('d'),1)],[pin,reserve])
                node('23.source_release',after=[moved],free='source')
                previous=node('24.KVReady',after=[moved],commit='destination')
        if separated:previous=node('90.destination_release',after=[previous],free='destination')
        node('99.terminal',after=[previous]+(['23.source_release'] if separated else []))
        for name,spec in nodes.items():descriptions[gid,name]=dict(spec.metadata)
        patches.append(GraphFragment('1.0',gid,GraphContext(gid,0,'controlled',0,(gid,)),tuple(nodes[k] for k in sorted(nodes)),tuple(edges),'99.terminal'))
    class LifecycleManager(CapacityResourceManager):
        def __init__(self):
            super().__init__(capacities);self.held={};self.pin_handles={};self.lifecycle=[]
        def release(self,lease,now):
            wake=super().release(lease,now)
            if not isinstance(lease,Lease):return wake
            gid,name=lease.owner;meta=descriptions[lease.owner]
            if 'hold' in meta:
                resource,amount,kind=meta['hold'];handle=self.reserve((gid,kind),resource,amount)
                if handle is None:raise ValueError('controlled reservation failed after owned lease release')
                self.held[gid,kind]=handle
                if kind=='source':self.commit(handle,gid+':'+kind)
                self.lifecycle.append(dict(graph=gid,operation='reserve_'+kind,time_s=now))
            if 'pin' in meta:self.pin_handles[gid,meta['pin']]=self.pin((gid,'transfer'),gid+':source')
            if 'commit' in meta:
                kind=meta['commit'];self.commit(self.held[gid,kind],gid+':'+kind)
            if 'free' in meta:
                key=gid,meta['free']
                if key in self.pin_handles:self.unpin(self.pin_handles.pop(key),now)
                wake+=super().release(self.held.pop(key),now)
                self.lifecycle.append(dict(graph=gid,operation='release_'+meta['free'],time_s=now))
            return wake
    manager=LifecycleManager();executor=DagExecutor(manager,resource_units={k:v.unit for k,v in capacities.items()},ready_queue_policy='fcfs')
    runner=DagRunner(executor)
    completed={}
    def finish(gid,now):
        completed[gid]=now
        return ()
    for graph in patches:runner.submit(graph,0,finish)
    runner.run()
    if manager.held or manager.pin_handles or any(v['used'] for v in manager.usage_snapshot().values()):raise ValueError('controlled capacity leak')
    observed={gid+'/'+name:dict(ready_s=t.ready_at,start_s=t.start_at,end_s=t.end_at) for gid,g in executor.graphs.items() for name,t in g.tasks.items()}
    return runner,dict(tasks=observed,completed=completed,final_time_s=runner.now,lifecycle=manager.lifecycle)


def run(output,specification):
    from vidur.dag.trace import write_results
    from vidur.dag.expanded_trace import write_expanded_results
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    data=read(specification);save(output/'frozen-input.json',data)
    frozen=digest(output/'frozen-input.json');reports=[]
    for case in data['cases']:
        folder=output/case['id'];folder.mkdir()
        reference=predict(case,data['costs'])
        runner,actual=execute(case,data['costs'])
        save(folder/'reference.json',reference);save(folder/'actual.json',actual)
        errors=[]
        if set(reference['tasks'])!=set(actual['tasks']):errors.append('task identity mismatch')
        for key,expected in reference['tasks'].items():
            if key not in actual['tasks']:continue
            for field in ('ready_s','start_s','end_s'):
                if abs(expected[field]-actual['tasks'][key][field])>1e-12:errors.append(key+' '+field)
        write_results(folder,runner);write_expanded_results(folder,runner.executor)
        reports.append(dict(id=case['id'],scenario=case['scenario'],passed=not errors,errors=errors,
            tasks=len(actual['tasks']),requests=case['requests'],old_path_status='unsupported' if case['scenario'] in ('moe','joint') else 'not_compared',
            metric='controlled_workflow_timing',primary_e2e_eligible=False))
    if digest(output/'frozen-input.json')!=frozen:raise ValueError('controlled inputs changed')
    result=dict(status='passed' if all(r['passed'] for r in reports) else 'failed',cases=reports,input_sha256=frozen,
        reference_kind='synthetic_component_harness',fit_parameters=0,hardware_accuracy_claim=False,formal_e2e_accuracy_claim=False)
    save(output/'mechanism-consistency.json',result)
    return result
