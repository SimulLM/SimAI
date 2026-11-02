# 阶段2：最小DAG执行核心

交付状态：执行核心、独立事件运行器、资源协议调用、受限追加、命令和逐任务输出均已完成。功能验收使用常量耗时；资源容量、原推理链和预测精度改善由后续阶段验收。

## 分部分说明

| 工作包 | 说明 | 主要代码 |
|---|---|---|
| A 输入与校验 | [01-validation-and-input.md](01-validation-and-input.md) | schemas/dag/v1/validation.py、io.py；dag/serialization.py |
| B 依赖执行 | [02-execution-core.md](02-execution-core.md) | dag/runtime.py、executor.py |
| C 事件与时钟 | [03-events-and-clock.md](03-events-and-clock.md) | dag/runner.py |
| D 资源与失败 | [04-resources-and-failure.md](04-resources-and-failure.md) | dag/executor.py、testing.py |
| E 原子追加 | [05-atomic-append.md](05-atomic-append.md) | DagExecutor.append、DagRunner.append |
| F 命令与验收 | [06-cli-and-acceptance.md](06-cli-and-acceptance.md) | scripts/dag_phase2/main.py、dag/trace.py |

表中dag目录为 `vidur-alibabacloud/vidur/dag`。v1 schema和contracts保持原声明，旧Node不参与执行。

## 环境与运行

使用Python 3.10+；本轮在Python 3.15.2验证。已有环境位于 `.cache/dag-phase1-py315`。创建新环境时可将临时目录放在项目内，以适应Windows目录权限：

```powershell
New-Item -ItemType Directory -Force .cache/python-tmp | Out-Null
$env:TEMP = (Resolve-Path .cache/python-tmp).Path
$env:TMP = $env:TEMP
& D:/Python/python.exe -m venv .cache/dag-phase2-env
& ./.cache/dag-phase2-env/Scripts/python.exe -m pip install -r scripts/dag_phase2/requirements.txt
```

以下使用已有环境。每次替换新的run_id，命令拒绝覆盖已存在目录：

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe scripts/dag_phase2/main.py run --graph tests/fixtures/dag/v1/fork_join.graph.json --resource-mode dependency-only --output results/dag/phase2/<run_id>
& ./.cache/dag-phase1-py315/Scripts/python.exe scripts/dag_phase2/main.py acceptance --output results/dag/phase2/<acceptance_id>
```

run输出timeline、events、summary和manifest；acceptance另外保存三份图结果、pytest日志、JUnit和acceptance-report。

## 执行语义

```mermaid
flowchart LR
    Input[图与冻结cost] --> Validate[完整校验与快照]
    Validate --> Pending[前驱计数]
    Pending --> Ready[READY队列]
    Ready --> Acquire[资源申请]
    Acquire --> Running[RUNNING与完成事件]
    Running --> Host[宿主事件堆]
    Host --> Release[释放与完成标记]
    Release --> Pending
    Release --> Terminal[terminal一次回调]
```

运行身份为(graph_id, task_id)。任务按提交序号调度；事件按(time_s, insertion_sequence)推进。全部前驱完成才READY；资源不足保持READY，其他工作可以前进。时间单位为秒。零时长任务也经完成事件，长链通过迭代收敛。

submit/append只返回事件意图，不自行推进事件循环。图cost提交后冻结，metadata隔离。非法输入不登记图；非法追加不改变原图。协议重复动作报错；运行失败清理一次并产生graph_failed，遗留完成事件不再解锁或释放。

## 阶段3接入

构造 `DagExecutor(resource_manager, resource_units={"gpu:0": "permits", "nic:0": "permits"})`。resource_units是ID到单位的映射；容量由管理器持有。try_acquire接收完整demands并返回Lease或None；release返回Wakeups。执行器全量扫描READY并保持提交顺序，唤醒列表不产生额外调度优先级。placement只描述位置，不增加隐式需求。

同一管理器服务同一执行器的多张图。外部容量释放通过宿主安排dispatch事件。资源管理器必须保证申请失败不残留占用。阶段3需实际实现并验证计算/通信容量、原子申请和KV协议，完成22/18/22μs资源场景。

DependencyOnlyResources是测试替身，不执行容量核算。该模式的18μs结果不证明原图共享GPU场景合法并行。

## 阶段4接入

原 `ReplicaStageScheduleEvent` 构造coarse任务并使用原total_time一次。将handle.initial_events和后续返回意图包装为原Simulator事件；任务完成事件调用on_task_complete，dispatch事件调用dispatch。保持原事件队列为唯一队列，原时钟按宿主事件推进。

terminal回调通过闭包绑定原batch/stage并生成原BatchStageEndEvent。回调可将事件暂存到适配层并返回空tuple；不能重入执行器或Simulator。原先直接安排StageEnd的路径必须由DAG路径替换，避免重复完成。阶段2没有修改原请求调度或Token逻辑。

## 验收与限制

最终联合回归110项通过，其中原阶段1测试31项、阶段2测试79项。手算图逐节点时序正确；同时间确定性、一次完成、零时长、失败清理、动态追加和CLI证据均有覆盖。结果见 [06-cli-and-acceptance.md](06-cli-and-acceptance.md)。

当前按仓库源码布局运行，未交付独立wheel。输入路径由CLI限制在仓库内。全量READY扫描、追加时整图校验、图完成后保留状态适用于正确性验证；规模与回收策略留待后续性能阶段。正耗时若在当前float时间精度下无法前进，运行明确失败；不静默转换为零耗时。

本轮继续复验阶段1：18项静态检查通过，0个有效精度样本、7个阻塞配对。阶段2功能通过不解除这些数据阻塞，也不产生预测精度改善结论。未运行完整推理、真实GPU、ns-3或analytical二进制。

## 交接内容

交接代码、上述运行命令、正式acceptance结果目录和当前限制。结果未纳入Git，需单独归档或用新的run_id复验。公共协议变更继续遵循阶段1版本规则；本轮没有更改schema/contracts字段或签名。
