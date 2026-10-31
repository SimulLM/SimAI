# LLM 推理 DAG 时间域仿真引擎：设计与实施计划

## 1. 目标与范围

**构建可执行的推理 DAG 时间域仿真引擎：按任务依赖和资源约束推进离散事件，输出任务开始、结束、等待时间及资源占用。**

建设主线：任务图 → 依赖就绪 → 资源分配 → 执行完成 → 激活后继。通信时延预测作为可替换的耗时提供器；PD 与动态 MoE 在同一引擎上扩展。

| 阶段 | 交付范围 | 完成标准 |
|---|---|---|
| 首月 | 固定 Batch、一轮阶段图；compute/collective/sync；容量1资源；常量与离线通信cost；时间线 | DAG可执行，手算正确，可复现；至少一条核验通过的SimAI通信cost进入节点执行 |
| 后续 | 接入Vidur Batch/Token；细化设备/网络/显存；PD KV；动态Expert与校准 | 请求与任务状态一致，依赖和争用可解释，误差与运行成本可测 |

首月不做动态组批、PD、逐kernel、在线ns-3、动态带宽公平分配或真实GPU画像。

## 2. 当前实现与缺口

### 2.1 当前执行链

```mermaid
flowchart LR
    W[请求生成] --> A[RequestArrivalEvent]
    A --> G[GlobalScheduleEvent]
    G --> R[ReplicaScheduleEvent / 组Batch]
    R --> S[Stage队列 / busy]
    S --> P[预测BatchStage总耗时]
    P --> E[BatchStageEndEvent]
    E --> N{末Stage?}
    N -->|否| S
    N -->|是| B[BatchEnd / 更新Token]
    B --> R
    B --> M[MetricsStore]
```

### 2.2 能力与待解决问题

| 模块 | 已有能力 | 主要缺口 | 代码定位 |
|---|---|---|---|
| 事件引擎 | heapq按事件时间推进 | 缺少完整的过去事件拒绝、同时间戳处理规则 | [Simulator.run/_add_event](../../vidur-alibabacloud/vidur/simulator.py#L67)、[BaseEvent](../../vidur-alibabacloud/vidur/events/base_event.py#L44) |
| 请求DAG | Task/Flow、NetworkX图；实际建立Prefill→Decode | 图未控制就绪、资源分配及完成解锁；KV插图调用未执行 | [Request](../../vidur-alibabacloud/vidur/entities/request.py#L378)、[Splitwise.schedule](../../vidur-alibabacloud/vidur/scheduler/global_scheduler/splitwise_global_scheduler.py#L342) |
| Batch/Stage | 请求组批、逐Token迭代、Stage排队互斥、PP转发 | Stage内部计算通信仍为汇总耗时，无统一物理GPU/NIC仲裁 | [ReplicaStageScheduler](../../vidur-alibabacloud/vidur/scheduler/replica_stage_scheduler/replica_stage_schduler.py#L39)、[StageEnd](../../vidur-alibabacloud/vidur/events/batch_stage_end_event.py#L42) |
| 通信 | TP可调用SimAI；集合内部flow按入度执行 | 返回隔离时延；不同请求/Batch不共享在线网络状态 | [TPTimePredictor](../../vidur-alibabacloud/vidur/execution_time_predictor/communication_time_predictor.py#L58)、[NcclFlowModel](../../astra-sim-alibabacloud/astra-sim/system/collective/NcclFlowModel.cc#L127) |
| PD | P/D配置、KV大小估计、静态size/bandwidth延迟 | 源KV提前释放；D提前入队且未比较当前时间与KV就绪时间，存在提前执行风险，待端到端复现 | [BatchEnd](../../vidur-alibabacloud/vidur/events/batch_end_event.py#L90)、[SplitwiseReplicaScheduler](../../vidur-alibabacloud/vidur/scheduler/replica_scheduler/splitwise_replica_scheduler.py#L226) |
| 显存 | block分配、MemoryPlanner与KV占用跟踪 | 多账本及MLA/TP/PP的存储、传输口径需统一 | [MemoryPlanner](../../vidur-alibabacloud/vidur/scheduler/utils/memory_planner.py#L91)、[KV估计](../../vidur-alibabacloud/vidur/entities/request.py#L411) |
| MoE | 层级汇总耗时、随机负载/最忙rank近似 | 缺动态逐Expert任务、共享资源排队与dispatch/combine独立执行 | [MoE估时](../../vidur-alibabacloud/vidur/entities/execution_time.py#L568)、[负载近似](../../aicb/utils/utils.py#L898) |

### 2.3 实施前置条件

| 项目 | 状态与处理 |
|---|---|
| AICB单位与PP | 特定模型分支的秒值再次乘1e-3；PP>1时层范围未赋值，已局部验证。接入前修正或明确拒绝该组合。[代码](../../vidur-alibabacloud/vidur/entities/execution_time.py#L1286) |
| AICB通信计费 | TP分支为0，Attention/MLP读取通信量但未单独计时；需先确认画像是否融合通信。MoE带宽分支固定prefill。[代码](../../vidur-alibabacloud/vidur/execution_time_predictor/base_execution_time_predictor.py#L87) |
| P/D映射 | Cluster与Splitwise分别计算分区，可能不一致；统一由Placement提供。[代码](../../vidur-alibabacloud/vidur/scheduler/global_scheduler/splitwise_global_scheduler.py#L51) |
| 旧运行类 | Node/Link依赖未接通的clock、metrics和schedule_event，不能直接启用。[代码](../../vidur-alibabacloud/vidur/entities/node.py#L42) |
| 通信数据 | 已有AllReduce、AllToAll及TP2/EP4原始成功日志/CSV/flow；历史运行身份与单位仍有缺项。先作解析测试，核验后才进入cost表 |
| 合成负载 | 已有均匀/热点/长尾×EP32/128六组数据；tokens=16384、top-k=8、256 Experts，总assignments=131072。可作守恒测试，尚无源目的矩阵和真实Expert耗时 |
| 验证边界 | PD配置测试通过不能证明KV时序正确；trace重叠数值需修正精度后复核；尚无DAG执行核或真实性能校准通过结论 |

首月使用常量cost独立验证执行核，上述推理模型问题不阻塞开发；在接入对应路径前解决。

## 3. 架构与接口

### 3.1 模块边界

以下为拟议模块；保留现有请求生成、组批策略、预测数据与指标入口。

```mermaid
flowchart TD
    I[JSON模板 / Vidur Batch适配] --> B[GraphBuilder / 校验]
    B --> D[DependencyTracker]
    D --> Q[ReadyQueue]
    Q --> X[Dispatcher]
    X <--> R[ResourceManager]
    X --> C[CostProvider]
    X --> E[Clock / EventQueue]
    E --> F[CompletionHandler]
    F --> R
    F --> D
    F --> M[任务与资源指标]
    F --> V[Stage / Iteration终端回调]
```

| 模块 | 单一职责 |
|---|---|
| GraphBuilder | 将固定模板或Batch快照转换为任务图，检查ID、引用与无环性 |
| DependencyTracker | 维护未完成前驱数，激活依赖满足的任务 |
| ReadyQueue / Dispatcher | 稳定选择就绪任务，尝试原子申请全部资源并启动 |
| ResourceManager | 容量、许可、等待者与释放；后续承接KV持久占用 |
| CostProvider | 返回匹配配置的服务时间或工作量，不修改仿真时间 |
| Clock / EventQueue | 推进唯一仿真时钟，排序事件、处理微步及终止 |
| CompletionHandler | 提交完成、释放资源、解锁后继、执行一次终端回调 |
| Metrics | 记录任务时序、等待原因、资源区间及请求关联 |

首月用独立CLI驱动执行核，后续由Vidur Simulator驱动同一实现，避免两套时钟和执行器。

### 3.2 节点、依赖与粒度

| 类型 | 表达内容 | 首月范围 |
|---|---|---|
| Compute | Attention、router、ExpertGroup等计算段 | 聚合常量或已有分项cost |
| Collective / Communication | TP AllReduce、EP dispatch/combine；后续PP与KV传输 | 一个覆盖通信组的原子节点 |
| Sync | 分支汇合、必要屏障 | 零时长，不占GPU |
| Memory（后续） | 有耗时的copy/pack/layout转换 | 容量reserve/free默认是资源动作 |

依赖边只表达数据完成、执行顺序、跨层/跨设备与同步关系；资源冲突由ResourceManager决定。

```mermaid
flowchart LR
    A[Compute A / GPU0] --> T[TP collective]
    T --> B[下一层Compute / GPU0]
    A --> K[KV transfer / NIC]
    K --> D[Decode / GPU2]
    X[另一Batch Compute / GPU0]
    A -.申请.-> G[(GPU0)]
    X -.申请.-> G
```

默认以Batch iteration或Prefill chunk生成图片段，按层选择性展开计算/通信；设备是placement维度。首月固定Batch一轮，MoE按rank专家组聚合。后续Decode按轮懒生成，必要时展开活跃Expert，完成片段可回收。共享Batch计算只执行一次，不按请求复制。

### 3.3 最小数据字段

| 对象 | 必需字段 |
|---|---|
| Graph | schema_version、graph_id、tasks、resources |
| Task | id、kind、predecessors、rank_ids、resource_demands、cost_ref或duration_ns（二选一） |
| Collective属性 | op、group_id、members、dispatch/combine阶段、payload_bytes及其per-rank/per-peer/全组口径 |
| Resource | id、type、capacity；首月capacity=1 |
| Cost | duration_ns、适用配置、是否包含计算/通信/overhead、核验状态 |
| Runtime | state、remaining_predecessors、ready/start/end、lease_ids、完成事件版本 |

phase、layer、batch/iteration、request slices作为可选元数据；接入推理时补齐。单位统一为整数ns，原始时间只在适配边界转换。零时长合法；负数、NaN/Inf、缺失cost和超容量需求报错。

建议接口：

```text
build(batch_or_template, placement) -> Graph
submit(graph, release_time) -> GraphHandle
estimate(task, context) -> Cost
try_acquire(task, now) -> Leases | WaitReasons
complete(task_id, now) -> ReadyTasks
release(leases, now) -> AffectedWaiters
on_terminal(graph_id, now) -> ControlEvents
```

### 3.4 时间与事件规则

生命周期：`Created → Pending → Ready → Running → Completed`。资源不足时保持Ready并记录等待；失败/取消为独立终态，首月不支持运行中抢占。

```text
earliest_start(v) = max(release_time(v), completion_time(各前驱))
actual_start(v) >= earliest_start(v)
completion_time(v) = actual_start(v) + duration(v)
ready_wait(v) = actual_start(v) - earliest_start(v)
```

固定服务时间模式采用上式；后续共享带宽模式按剩余bytes和速率积分更新完成事件。

事件键为 `(time_ns, microstep, phase, sequence_id)`；同时间先完成/释放，再控制事件与后继激活，最后稳定仲裁Ready任务。零时长完成进入下一微步，直到当前时间无新事件。所有资源all-or-nothing申请；重复/失效完成事件不能重复释放或解锁。

```mermaid
flowchart TD
    A[提交并校验图] --> B[初始化前驱与release事件]
    B --> C[取最早时间 / 禁止回退]
    C --> D[完成任务 / 释放资源]
    D --> E[控制事件 / 激活后继]
    E --> F[稳定仲裁Ready / 原子申请]
    F --> G[启动 / 安排完成事件]
    G --> H{同时间还有事件?}
    H -->|有| D
    H -->|无| J{还有未来事件?}
    J -->|有| C
    J -->|无| K[全部完成则输出 / 否则报告阻塞]
```

### 3.5 资源与cost规则

| 资源/模式 | 实现规则 |
|---|---|
| GPU Compute | 首月每rank一个许可；后续映射物理GPU，group任务原子申请所有成员 |
| Communication | 首月各成员comm资源互斥；可配置collective同时占compute，比较两种假设 |
| NIC/Link（后续） | 显式路径和端点争用；先独占服务，再按研究需要增加fluid共享带宽 |
| Memory/KV（后续） | 容量与持久lease，模型权重、KV、workspace分开；统一动态账本 |

无依赖且资源不冲突才允许重叠。collective占用GPU的方式必须显式配置；不能仅凭图分叉认定真实GPU可完全并行。离线通信cost加资源互斥只模拟粗粒度排队，不模拟在线网络拥塞。

cost接入要求：

- 精确匹配操作、组规模、消息口径、placement、拓扑/带宽与后端配置；缺项报错。
- 优先取单操作通信服务时间，核对是否混入计算、多操作和额外开销；同一费用只计一次。
- 历史身份/单位未齐的CSV只作解析或明确标注的演示，不进入核验通过的cost表。
- 失败日志、0 collective/streams、跨用例错配CSV不作有效cost；不将NaN或导入失败填0。
- AllReduce现有作业含两个streams和计算，需拆清单操作或补跑隔离用例。EP历史配置为TP2/EP4，不能直接用于TP1/EP4模板。

### 3.6 PD与MoE扩展

**PD：** P/D使用独立计算资源；发送前源KV保持pin，目标预留接收容量；接收提交后产生KVReady，之后才能进入Decode可组批队列。源/目标KV的存储与wire bytes按layout计算，P/D不同TP/PP时显式重分片。

```mermaid
flowchart LR
    A[Arrival / P admission] --> P[Prefill compute]
    P --> K[KV ready / source pinned]
    K --> X[KV transfer]
    R[目标容量reserve] --> X
    X --> C[Receive commit / KVReady]
    C --> D[Decode admission / iterations]
    X --> F[释放源pin]
    D --> Z[请求完成 / 释放目标KV]
```

**MoE：** 每轮每层生成一次RoutingResult，包含Expert计数、placement和dispatch/combine矩阵；同轮up/down复用路由。按活跃Expert或真实grouped GEMM组计算独立cost，同卡共享compute，输出join等待必要分支。

```mermaid
flowchart TD
    R[Router / RoutingResult] --> D[Dispatch AllToAll]
    D --> E0[ExpertGroup 0 / GPU0 / n0]
    D --> E1[ExpertGroup 1 / GPU1 / n1]
    E0 --> C[Combine AllToAll]
    E1 --> C
    C --> J[输出Join / 下一层]
```

首月MoE固定EP4、TP1、PP1：router/ExpertGroup/output按rank建节点，dispatch和combine各覆盖全部参与rank，分别声明cost。已有合成负载可作守恒测试；转为EP4需重新聚合placement，不能从目的端负载推导唯一网络矩阵。动态Expert、chunk流水及尾延迟验证在后续实施。

### 3.7 现有模块改造边界

| 模块 | 处理方式 | 关键约束 |
|---|---|---|
| RequestGenerator、全局/副本组批策略 | 复用，输出Batch快照 | 策略决定成员，DAG决定执行；Decode下一轮依赖上一轮完成 |
| Request/Batch与MetricsStore | 适配终端回调、任务关联 | Stage/iteration只更新一次token与指标，子任务不得重复累计 |
| ReplicaStageScheduler与Stage事件 | 先映射一个coarse任务，再展开 | 图terminal完成才触发原StageEnd；PP节点不重复计时 |
| ExecutionTimePredictor/AICB/通信预测器 | 转为cost adapter | 统一单位、适用配置与费用清单；缺分项时不强拆总时长 |
| Cluster/Replica/MemoryPlanner | 提供Placement与初始预算 | P/D分区唯一来源；动态资源账本统一 |
| Node/Task/Flow/Link | 可复用描述，不直接调用旧生命周期 | 执行状态归新runtime |
| Astra-Sim/SimCCL/ns-3 | 先离线cost，在线协同后续评估 | 宿主运行耗时不计入仿真；同一网络服务不重复收费 |

## 4. 实施计划

### 4.1 四周分工与里程碑

建议投入：四人，每人每周10–15小时；D1–D20从实际开工计算。

| 角色 | 责任 |
|---|---|
| A | 图schema、校验、模板与集成 |
| B | 事件执行核、Ready队列、资源申请与释放 |
| C | 通信CSV解析、配置/单位核验、必要的隔离通信补跑 |
| D | 独立手算测试、CLI、时间线、复现与报告 |

| 周次 | 核心工作 | 交付物 | 验收门槛 |
|---|---|---|---|
| W1 / D1–D5 | 冻结最小schema；完成依赖/事件/容量1资源；整理cost正负样例 | 三个手算图、执行核、CLI、CSV时间线 | D3跑通JSON→执行→CSV；周末链/分支/冲突正确，零时长可收敛 |
| W2 / D6–D10 | 完善互斥/并行、确定性、异常；接入核验通过的cost | 资源测试、cost adapter、通信依赖图 | 相同图可切换常量/CSV；至少一条真实通信cost进入执行；失败/错配记录被拒绝 |
| W3 / D11–D15 | 固定EP4 MoE模板、等待原因、参数扫描 | MoE图、3×3计算/通信敏感性结果 | dispatch→ExpertGroup→combine依赖完整，差异可解释；D15功能冻结 |
| W4 / D16–D20 | 修复、回归、测运行开销与独立复现 | 结果文件、复现说明、实验报告 | 第二人新环境复现；全部验收项有结果，未完成项明确列出 |

计划目录：`simai_taskgraph/`、`examples/taskgraph/`、`tests/taskgraph/`。本轮仅修改文档，上述模块尚未实现。

计划命令：

```bash
python -m simai_taskgraph run --graph examples/taskgraph/fork_join.json \
  --policy resource --output results/taskgraph/fork_join
```

### 4.2 调整规则

| 触发条件 | 调整 |
|---|---|
| D3无执行闭环 | 暂停扩展，A/B集中打通常量cost DAG |
| 后端排障超过6人时 | 集中一个环境处理，DAG开发继续；不能恢复历史身份就补跑新用例 |
| D10真实cost未接入 | 削减trace、真实A2A等扩展，保留执行核测试与最小cost接入 |
| D15 MoE不稳定 | 固定手工模板，不做自动模型生成或任意矩阵 |
| D20仍无真实cost闭环 | 分别报告执行核与数据适配状态，不宣布全部首月目标完成 |

### 4.3 后续路线

| 阶段 | 目标与范围 | 前置/验收 | 主要风险 |
|---|---|---|---|
| L1 Vidur接入 | 复用同一执行核，coarse BatchStage桥接 | 单位/支持矩阵明确；Batch成员、token和完成时间回归；错误旧基线另设修正oracle | 重复回调/计费、phase与PP适用范围 |
| L2 细粒度资源 | 选择性层/算子、物理GPU/NIC/link、KV容量 | 原子申请、并行/互斥、PP/TP通信与资源trace正确 | 过度串行、通信占GPU假设、物理映射 |
| L3 PD | KV transfer、源pin、目标reserve、KVReady准入 | 双请求反例与容量背压通过；布局/字节守恒 | 提前Decode、释放过早、背压死锁 |
| L4 动态MoE | RoutingResult、Expert cost、A2A矩阵、共享资源 | 路由守恒、同轮复用、热点排队和join尾部可解释 | 聚合cost误拆、缺源目的矩阵、图规模 |
| L5 校准与扩展性 | 回归、规模基准、匹配硬件参考 | 报告TTFT/ITL/E2E/吞吐误差及事件吞吐/内存 | 参考数据不可比、样本不足 |

L3/L4均依赖L2，可按研究需求安排；联合PD+MoE实验在二者完成后开展。

### 4.4 待冻结参数

首版cost匹配配置与字节口径；collective是否占compute；Vidur首个支持模型/backend/TP/PP组合；KV布局；目标图规模、墙钟与内存预算。DAG建设方向已确定，实施参数按对应阶段冻结。

## 5. 验收与输出

### 5.1 正确性测试

| 测试 | 期望 |
|---|---|
| 图校验 | 环、重复ID、缺前驱/资源、非法cost、超容量需求明确报错 |
| Fork/join | A=3、B=5独立，C=2等两者：总时长7 |
| 串行/并行/争用 | A=10us、B=4us独立，C=8us等两者；A/C占compute，B占comm：serial=22us，resource=18us；B再占compute时=22us |
| 资源 | 同GPU互斥、异GPU可并行；多资源申请失败无残留；完成后恰好释放一次 |
| 时间 | 不倒退；同时间先释放后仲裁；零时长链收敛；重复/失效完成事件无副作用 |
| 确定性 | 同输入/配置的规范任务顺序和时间一致；日志开关不改变结果 |
| Cost导入 | 匹配配置和单位；只计一次服务时间；失败/零collective/错配/未知记录拒绝 |
| MoE | 分支输入覆盖所有成员；同卡Expert串行，异卡按并行关键路径；负载总量守恒 |
| PD（L3） | first_decode_start≥kv_ready；源占用跨传输；目标无容量则等待 |
| 回归（L1起） | Batch/token/终端回调一致；单token、t=0、空workload边界明确支持或拒绝 |

serial/resource对比使用相同图、相同cost与资源配置，仅改变执行策略；资源占用模式另作独立实验。手算测试验证模型逻辑，不代表硬件精度。

### 5.2 输出字段

| 文件 | 最低内容 |
|---|---|
| timeline.csv | task_id、kind、rank/group、ready/start/end_ns、duration_ns、wait_ns、wait_reason、cost_ref |
| trace.json | Chrome Trace任务/资源区间，同一collective投影到多个rank时保留统一task_id |
| summary.json | makespan、依赖路径下界、资源busy/wait/overlap、任务/事件数、仿真墙钟、峰值内存、运行配置 |
| timeline.png | 时间单位、资源lane、执行策略、合成/核验cost标识 |

每rank的重叠时长按compute区间并集与comm区间并集的交集计算；跨rank忙碌时间之和不等于墙钟时延。原图最长依赖路径是资源受限makespan的下界。

### 5.3 性能与校准

首月记录构图/执行墙钟、任务/边/事件数、峰值队列和内存；扫描图规模与计算/通信比例。后续用懒生成与完成片段回收控制历史任务内存。

真实性能校准需要匹配模型、shape、dtype、并行配置、KV布局和硬件/拓扑的参考测量；报告绝对/相对误差、分位数、样本数和测量噪声。没有参考数据时只报告内部正确性和敏感性分析，不承诺统一精度阈值。历史通信模拟结果导入不等于已对真实GPU校准。
