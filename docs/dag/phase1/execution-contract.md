# DAG v1 执行契约

状态：阶段1接口冻结，执行器及资源管理器尚未实现。协议版本 `1.0`；破坏兼容性的字段或语义变更升级版本，并在本目录记录迁移说明。

## 边界与数据表示

一个 `GraphFragment` 表示一个 batch iteration 在一个 replica、一个 pipeline stage 上的执行。`context` 保留 batch、iteration、replica、stage 和 request IDs；跨图的 task ID 可以相同，运行身份是 `(graph_id, task_id)`。同一执行器中的 graph ID 不可重复提交。

静态 JSON 由 `schemas/dag/v1/graph.schema.json` 校验，类型声明由同目录 `contracts.py` 提供。Python tuple 对应 JSON array，Enum 对应其字符串值，dataclass 对应 JSON object；序列化不包含运行状态。结构约束之外，还必须调用 `validate_graph` 检查唯一性、引用、无环、收口、单位和聚合费用互斥。

任务类型为 `coarse/compute/comm/sync`。placement 描述设备与通信组；`demands` 才是实际占用声明，不能从 placement 自动推导额外占用。资源 ID 在整个执行器中唯一，例如 `gpu:replica0:0`、`nic:host0`、`kv:replica1`；资源注册表规定单位和容量。许可证使用正整数 `permits`，容量使用正整数 `bytes`；零需求通过空列表表达。

每张图恰好有一个终点：零时长、无资源需求的 `sync` 任务。所有叶子必须汇入它，允许终点之前有多个根和多级 join。最小单节点空工作图也使用该 terminal 表示。未知字段仅允许放在 task 的 metadata 内。

## 构图与现有推理链

`GraphBuilder.build(context)` 返回图；构图器通过初始化参数持有原 batch、predictor 和配置，context 只承载身份。`CostProvider.estimate(task, context)` 返回同一协议的 CostEstimate，不推进时间、不申请资源；图中 cost 为提交时冻结的估计快照，执行器不在运行中重复估时。

阶段4的 coarse 适配位置是 `ReplicaStageScheduleEvent` 当前安排 `BatchStageEndEvent` 的位置：保留原组批、Stage 忙状态和开始指标；提交一个 coarse 节点和 terminal，coarse cost 精确使用原 `ExecutionTime.total_time`。终点完成时才通过回调安排原 `BatchStageEndEvent`，不得同时保留旧路径直接安排的完成事件。

终端回调绑定原 batch、batch_stage、replica、stage、is_last_stage，签名为 `(graph_id, now_s) -> EventIntents`。适配层可在回调中把绑定的原 StageEnd 事件加入其待输出集合，返回空 tuple；不得从回调内递归推进 Simulator。回调恰好调用一次，原 StageEnd 继续负责 Stage 释放、指标、下一 Stage/BatchEnd；请求完成与 Token 推进保持原语义。

## 公共接口与事件适配

精确类型以 `contracts.py` 为准：

| 接口 | 返回与职责 |
|---|---|
| `GraphBuilder.build(context)` | `GraphFragment`，仅构图 |
| `CostProvider.estimate(task, context)` | `CostEstimate`，冻结耗时与来源 |
| `DagExecutor.submit(fragment, now, terminal_callback)` | `GraphHandle`，包含图 ID 和初始事件意图 |
| `DagExecutor.dispatch(now)` | `EventIntents`，尝试启动 READY 任务 |
| `DagExecutor.on_task_complete(graph_id, task_id, now)` | 释放已完成任务、解锁后继，返回后续事件意图 |
| `DagExecutor.append(patch, now)` | 原子校验并追加节点/边，返回事件意图 |
| `ResourceManager.try_acquire(owner, demands)` | 完整 `Lease` 或 None，失败不残留占用 |
| `ResourceManager.release(lease, now)` | 有序 `Wakeups`，待重新调度的 owner |
| `KVCapacity.reserve(owner, resource_id, storage_bytes)` | `Reservation` 或 None |
| `KVCapacity.commit(reservation, allocation_id)` | 预留转为已接收分配，不再次收费容量 |
| `KVCapacity.release(reservation, now)` | 取消预留或释放已提交容量；pin 未清除时不能释放 |
| `KVCapacity.pin(owner, allocation_id)` / `unpin(pin, now)` | 源已有分配增加/移除保留引用，不重复分配存储 |

EventIntent 为 `time_s/kind/owner`，kind 是 task_complete、dispatch 或 graph_failed。完成时刻和执行开始时刻由执行器返回，宿主适配层将其包装成原事件对象。集成模式只有 Simulator 的事件队列和秒时钟；独立 CLI 使用相同协议的最小堆适配器。`submit` 与 `append` 不隐式调用第二个事件循环。

`GraphAppend` 不更改图 ID 和 terminal ID，只能引用既有节点或本次新节点；新增任务 ID 不可重复，所有目标节点必须仍为 PENDING。追加后仍须无环且全部收口，终点 READY 后拒绝扩图。整次追加校验失败不得改动原图。未来 MoE 需要在终点 READY 之前，由仍 PENDING 的依赖屏障保护追加；阶段1不实现动态调度。

## 状态、时钟与异常

任务状态为 `PENDING → READY → RUNNING → COMPLETED`。所有前驱完成才 READY；资源不足保持 READY，单独记录 resource_wait。资源申请成功后启动，完成时先释放、再解锁后继。资源等待者与新就绪任务按稳定提交序号处理；不可用任务可以被跳过，让其他资源上的 READY 工作前进。

时间为有限非负 float 秒，事件按 `(time_s, insertion_sequence)` 排序，序号由单一宿主队列生成。相同输入与任务提交次序必须确定；同时间完成/零时长后继的事件允许追加，但不可安排过去事件。零时长任务仍只完成一次，资源占用为空时间区间。各子任务端到端耗时不以求和替代关键路径。

环、缺引用、重复 ID、非法 terminal、非法数值及资源单位不匹配均在启动前拒绝。重复完成、重复释放、重复 commit、重复 unpin 是协议错误：抛出明确异常，且不得再次解锁或释放。输入/契约异常使用 ValueError；运行期重复动作或不合法状态使用 RuntimeError。

运行期失败时标记任务 FAILED、图失败，停止新的任务启动；执行器取消/忽略该图后续完成事件并恰好一次清理其资源，发出 graph_failed，不调用成功回调。阶段2可令宿主中止该次仿真并输出失败；不定义重试和抢占。

## Cost 及资源所有权

CostEstimate 保存 `duration_s/source/raw_value/raw_unit/conversion_to_s/evidence/includes/unknown_components`。允许的时间单位及因子是 s=1、ms=1e-3、us=1e-6、ns=1e-9。raw_value 为聚合 cost 时，evidence 必须记录原公式与源码位置。includes 表示已知包含项，unknown_components 不可被解释为零费用。

一个片段采用 coarse 或 expanded 计费，禁止 coarse 与 compute/comm 同时计费。父级上下文不产生额外执行节点收费；CPU、PP 等残余费用若确实包含在 Stage cost 中，展开时必须分配到独立任务或一个残余任务，不能遗失。sync 只表示依赖；有实际时延的同步等待必须显式说明 cost 来源。

默认每设备一个 compute 许可，通信可以单独申请 NIC/通信组许可，也可以同时申请 compute 许可；多资源原子申请。coarse 模式由原 Stage 忙状态保留兼容排队，DAG 子资源租约不负责再次释放旧 Stage 忙状态。展开后的资源管理器是细粒度占用唯一所有者。

KV 存储量与 wire bytes 分开：reserve/commit 使用 storage_bytes，传输 task cost 使用 wire bytes。Gbps 为 `1e9/8 bytes/s`，Gib/s 为 `2**30/8 bytes/s`；旧代码中使用 1024 因子的历史语义仅记录，不静默修正。

## 三份手算图

输入与期望位于 `tests/fixtures/dag/v1/`。时间由微秒显式转换成秒：

| 图 | 任务/资源 | 期望 |
|---|---|---|
| serial | T1=3→T2=5→T3=2→terminal，共享 GPU | 10μs |
| fork_join | T1=3、T2=5 在不同 GPU，T3=2 等二者 | 7μs |
| resource_contention | T1=10、T2=4，T3=8 等二者 | 共 GPU=22μs，T2 独占 NIC=18μs，T2 同时占 NIC/GPU=22μs |

expected 文件记录容量、场景资源覆盖、完整任务起止和 makespan。阶段1只代数检查依赖、区间容量和给定答案，不生成调度；阶段2/3必须实际运行图并对照这些答案。资源场景覆盖只改变 demands，placement 是说明性信息，不能代替资源申请。
