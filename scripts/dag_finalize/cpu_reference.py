"""Independent Decimal workflow model; no SimAI/DAG imports or timeline inputs.

Known synthetic service times test resource/lifecycle arithmetic, not GPU accuracy.
The workload describes requests, routing, placement, phases and capacity.
"""
from decimal import Decimal
import heapq


def predict(case, costs):
    for name in ('requests','rounds','kv_slots'):
        if isinstance(case[name],bool) or not isinstance(case[name],int) or case[name]<1:
            raise ValueError(name+' must be a positive integer')
    if case['scenario'] not in ('dense','pd','moe','joint') or case['tp'] not in (1,2) or case['pp'] not in (1,2):
        raise ValueError('unsupported controlled scenario')
    if case['scenario'] in ('pd','joint') and case['rounds']<2:raise ValueError('PD requires prefill and decode')
    work={}
    capacities={k:1 for k in ('gpu:p0','gpu:p1','gpu:d0','gpu:d1','link:fabric','link:p','link:d','link:pd')}
    capacities.update({'kv:p':16*case['requests'],'kv:d':16*case['kv_slots']})
    def add(r,name,duration=0,needs=(),parents=(),hold=None,free=None,commit=None,pin=None):
        key=f'r{r:02d}/'+name
        value=Decimal(str(duration))
        if not value.is_finite() or value<0:raise ValueError('invalid service cost')
        work[key]=dict(duration=value,needs=dict(needs),parents=set(parents),hold=hold,free=free,commit=commit,pin=pin)
        return key
    def link(side):return 'link:fabric' if case['shared_link'] else 'link:'+side
    def gpu(side,rank=0):return 'gpu:'+side+str(rank)
    for r in range(case['requests']):
        first=add(r,'00.arrival',Decimal(str(costs['arrival_gap_s']))*r)
        pd=case['scenario'] in ('pd','joint')
        moe=case['scenario'] in ('moe','joint')
        if pd:
            first=add(r,'01.source_reserve',needs=[('kv:p',16)],parents=[first],hold=('kv:p',16,'source'))
        cursor=first
        phases=[('p',0)] + ([('d',i) for i in range(1,case['rounds'])] if pd else [('p',i) for i in range(1,case['rounds'])])
        for side,index in phases:
            tag=f'{10+index:02d}.'
            compute=add(r,tag+'attention',costs['compute_s'],[(gpu(side,rank),1) for rank in range(case['tp'])],[cursor])
            if case['tp']>1:
                compute=add(r,tag+'tp',costs['comm_s'],[(gpu(side,rank),1) for rank in range(case['tp'])]+[(link(side),1)],[compute])
            branches=[]
            if moe:
                route=add(r,tag+'route',costs['route_s'],[(gpu(side),1)],[compute])
                counts=[0]*4
                mode=case['routing']
                if mode=='alternating':mode='balanced' if index%2==0 else 'hotspot'
                for token in range(4):counts[token%4 if mode=='balanced' else 0]+=1
                for expert,count in enumerate(counts):
                    if not count:continue
                    rank=0 if case['colocated'] else expert//2
                    target=gpu(side,rank);node=route
                    communication=[(link(side),1)] + ([] if case['independent_comm'] else [(gpu(side),1),(target,1)])
                    if rank:
                        node=add(r,tag+f'e{expert}.dispatch',Decimal(str(costs['comm_s']))*count,communication,[node])
                    node=add(r,tag+f'e{expert}.up',Decimal(str(costs['expert_s']))*count,[(target,1)],[node])
                    node=add(r,tag+f'e{expert}.down',Decimal(str(costs['expert_s']))*count,[(target,1)],[node])
                    if rank:
                        node=add(r,tag+f'e{expert}.combine',Decimal(str(costs['comm_s']))*count,communication,[node])
                    branches.append(node)
                compute=add(r,tag+'join',parents=branches)
            if case['pp']>1:
                compute=add(r,tag+'pp',costs['comm_s'],[(link(side),1),(gpu(side),1),(gpu(side,1),1)],[compute])
                compute=add(r,tag+'pp_compute',costs['compute_s'],[(gpu(side,1),1)],[compute])
            cursor=add(r,tag+'residual',costs['residual_s'],[(gpu(side),1)],[compute])
            if pd and index==0:
                pinned=add(r,'20.pin',parents=[cursor],pin='source')
                reserved=add(r,'21.destination_reserve',needs=[('kv:d',16)],parents=[cursor],hold=('kv:d',16,'destination'))
                moved=add(r,'22.transfer',0 if case['zero_transfer'] else costs['transfer_s'],
                    [(link('pd'),1),(gpu('p'),1),(gpu('d'),1)],[pinned,reserved])
                add(r,'23.source_release',parents=[moved],free='source')
                cursor=add(r,'24.KVReady',parents=[moved],commit='destination')
        if pd:cursor=add(r,'90.destination_release',parents=[cursor],free='destination')
        add(r,'99.terminal',parents=[cursor]+([f'r{r:02d}/23.source_release'] if pd else []))
    # Independent request-input expansion above; resource queue below uses Decimal.
    keys=sorted(work);sequence={key:i for i,key in enumerate(keys)}
    used={r:0 for r in capacities};state={k:'pending' for k in keys};times={};held={};pins=set();events=[];counter=0;now=Decimal(0)
    def dispatch():
        nonlocal counter
        for key in keys:
            if state[key]=='pending' and all(state[p]=='done' for p in work[key]['parents']):
                state[key]='ready';times[key]=dict(ready_s=now)
        ready=sorted((k for k in keys if state[k]=='ready'),key=lambda k:(times[k]['ready_s'],sequence[k]))
        for key in ready:
            item=work[key]
            if any(used[r]+n>capacities[r] for r,n in item['needs'].items()):continue
            for r,n in item['needs'].items():used[r]+=n
            state[key]='running';times[key].update(start_s=now,end_s=now+item['duration'])
            heapq.heappush(events,(now+item['duration'],counter,key));counter+=1
    dispatch()
    while events:
        now,_,key=heapq.heappop(events);item=work[key]
        for resource,amount in item['needs'].items():used[resource]-=amount
        owner=key.split('/')[0]
        if item['hold']:
            resource,amount,kind=item['hold'];used[resource]+=amount;held[owner,kind]=(resource,amount)
        if item['pin']:pins.add((owner,item['pin']))
        if item['commit'] and (owner,item['commit']) not in held:raise ValueError('commit without reservation')
        if item['free']:
            resource,amount=held.pop((owner,item['free']));used[resource]-=amount;pins.discard((owner,item['free']))
        state[key]='done';dispatch()
    if any(v!='done' for v in state.values()) or any(used.values()) or held or pins:
        raise ValueError('reference deadlock or leaked capacity')
    return dict(tasks={key:{k:float(v) for k,v in values.items()} for key,values in times.items()},
        completed={f'r{r:02d}':float(times[f'r{r:02d}/99.terminal']['end_s']) for r in range(case['requests'])},
        final_time_s=float(now),nature='synthetic_mechanism_reference',fit_parameters=0)
