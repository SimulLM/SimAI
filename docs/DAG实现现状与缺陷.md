> 2026-10-31 第一阶段补充核验：核心结论在基线 `354a9289e65a7d4ef58b6d232c628c8ebd4789a2` 工作区仍成立；源码证据、AST 检查、backend 费用归属及 AICB 单位探针见 [第一阶段核验报告](dag/phase1/source-audit.md)。下文保留原 `0a1882f` 的历史追踪；最新可复现证据以第一阶段报告及运行 manifest 为准。

根据当前代码，上一条结论可以进一步明确为：

**项目已有请求级离散事件仿真、阶段级资源调度，以及底层通信 flow 的依赖执行；但用于统一调度“计算节点＋通信节点”的请求级 DAG 引擎尚未接通。**

以下基于当前提交 `0a1882f` 的源码追踪。关键要看三件事：**图在哪里创建、执行时是否读取图、完成事件是否解锁图中的后继。**

**1．已有 DAG 数据结构，能够创建计算与通信节点**

在 [request.py](/G:/github/SimAI/vidur-alibabacloud/vidur/entities/request.py:72) 中，每个请求包含：

```python
self.dag = nx.DiGraph()
```

其 [create_task()](/G:/github/SimAI/vidur-alibabacloud/vidur/entities/request.py:378) 创建计算任务并加入图：

```python
task = Task.from_type(...)
self.dag.add_node(task)
self.nodes[task.node_id] = task
```

[create_flow()](/G:/github/SimAI/vidur-alibabacloud/vidur/entities/request.py:392) 同样创建通信节点：

```python
flow = Flow.from_type(...)
self.dag.add_node(flow)
self.nodes[flow.node_id] = flow
```

因此，“计算节点、通信节点、节点间连边”已经有表示基础。

但这些方法只负责创建和保存对象，没有负责判断节点是否就绪、启动执行或安排完成事件。

**2．当前实际创建的请求图很粗，主要是 Prefill→Decode**

在 [splitwise_global_scheduler.py](/G:/github/SimAI/vidur-alibabacloud/vidur/scheduler/global_scheduler/splitwise_global_scheduler.py:342) 中：

```python
prefill_task = request.create_task(
    task_type=TaskType.PROMPT,
    prompt_size=request.num_prefill_tokens
)
decode_task = request.create_task(
    task_type=TaskType.TOKEN,
    token_size=request.num_decode_tokens - 1
)

request.dag.add_edge(prefill_task, decode_task)
request.root_node = prefill_task
```

对应的图是：

```text
整个 Prefill → 整个 Decode 阶段
```

这里没有展开出：

```text
Attention → TP 通信 → EP dispatch
          → 专家计算 → combine → 下一层
```

所以，当前 DAG 表示还没有达到你要求的计算、通信操作粒度。

**3．存在插入 KV 通信节点的函数，但当前调度路径没有执行它**

[add_kv_cache_transfer()](/G:/github/SimAI/vidur-alibabacloud/vidur/scheduler/global_scheduler/splitwise_global_scheduler.py:234) 的设计确实符合 DAG 思路：

```python
kv_transfer_flow = request.create_flow(
    FlowType.KVCacheTransfer,
    size=flow_size,
    src=src_replica,
    dest=dest_replica
)

request.dag.remove_edge(prefill_task, decode_task)
request.dag.add_edge(prefill_task, kv_transfer_flow)
request.dag.add_edge(kv_transfer_flow, decode_task)
```

它会将图改为：

```text
Prefill → KV transfer → Decode
```

但是，[当前 schedule() 中调用它的代码](/G:/github/SimAI/vidur-alibabacloud/vidur/scheduler/global_scheduler/splitwise_global_scheduler.py:382) 位于 **382–431 行的三引号字符串内**：

```python
'''
...
self.add_kv_cache_transfer(...)
...
'''
```

我使用 Python AST 检查确认，这段是字符串表达式，不会执行。其中包含的函数调用不会发生。

这说明代码中保留了 DAG 设计，但这条 KV flow 接入路径当前没有启用。

**4．真正驱动执行的是请求队列、batch 和 stage**

先看实际调用链：

```text
GlobalScheduleEvent
  → 全局调度器分配请求
  → ReplicaScheduleEvent
  → 副本调度器组成 batch
  → ReplicaStageScheduleEvent
  → stage 执行时间预测
  → BatchStageEndEvent
```

[GlobalScheduleEvent](/G:/github/SimAI/vidur-alibabacloud/vidur/events/global_schedule_event.py:30) 消费的是“请求到副本的映射”：

```python
self._request_mapping = scheduler.schedule()

for replica_id, request in self._request_mapping:
    scheduler.get_replica_scheduler(replica_id).add_request(request)
```

副本调度器的 [_get_next_batch()](/G:/github/SimAI/vidur-alibabacloud/vidur/scheduler/replica_scheduler/splitwise_replica_scheduler.py:315) 主要遍历：

```python
for request in self._request_queue:
```

并检查请求类型、token 预算、batch 上限和显存分配条件。

**它选择执行对象的依据是请求状态与队列条件，没有通过 `request.dag` 的前驱完成情况寻找 ready 节点。**

我还扫描了 Vidur 中可执行的 DAG 相关调用：图操作集中在请求对象和 Splitwise 全局调度器，未发现主事件调度链通过这张请求图解锁后继的路径。

**5．已有资源调度，但粒度主要是整个 stage**

在 [ReplicaStageScheduler.on_schedule()](/G:/github/SimAI/vidur-alibabacloud/vidur/scheduler/replica_stage_scheduler/replica_stage_schduler.py:39) 中：

```python
if self._is_busy or not self._batch_queue:
    return None, None, None

self._is_busy = True
batch = self._batch_queue.pop(0)

execution_time = self._execution_time_predictor.get_execution_time(
    batch,
    self._stage_id,
)

total_execution_time = execution_time.total_time
```

这段代码实现了：

- stage 忙时不能执行新 batch；
- stage 空闲时取一个 batch；
- 预测这个 batch 在 stage 上的整体耗时。

在 [ReplicaStageScheduleEvent](/G:/github/SimAI/vidur-alibabacloud/vidur/events/replica_stage_schedule_event.py:57) 中，再安排：

```python
BatchStageEndEvent(
    self.time + self._batch_stage.execution_time,
    ...
)
```

因此，当前资源占用关系近似为：

```text
stage 空闲
  → 整个 batch-stage 开始
  → 经过汇总 execution_time
  → 整个 batch-stage 完成
```

这已经是有效的资源约束与时间推进机制。但它还没有统一表达“某个计算节点占 GPU、某个通信节点占 NIC，两者按 DAG 依赖并行或等待”。

**6．完成事件继续推进预设流程，没有通用的后继解锁机制**

在 [BatchStageEndEvent.handle_event()](/G:/github/SimAI/vidur-alibabacloud/vidur/events/batch_stage_end_event.py:35) 中，完成后会：

1. 调用 `on_stage_end()`，释放 stage 的忙状态；
2. 触发当前 stage 的下一次调度；
3. 根据是否为最后一个 stage，选择触发：
   - `BatchEndEvent`；
   - 或下一 stage 的 `BatchStageArrivalEvent`。

执行关系由这些事件处理函数明确规定。

而通用 DAG 引擎还需要在节点完成后执行类似逻辑：

```python
# 示意：目标机制，当前请求执行链尚未实现
for successor in graph.successors(completed_node):
    successor.remaining_predecessors -= 1

    if successor.remaining_predecessors == 0:
        ready_queue.push(successor)
```

再根据资源是否可用决定启动时间。当前请求级 DAG 没有形成这套执行闭环。

**7．PD 与 MoE 耗时目前怎样影响时间线？**

PD 在 [BatchEndEvent](/G:/github/SimAI/vidur-alibabacloud/vidur/events/batch_end_event.py:104) 中直接计算：

```python
request.pd_p2p_comm_time = (
    request.pd_p2p_comm_size / request.pd_p2p_comm_bandwidth
)

request.decode_arrived_at = (
    request.prefill_completed_at + request.pd_p2p_comm_time
)
```

随后在第 144 行安排：

```python
ReplicaScheduleEvent(
    request.decode_arrived_at,
    request.decode_replica_id
)
```

因此，**KV 迁移延迟已经会推迟 Decode，但主要通过直接修改到达时间实现**。它没有经过前面定义的 `KVCacheTransferFlow` 节点完成事件。

MoE 的 AICB 分支也主要采用汇总方式。在 [ExecutionTime](/G:/github/SimAI/vidur-alibabacloud/vidur/entities/execution_time.py:599) 中：

```python
moe_comm_time = moe_comm_size / cur_bw
moe_time = moe_comp_time + moe_comm_time
```

然后[按层累加](/G:/github/SimAI/vidur-alibabacloud/vidur/entities/execution_time.py:1182)：

```python
return att_time + mlp_time + moe_time
```

这条路径可以让通信估计进入执行时间，但没有将 dispatch、不同专家计算、combine 展开为独立节点进行资源调度。

**8．需要特别限定：底层通信已经有依赖执行能力**

不能据此说整个 SimAI 都没有 DAG 式依赖。

在 Astra-Sim 的 [NcclFlowModel.cc](/G:/github/SimAI/astra-sim-alibabacloud/astra-sim/system/collective/NcclFlowModel.cc:127) 中，已有 flow 入度初始化：

```cpp
indegree_mapping[flow_id] = parent_flow_id.size();
```

并在相关完成处理中[递减后继入度](/G:/github/SimAI/astra-sim-alibabacloud/astra-sim/system/collective/NcclFlowModel.cc:192)：

```cpp
if (--indegree_mapping[next_flow_id] == 0) {
    ...
}
```

这正是依赖驱动的执行基础，但它处理的是**集合通信内部 flows 的依赖**。

你提出的目标则还需要统一处理：

```text
请求 / batch
  → 计算节点
  → TP / EP 通信节点
  → 专家计算节点
  → PD KV 迁移节点
```

两者处于不同粒度。底层 flow 执行能力可以复用，上层请求任务图仍需要接通。

对应你的实施路径，源码支持的判断是：

| 要求 | 代码证据 | 判断 |
|---|---|---|
| 定义计算、通信节点与依赖 | `Task`、`Flow`、`request.dag` | 已有表示基础 |
| 将推理展开为操作级 DAG | 当前主要建立 Prefill→Decode | 尚未完成 |
| 预测计算、通信时延 | 预测器、画像、通信后端 | 已有基础能力 |
| 按 DAG 依赖调度 GPU/NIC 等资源 | 主链采用请求队列和 stage 汇总耗时 | 尚未形成统一实现 |
| 用 DAG 支撑 PD、动态 MoE | PD 直接延后到达；MoE 部分路径汇总估时 | 仍需集成 |

**所以，下一步应围绕现有事件队列和预测器，接入“节点就绪→资源分配→执行完成→解锁后继”的请求级执行机制，并复用底层通信 flow 的能力。** 以上是源码与 AST 检查结论，未将注释或计划当作运行验收证据。
