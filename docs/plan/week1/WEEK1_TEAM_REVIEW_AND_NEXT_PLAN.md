# 第一周团队成果审核与下一阶段规划（成员一）

审核日期：2026-10-03，Asia/Shanghai。审核范围：成果查找、证据检查、现有代码核对及下一阶段设计；本次没有重新执行他人的实验。

最新接收与验收状态统一维护于 [验收表](week1_acceptance.md)，Linux 输入与命令维护于 [基线清单](week1_baseline_manifest.md)。旧成员一周计划已由本报告取代并删除；文档重构后本周组长材料统一归档在 `docs/plan/week1/`。原 Day 2 文档已不在当前文档树中，结果汇总和本地原始证据仍保留，详见验收表及 [周计划总索引](../README.md)。

## 1. 总体判定

第一周已形成稳定的 analytical 基线、底层 AllToAll/EP 的 ns-3 执行证据、Vidur 调度边界分析和 DeepSeek trace 行为参考，可以开始接口设计。全组“同一 Linux 环境、同一版本、同一输入、完整原始记录”的统一验收仍有缺口，不能整体标记通过。

下一阶段主目标：固定 EP source→destination 字节矩阵进入通信后端，返回完成时延，并在 Vidur 的 MoE 执行依赖中回写。先验证确定性闭环，再扩展偏斜和跨节点竞争。

## 2. 成果位置与审核快照

本次已 fetch 两个指定远程分支，通过 `git show` 读取，无切换、合并或覆盖当前工作区。

| 成员 | 来源 | 审核版本/身份 | 主要交付位置 |
|---|---|---|---|
| 二 | `C:/Users/wwjjy/Desktop/results.zip` | SHA-256 `41e4e54e5a086a11429ad280c9a4ac6223931ce62664633b1d915c85d8fdbf4c` | ZIP 内 `results/`：报告、规范化记录、原始日志、CSV |
| 三 | `origin/role3` | `cfea1491872edb3616054fcbc82831cc6b2226c4` | `mydocs/成员3_Vidur与PD调度_任务记录.md`、`mydocs/W1-M3-20260902-01_实验记录.md`、测试截图 |
| 四 | `origin/smwy/week1` | `f2ac89a60102e69c1f81de62071733ce23a33af5` | `docs/WEEK1_MEMBER4_*.md`、`docs/experiment_record.md`、`docs/data/`、`docs/paper_reading/`、三个分析脚本 |
| 一 | 当前工作区 | Day 2 结果已汇总，原始归档保留 | [验收表](week1_acceptance.md)、本地 `results/week1/member1/W1-M1-20260902-01/` |

远程成果浏览入口：

- [成员三任务记录](https://github.com/SimulLM/SimAI/blob/cfea1491872edb3616054fcbc82831cc6b2226c4/mydocs/成员3_Vidur与PD调度_任务记录.md)
- [成员四完成度复审](https://github.com/SimulLM/SimAI/blob/f2ac89a60102e69c1f81de62071733ce23a33af5/docs/WEEK1_MEMBER4_COMPLETION_REVIEW.md)
- [成员四 trace 分析](https://github.com/SimulLM/SimAI/blob/f2ac89a60102e69c1f81de62071733ce23a33af5/docs/WEEK1_MEMBER4_DEEPSEEK_TRACE_ANALYSIS.md)

## 3. 成员二审核

### 已证实

- 主 analytical CSV 已随附件交付。审核直接读取 ZIP 内原始字节，SHA-256 为 `b3d73975f0081c119094852f15b7926b288afb33b337aa19fd46ed6a20acdd69`，与成员一归档及成员四报告完全一致。总时间 7,545,619；计算 4,542,795；暴露通信 2,656,839；bubble 345,984。
- microAllReduce ns-3 成功记录 `-02` 的原始日志包含两次 collective、2/2 streams 完成、100% 完成率，CSV 提供通信与总时间。
- 普通 AllToAll 的 `ns3_rail8/run.log` 和 EP 的 `ns3_rail8_tp2_ep4/run.log` 均有 collective 实际发行和 1/1 streams 完成。各自总时间为 52 和 45（CSV 展示值）。
- TP1/EP8 失败日志明确显示 `all dims disabled` 和 0 collective，不能把产生 CSV 当作有效通信完成。
- 拥塞方案已明确要求 source→destination 矩阵、队列/FCT/ECN 等证据，方向合理；方案尚未执行。

### 必须补证或修改结论

1. 规范化记录中的 OS、编译器、Git SHA、子模块 SHA、输入哈希和原始退出码大多为 N/A。主结果一致只能证明输出一致，不能反推出当时完整软件与环境身份。
2. ZIP 没有包含报告引用的 `example/workload_alltoall_minimal.txt`、`example/workload_alltoall_ep_minimal.txt` 原件，也没有实际拓扑和配置快照。索引引用的“成员二_第一周任务验收与汇报总结.md”亦不在附件中。必须补原件、哈希和生成命令。
3. 普通 AllToAll analytical 使用 `-g_p_s 1 -nv 8 -nic 100`，ns-3 使用 8 GPU/节点的 H20 拓扑；EP analytical 的带宽参数也与 ns-3 不同。25→52、3030→45 的差异混入节点布局和带宽差异，不能归因为后端模型误差，更不能当作精度。
4. 8 GPU 单节点 ns-3 成功不能证明跨节点 RDMA 拥塞能力；下一阶段需至少 16 GPU/2 节点的代表性对照。
5. 128 GPU 拓扑与 8 GPU workload 的失败和参数调整是排查线索，现有证据不足以将“规模不匹配”定为唯一根因，需匹配/不匹配控制实验。
6. `-01` 是未完成启动记录，并非成功实验的重复编号；根目录 CSV 易被覆盖，正式引用只使用有实验身份的独立输出目录。

审核结论：基础通信支持有运行证据；严格可复现验收为“补证后通过”；analytical/ns-3 精度对比暂不验收。

## 4. 成员三审核

### 可采用的成果

- 请求→heapq 事件→调度→执行时间预测→指标链梳理细致，纠正了把遗留 `EventQueue` 当作实际主循环的误解。
- 区分 TP 后端调用、PP 查表、EP 缺口和 PD KV 静态估算，适合作为接口设计的代码地图。
- `batch_end_event.py` 中 KV size/带宽静态估算及 `decode_arrived_at` 回写位置与当前代码一致。
- Windows 上 10 项 PD 配置测试通过，有截图和环境记录；成员一 Linux 复核也为 10/10，但不能代替成员三本人完成统一 Linux 验收。

### 设计修正

1. 成员三未提交 Linux 正式测试及完整原始日志，也缺主通信基线；按全员统一验收要求仍需补齐。
2. TP→SimAI 是已有代码入口，现有 PD 配置单元测试没有触发它，应称“已存在接入路径，端到端运行待验证”，不宜直接认定各后端已验证闭环。
3. EP dispatch/combine 应接入 MoE 层/批次执行依赖，不能通过替换 PD KV 的 `size/bandwidth` 来实现。PD KV 是另一种点对点操作，发生在 Prefill→Decode 切换。
4. 提议的 `latency_ms` 不能原样赋给 `pd_p2p_comm_time`：当前 size/bytes-per-second 得到秒，而通信预测路径有 ms 语义；适配器必须明确转换和校验。
5. `pd_p2p_comm_bandwidth * 1024^3/8` 与通常十进制 Gbps 定义也有偏差，必须记录旧行为并统一契约中的 byte/s 或 bit/s。
6. detailed flow CSV 是诊断输出，不应描述为 ns-3 必然读 CSV 执行。当前 `NcclFlowModel` 消费内存 FlowModels，并调用前端发送接口。
7. Prefill E2E、平均 decode normalized time 与 TTFT/TPOT 的对应需结合首 token 产生位置、decode token 分母和 KV/排队是否计入确认；逐 token 间隔 TBT 必须独立记录。

审核结论：架构梳理可采用；指标语义和 schema 落点需修订；Linux 统一验收待补。

## 5. 成员四审核

### 可采用的成果

- 工作负载分析脚本、结构化 JSON、字段说明齐全。18 GiB 普通 AllToAll 和 72 GiB EP 是声明消息量之和，报告已经正确区分其与真实网络字节量。
- DeepSeek 固定源提交 `449602428a1b023acb8a505d4f34fef536535db6`，有 trace 哈希、设备、EP32/EP128、事件表与质量检查。
- Prefill 85.207% 和 Decode 0.006% 是可见 EP kernel 与已分类计算 kernel 的区间重叠比例。Decode 不含完整 RDMA 区间，不能解释为“Decode 没有通信重叠”。
- 三种偏斜生成器保持 assignment 守恒，明确输出是目的 expert/rank 向量，尚非 source→destination 网络矩阵。
- 四篇文献卡及校准模板已经形成，可直接作为设计参考。

### 补证与限制

- Linux 主运行和 pytest 有实填记录、SHA、结果哈希和成本，但明确没有保存完整 stdout/stderr。按团队规则标“结果记录充分，原始日志待补”，不接受自评 7/7 代替负责人验收。
- 本次读过分析脚本及结构化结果说明，没有下载大型原 trace 重跑，因此 85.207% 等作为成员四提交的分析值引用，不标作本次独立复算。
- Decode 相邻配对只有形状观察，缺 correlation 时不能构造网络完成依赖。
- trace 脚本把浮点时间转 int；在解释 1 μs 交集或极小重叠比例前，应保留原精度并给出舍入敏感性检查。
- 偏斜向量不保证每 token Top-K expert 互异，也不含 source-rank 分布。可以作为合成压力输入，不可宣称真实路由回放。
- 16,384 tokens 的“每源 rank”还是“全 EP 组总量”必须先明确；当前生成器将其当作场景总量，与每卡 16K 的 profile 口径不能直接混用。

审核结论：工作负载/trace/偏斜方案/文献交付可用于设计；基线原始日志与严格 trace 数值复核待补。

## 6. 负责人纠偏：统一输入身份

Day 1 清单使用 Windows CRLF 的 SHA-256，而成员四使用原生 Linux LF 检出。审核在当前工作区内存中规范化换行后重新计算，四项均与成员四值一致，因此该差异来自行尾，并非业务输入变化。此前“任何原始哈希差异都不可比较”的表述需增加平台与换行前提。

正式 Linux 基线统一采用：

| 输入 | LF SHA-256 |
|---|---|
| `workload_analytical.txt` | `8c2e255aa7397d8c5c7e01daa04d4b3c97a6b015a27bd425770ef8e7e5cbe0a1` |
| `busbw.yaml` | `ae063b004c098c15f3e5e3cf78c037f13187a06f5394499a876b8c86094a1a87` |
| `microAllReduce.txt` | `5aea5b1afc033d4423897323348c0ed8eac6596ef7b5ce66a6017c259c0caae2` |
| `test_pd_separation.py` | `c1d627de37e60c309c7d9101f4de082083b1ac5df0615ec029bfb1d9b9e203a5` |

保留历史 CRLF 哈希；新实验用 Linux 原生干净检出，记录 Git commit、blob、原始文件 SHA-256 和换行方式。不能用后来采集的环境字段冒充历史执行身份，无法恢复者需补跑。

## 7. 接口决策草案

成员一组织评审并冻结以下三种版本化契约：

- 通信请求：`schema_version, op_id, phase, layer_id, microbatch_id, request_ids, comm_type, ep_group_ranks, rank_to_node, bytes_matrix, dtype, topology_hash, issue_time_s, dependency_ids`。
- 通信结果：`op_id, backend, status, latency_s, start_time_s, finish_time_s, simulated_bytes, input_hash, config_hash, simulator_sha, cache_key`；有证据才填写 queue/FCT 分解。
- 请求回写：`op_id, affected_request_ids, dependency_node_id, ready_time_s, exposed_delay_s, source`。

约束：矩阵元素为非负整数 bytes；rank 映射显式；总量和各行/列守恒；本地对角 payload 与网络传输量分别记录；dispatch 与 combine 分开；统一接口时间为秒，CSV 单位在适配器集中转换。失败不能返回负时延进入调度，必须显式状态和降级来源。

缓存键包含矩阵、并行组、placement、dtype、拓扑、带宽/环境配置、后端和版本。不同操作使用独立结果目录，禁止复用根目录最近一次 CSV。

第一版默认串行依赖以便验证；DeepSeek 重叠用于后续独立 DAG 建模，不能直接把总时延乘以固定 85.207% 来扣除通信。

## 8. 下一阶段五个工作日安排

以下保留首次审核时的建议安排。正式执行以 [Week 2 团队分发计划](../week2/WEEK2_PLAN.md) 为准：接口冻结提前至 D1 上午，补证与开发并行。

时间从团队启动下一阶段起算，不将九月历史实验日期改写为当前日期。

| 工作日 | 成员一 | 成员二 | 成员三 | 成员四 | 阶段退出条件 |
|---|---|---|---|---|---|
| D1 | 汇总审核、修订 Linux 哈希清单、确认源码/子模块基线、建立具体补证任务 | 补环境/SHA、最小 workload/拓扑/config 原件及构建日志 | Linux 补跑 PD 与主基线，保存完整日志 | 补原始基线日志；提交固定 trace 获取清单 | 全组身份和证据可追溯；缺项有明确负责人 |
| D2 | 主持三种 schema 与指标定义评审，冻结 v0 | 明确 EP group/rank/字节语义；复核 TP1/EP>1 路径 | 确定 MoE 插入点、单位和 batch/token 计数 | 向量扩展为确定的 source→destination 矩阵 | 固定矩阵、映射、单位、接口和失败语义一致 |
| D3 | 评审最小实现与确定性测试 | 通信后端消费固定矩阵，核查实际 flow 字节守恒 | EP 结果接入执行依赖；先用可控 mock latency 验证回写 | EP4/EP8 均匀矩阵及质量检查 | 矩阵真正进入后端；mock 延迟改变正确阶段 |
| D4 | 主持端到端演示，检查缓存隔离和回归 | 同硬件参数 analytical/ns-3 对照，16 GPU/2 节点小场景 | 真实通信结果回写、TP/PD 配置回归、逐请求输出 | 汇总 makespan、指标变化和成本 | 固定 EP 矩阵→后端→Vidur 指标闭环可复现 |
| D5 | 验收、失败清单和下一里程碑决策 | 视 D4 状态开展网络拥塞观测 | 核验 TTFT/TPOT/TBT/P95/P99 统计口径 | 一组 uniform/hotspot/long-tail 对照，记录 placement | 输出能力、成本、边界和证据；不强求偏斜性能结论 |

若 D2 发现后端不能表达非均匀矩阵，先实现矩阵/FlowModel 契约及其守恒测试；不得用只变 collective 总字节数代替偏斜。如果 D4 未闭环，D5 继续修复闭环，暂停大规模参数扫描。

TP1/EP>1 是 DeepSeek TP1 场景的重要接口要求。TP2/EP4 可作为现有路径冒烟，但不能用调整 TP 规避该缺口并宣称覆盖 EP32/EP128。记录问题、先做最小复现，再走单独修复评审。

## 9. 下一阶段验收标准

1. 固定矩阵包含可验证的 source/destination/rank placement，后端生成字节与预期映射一致；非均匀矩阵不能被丢弃成均值。
2. 至少有一条真实通信结果经适配器进入 Vidur MoE 执行依赖；日志可用 op_id 追踪到请求。
3. 单请求、固定 batch、串行计算的受控测试中，注入 dispatch/combine 延迟 Δ，对应阶段关键路径按预期增加；PD KV 延迟只影响其应影响的 Decode 依赖。
4. 并发/重叠场景按 DAG 关键路径验证，不能假设所有请求指标都增加同一 Δ。
5. 改变矩阵、拓扑或带宽使缓存失效；同输入结果确定；操作之间输出隔离。
6. Analytical/ns-3 使用同一矩阵、组、placement 和可比配置，报告模型间差异及运行成本；无真实参考时不称精度误差。
7. PD 指定 10 项测试仍通过；TP1/EP>1 不得静默发行 0 collective。
8. 首阶段小样本只检验确定性与趋势，不根据几次仿真给出稳定 P99 或置信区间。FCT P99、请求 P99、平均 TPOT、逐 token TBT 分别命名。

## 10. 成果整合顺序

- 优先评审成员四分析脚本、JSON/事件表和文献材料；模块代码没有在这两条分支中更改，整合时保留生成物来源和脚本版本。
- 成员三选取任务/实验文档，修正接口落点与单位；`.ua` 图谱及 `.gitignore` 变更另行评审，避免与验收文档一起盲目合并。
- 成员二补齐完整实验包，原始日志/CSV 留在归档存储，通过哈希清单引用；不要将大体积结果直接纳入主仓库。
- 成员一 Day 2 实际结果已汇总于验收表，原始归档仍保留；重构后不再引用已移除的 Day 2 文档。审核状态为三位成员成果均已取得，验收表统一维护当前待办。本次没有创建远程 Issue、PR 或向团队发消息。

负责人决策：第一周成果“具备进入设计阶段的条件，团队统一验收待补证”；优先贯通固定 EP 纵向路径。动态 KV 竞争、完整双 micro-batch 重叠和 EP32/EP128 大规模实验放到小规模闭环及跨节点可观测性完成之后。
