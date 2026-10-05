# SimInfer 第二周开发计划（团队分发版）

本文件是第二周执行计划。D1–D5 指团队启动后的五个工作日，不默认等同于自然周日期。第一周审核背景见 [团队成果审核](../week1/WEEK1_TEAM_REVIEW_AND_NEXT_PLAN.md)，当前验收状态见 [第一周验收表](../week1/week1_acceptance.md)。周计划与验收入口见 [总索引](../README.md)，本周后续成果审核与验收记录统一放在本目录。

## 1. 本周目标与开工决定

**从 D1 开始接口开发，D1 上午冻结最小契约，D3 完成 mock 回写，D4–D5 争取跑通固定 EP 通信的真实后端闭环。**

本周交付的链路：

```text
固定请求/批次的 MoE dispatch / combine
  → EP 通信请求（rank 映射 + source→destination bytes 矩阵）
  → 通信适配器（mock / SimAI analytical / 小规模 ns-3）
  → 版本化通信结果（状态 + 秒单位时延 + 来源）
  → Vidur MoE 执行依赖
  → 逐请求/逐 token 指标与可追踪日志
```

第一周补证与开发并行。缺历史日志不阻塞 schema、mock、矩阵生成和 Vidur 受控测试；真实后端验收必须具备本次运行的版本、输入、配置、命令、退出码及原始日志。

## 2. 当前基础与约束

- 成员一、二、四的主 analytical 结果一致，总时间 7,545,619；正式 Linux 输入身份见 [基线清单](../week1/week1_baseline_manifest.md)。
- 成员二已有 TP2/EP4 的 AllToAll ns-3 完成证据；TP1/EP8 曾出现 0 collective，仍需单独排查。
- Vidur 已有 TP AllReduce 调用 SimAI 的代码入口，EP dispatch/combine 尚未接入。
- PD KV 目前是静态 size/bandwidth；它与 MoE EP 通信是两个独立依赖，不能把修改 KV 回写当作 EP 闭环。
- 成员四已有 expert/rank 负载向量，需补 source-rank 分配和网络字节矩阵。
- DeepSeek trace 用于事件顺序与可见 kernel 重叠参考；本周不据此宣称请求级绝对精度。

## 3. 范围与优先级

| 优先级 | 工作 | 本周要求 |
|---|---|---|
| P0 | 请求/结果 schema、校验、mock 后端 | 必须完成 |
| P0 | 固定 EP 矩阵生成、字节守恒、rank placement | 必须完成 |
| P0 | Vidur EP 独立预测/回写路径及受控延迟测试 | 必须完成 |
| P0 | 至少一个真实 SimAI 后端结果进入 Vidur | 必须争取完成，未完成时明确判为部分完成 |
| P0 | 错误传播、缓存身份、独立运行目录、现有回归 | 必须完成 |
| P1 | TP1/EP>1 复现及最小修复 | 并行推进；无法修复须显式拒绝且记录限制 |
| P1 | 同配置 analytical/ns-3 对照、16 GPU/2 节点 | P0 闭环后推进 |
| P2 | uniform/hotspot/long-tail 小规模网络对照 | 矩阵确实进入后端后推进 |
| 后续 | 动态 KV 竞争、完整双 micro-batch 重叠、EP32/EP128 扫描 | 不列为本周必须交付 |

第一版使用串行 dispatch→expert compute→combine 依赖，无需先建设完整通用 DAG。已有计算模型保持不变，避免重复计入 AICB 中已经含有的通信时间；若无法可靠拆分该后端，应明确禁用本周 EP 扩展组合。

## 4. D1 上午冻结的接口 v0

以下作为开发起点。成员一、二、三、四在启动后的前 2 小时内核对必要字段，上午结束前发布 v0。后续变更通过小范围兼容补充，避免多人各自改字段名。

### 4.1 调用接口

```python
estimate(request: CommunicationRequest) -> CommunicationResult
```

这是同步的离线预测接口：返回一个通信操作的逻辑时延；进程 wall time 单独统计。真实后端尚未就绪时，调用同一个 mock 接口开发，不另建一套字段。

成员一提供契约和校验；成员二实现后端；成员三调用接口并推进 Vidur 逻辑时间。具体文件位置 D1 冻结，建议 Python 接口置于 Vidur 的 execution_time_predictor 内，矩阵协议与后端输入保持独立。

### 4.2 CommunicationRequest

| 字段 | 含义与约束 |
|---|---|
| `schema_version` | 固定为 `0.1` |
| `op_id` | 本次运行内唯一标识，关联日志和结果；不因请求 ID 不同影响性能缓存 |
| `comm_type` | 第一版为 `ep_dispatch` 或 `ep_combine` |
| `phase` | `prefill` / `decode` |
| `layer_id`, `microbatch_id`, `request_ids` | 操作与执行批次/请求对应关系 |
| `ep_group_ranks` | 有序且不重复的全局 rank 列表 |
| `rank_to_node` | 每个 rank 的节点位置；必须覆盖该通信组 |
| `bytes_matrix` | N×N 非负整数矩阵；行是发送 rank，列是接收 rank；顺序与组列表一致 |
| `dtype` | 有效载荷编码说明；矩阵已经是 bytes，不再按 dtype 重复乘系数 |
| `topology_hash`, `config_hash` | 后端拓扑和网络配置的内容身份 |
| `dependency_ids` | 前置逻辑操作 ID；由上层控制 ready time，第一版可为空 |

字节定义：`bytes_matrix[i][j]` 是该逻辑操作 i→j 的有效载荷，排除协议包头、集合算法重复传输。对角元素是本地 payload，本周基线设为 0。源数据总量、对角本地量、跨 rank 量和跨节点量分别记录；uniform/skew 对照保持跨 rank 有效载荷总量相同。

固定 4-rank 接口样例：每个非对角元素为 1 MiB，全组跨 rank 有效载荷为 12 MiB，每源 rank 为 3 MiB。

```json
{
  "schema_version": "0.1",
  "op_id": "run001-prefill-layer0-mb0-dispatch",
  "comm_type": "ep_dispatch",
  "phase": "prefill",
  "layer_id": 0,
  "microbatch_id": "mb0",
  "request_ids": ["r0"],
  "ep_group_ranks": [0, 1, 2, 3],
  "rank_to_node": {"0": 0, "1": 0, "2": 1, "3": 1},
  "bytes_matrix": [
    [0, 1048576, 1048576, 1048576],
    [1048576, 0, 1048576, 1048576],
    [1048576, 1048576, 0, 1048576],
    [1048576, 1048576, 1048576, 0]
  ],
  "dtype": "bf16",
  "topology_hash": "sha256:<实际拓扑哈希>",
  "config_hash": "sha256:<实际配置哈希>",
  "dependency_ids": []
}
```

该样例只固定接口语义；真实 SimAI 的 GPU/TP/EP 配置须满足后端要求，不能把四个 EP rank 未经映射直接当作四张物理 GPU。

### 4.3 CommunicationResult

| 字段 | 约束 |
|---|---|
| `schema_version`, `op_id` | 与请求对应 |
| `status` | `ok` / `unsupported` / `error` |
| `latency_s` | `ok` 时非负有限数；其余为 null |
| `backend`, `model_version` | `mock` / `simai_analytical` / `simai_ns3`，以及适配模型版本 |
| `input_hash`, `topology_hash`, `config_hash`, `simulator_sha` | 可追溯来源 |
| `payload_bytes`, `network_payload_bytes` | 契约有效载荷及排除对角后的载荷；不假称为实测 wire bytes |
| `cache_key`, `cache_hit` | 缓存身份与是否命中 |
| `run_manifest_path` | 原始日志、结果、命令与退出码的归档索引 |
| `error_code`, `message` | 失败解释，成功时可为空 |

缓存命中时重新绑定当前 `op_id`。缓存键包含矩阵、组和 placement、操作类型、编码、拓扑、网络配置、后端、源码/子模块版本及适配器版本；排除纯追踪 ID。错误不静默转为 0 时延，不自动降级到 mock。

所有接口时间为秒。Astra/CSV/预测器旧单位在适配器中明确转换，不能直接假设 tick、CSV 展示值和 ms 相同。先做已知时延测试确定换算，再联调。

### 4.4 Vidur 回写日志

至少输出：`op_id, request_ids, phase, layer_id, ready_time_s, start_time_s, finish_time_s, latency_s, backend, input_hash, cache_hit`。

串行基线中 `finish = start + latency`；Vidur 由该完成时间推进后续执行依赖。预测子进程运行 2 秒不代表模拟请求增加 2 秒。暂不估计真实 overlap；后续引入并发时再基于关键路径计算暴露时延。

## 5. 四人任务与交付

### 成员一：接口、集成与验收负责人

- D1 发布契约 v0、Python 类型/校验、mock 后端和可运行调用样例；明确模块边界及字段唯一来源。
- 确认 Week 2 集成提交与固定子模块；创建/整理设计、后端、Vidur、矩阵和回归任务。
- D2–D4 审核接口兼容、时间单位、缓存和重复计算风险；集成成员二/三/四最小 PR。
- D5 主持演示验收，更新进度及失败边界。

交付：契约文档与实现、mock、集成测试入口、验收清单、周总结。验收：相同样例能被各成员独立调用；错误输入被拒绝；真实后端与 mock 共用接口。

### 成员二：通信后端与 EP 矩阵消费

- D1 对接契约，核对现有 AllToAll 消息大小是 per-rank/per-peer/全组哪种语义；提交最小 workload、拓扑/config 原件及哈希。
- 实现请求→后端输入→运行→结果解析，保存独立运行目录、原始日志、退出码和单位映射。
- 均匀矩阵可先接现有 scalar AllToAll，但必须证明其展开后的矩阵与契约相符；非均匀矩阵若不支持，返回 `unsupported`，不可丢弃成平均值。
- 优先使固定矩阵真正进入 SimAI/FlowModel；必要时增加矩阵 sidecar/读取路径或版本化适配，单独 PR，不混改集合算法。
- 独立排查 TP1/EP>1；真实配置始终记录 GPU→TP/EP→node 映射。
- P0 完成后做同配置 analytical/ns-3 和 16 GPU/2 节点对照。

交付：至少一个真实后端适配器、矩阵消费证据、单位说明、成功/失败运行包、TP1/EP 状态。验收：实际 flow 的有效载荷按 rank 对应正确；存在 unsupported/error 测试；0 collective 不能算成功。

### 成员三：Vidur EP 调用与请求指标

- D1 用 mock 接口开发 EP 独立调用路径；定位 MoE 层/批次执行时间组合处，避免把 EP 插入 PD KV 回写。
- 第一版显式配置开关，默认关闭；开启后分别加入 dispatch/combine 时延，保留原 TP/PP 预测行为。
- 核对秒/ms 换算、层数/PP stage/迭代数乘法和 batch 内请求归属；避免按层或 token 重复相加。
- 编写受控延迟测试和逐请求/逐 token 输出，D3 前提交 mock 闭环，随后替换为真实后端。
- 同步完成 Linux PD 10 项复核和主基线记录；已有 PD KV 行为保持兼容。

交付：EP 调用/回写代码、mock 与真实后端联调记录、指标定义及回归。验收：受控单请求串行计算中注入已知延迟，完成时间按预期变化；无法预测时明确报错；配置关闭时原行为一致。

### 成员四：流量矩阵与实验输入

- D1 提交均匀 EP4 样例，D2 补 EP8、hotspot、long-tail 和非法输入样例。
- 将 expert/rank 负载向量补为 source→destination assignment/bytes，记录每源 token、Top-K、dtype、hidden size、expert placement、seed。
- 明确每 rank/全组 token 口径；dispatch 与 combine 分开，禁止无依据直接假设互为转置。
- 均匀/偏斜对照固定发送行总量、跨 rank 总字节和 placement；非均匀目的负载可作为合成压力输入，并注明不保证真实 token Top-K 共现。
- 提供行/列和、总量、对角/跨节点字节及输入哈希校验；补原始基线日志和 trace 时间精度核验。

交付：生成器、版本化 JSON 样例、守恒检查、实验对照表。验收：固定 seed 输出一致；总量不随 skew 模式漂移；缺 source 或 placement 的向量不进入网络实验。

## 6. 每日里程碑

| 时间 | 共同里程碑 | 当日必须可展示的结果 |
|---|---|---|
| D1 上午 | 最小契约冻结，开发启动 | schema + EP4 样例 + mock 调用；确认具体代码位置和集成基线 |
| D1 下午 | 各模块独立开发 | 成员二 adapter 骨架；成员三 mock 接线；成员四矩阵校验；补证任务已分配 |
| D2 | 请求、后端、结果链对接 | JSON 校验、单位测试、均匀矩阵消费/unsupported 边界；EP8/skew 输入 |
| D3 | Vidur mock 闭环通过 | known-latency 回写、开关回归、独立日志/缓存；至少真实后端单次调用 |
| D4 | 固定 EP 真实闭环 | 同一 op_id 串起矩阵、后端时延和请求指标，保留完整运行包 |
| D5 | 验收与条件扩展 | P0 检查；闭环已通过才开展非均匀或跨节点对照，并提交周总结 |

开发中每日短同步 15 分钟，只报告已合并/可运行结果、今日接口依赖和阻塞。一个接口阻塞超过半天，组长当天裁决：补最小字段、隔离不支持能力或调整依赖，不等待下次周会。

## 7. 必做测试与验收

| 编号 | 检查 | 通过标准 |
|---|---|---|
| W2-A01 | schema/输入校验 | 错维度、负字节、未知 rank、缺 placement、非法时间均被拒绝 |
| W2-A02 | 矩阵守恒 | 行/列/总量与生成规则一致，后端有效载荷映射一致 |
| W2-A03 | 单位 | 已知秒值经 CSV/适配器转换后仍正确，无 10³/10⁶ 倍差异 |
| W2-A04 | mock 回写 | 固定单请求/批次串行实验中 dispatch/combine 延迟 Δ 按实际调用次数进入关键路径 |
| W2-A05 | 真实闭环 | 至少一个非零 EP 操作经真实 SimAI 后端进入 Vidur，日志关联完整 |
| W2-A06 | 失败 | 超时、非零退出、缺 CSV、0 collective、unsupported 均显式处理 |
| W2-A07 | 缓存/目录 | 改矩阵/配置/placement 必须失效；不同运行互不覆盖；缓存命中保留来源 |
| W2-A08 | 回归 | PD 10 项通过；TP AllReduce 可运行样例通过；EP 关闭时原行为一致 |
| W2-A09 | 结果与成本 | 逐请求输出、命令/SHA/输入/日志齐全；wall time 和模拟时延分别记录 |

**本周完成判定：W2-A01–A09 通过，且包含真实后端 EP→Vidur 回写。仅 mock 通过或只有新接口文件，判为“接口完成、真实闭环未完成”。**

TP1/EP>1 若尚未修复，不能宣称覆盖 DeepSeek TP1；必须显式不支持，列为后续阻塞。非均匀矩阵尚不支持时，只能验收均匀固定矩阵闭环，不能报告 MoE 偏斜已实现。

P95/P99 请求时延、FCT P99、平均 TPOT、逐 token TBT 分开命名。小样本只检查功能和趋势，不把一次结果或三次重复解释成稳定尾时延精度；没有真实参考时报告后端差异，不报告预测精度。

## 8. 分支、PR 与整合

建议每个主题一条开发分支：

| 主责 | 分支建议 | 主要范围 |
|---|---|---|
| 一 | `codex/week2-comm-contract` | 契约、校验、mock、集成验收 |
| 二 | `codex/week2-ep-backend` | 矩阵消费、后端适配、结果解析 |
| 三 | `codex/week2-vidur-ep` | EP 调用、执行依赖、指标回写 |
| 四 | `codex/week2-traffic-matrix` | 数据生成与守恒校验 |

D1 由成员一确认集成分支和起始提交。子模块仍固定为第一周三个 SHA；如成员二需要修改 SimCCL/ns-3，先提交子模块对应分支/PR，再由成员一审核 gitlink 更新和兼容回归。

PR 只提交实现、测试、小型 fixture 和说明；大型 trace、CSV、二进制、虚拟环境及日志以归档索引和哈希引用。不要直接整体合并旧 `.ua` 图谱或 `.gitignore` 改动。D1 契约先合并，各成员基于它工作，后续每日小 PR 集成。

## 9. 风险裁决与降级顺序

- **ns-3 构建阻塞：**继续 mock/Vidur 开发，优先打通可运行 analytical 的均匀固定矩阵；不阻塞上层接口。
- **后端不识别矩阵：**先补矩阵消费入口和守恒证据；保持 unsupported 返回，不偷偷压缩为标量。
- **真实模型画像缺失：**用固定计算时间做接口受控实验并标明来源，不申请 GPU 作为接口开发前置条件。
- **D4 仍无真实闭环：**D5 聚焦闭环，推迟拥塞、PD 动态 KV 和大规模参数扫描；如仍失败，交付具体断点和可复现失败。
- **发现旧单位/错误处理问题：**单独最小修复 PR，由成员一与模块负责人评审，不混入重构。

## 10. 启动时每人的第一件事

1. 成员一：提交接口 v0、mock 和最小调用样例，确认上午评审时间。
2. 成员二：给出“现有 AllToAll 字节参数→四 rank 矩阵”的映射证据，开始 adapter。
3. 成员三：确定 MoE 插入点，调用 mock 做一条固定请求回写。
4. 成员四：给出 EP4 uniform JSON 和守恒校验，随后扩展 EP8 与 skew。

启动后立即按这四项开工，第一周补证作为并行任务推进。
