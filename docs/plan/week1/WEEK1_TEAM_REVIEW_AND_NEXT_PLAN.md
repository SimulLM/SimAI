# 第一周团队成果审核与下一阶段规划（成员一）

审核日期：2026-10-03。审核范围：成果查找、证据检查、现有代码核对及下一阶段设计；本次没有重新执行他人的实验。

最新接收与验收状态统一维护于 [验收表](week1_acceptance.md)，Linux 输入与命令维护于 [基线清单](week1_baseline_manifest.md)。旧成员一周计划已由本报告取代并删除；文档重构后本周组长材料统一归档在 `docs/plan/week1/`。原 Day 2 文档已不在当前文档树中，结果汇总和本地原始证据仍保留，详见验收表及 [周计划总索引](../README.md)。

## 1. 总体判定

第一周已形成稳定的 analytical 基线、底层 AllToAll/EP 的 ns-3 执行证据、Vidur 调度边界分析和 DeepSeek trace 行为参考，具备启动接口开发的基础。D1 上午先完成最小开工对齐，再于当天开始实现；第一周补证并行推进，不要求先通过全组第一周验收才开工。全组“统一 Linux 环境口径、同一版本、同一输入、完整原始记录”的统一验收仍有缺口，不能整体标记通过。

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

## 7. 接口设计依据

  请求、结果及 Vidur 回写日志以 [Week 2 计划第 4 节](../week2/WEEK2_PLAN.md#4-d1-上午冻结的接口-v0) 为唯一开发口径。

保留设计原则：矩阵单位为 bytes，接口时间为秒；EP dispatch/combine 与 PD KV 分开；有效载荷与 wire bytes 分开；失败显式返回，不静默转为零时延或 mock。第一版采用串行依赖，不能用固定 85.207% 重叠比例扣减通信。

## 8. 第二周开工与补证安排

唯一每日安排见 [Week 2 计划第 6 节](../week2/WEEK2_PLAN.md#6-每日里程碑)。D1–D5 从团队确认的启动日算起，不改写历史实验日期。

- 主线：D1 上午对齐并冻结最小契约，当天实现接口、mock、矩阵和 Vidur 接线；D2 对接，D3 mock 闭环，D4–D5 真实后端联调与验收。
- 并行线：D1 分配第一周补证责任，D2 前登记可恢复材料与需补跑事项；D5 汇总已补齐、待补或无法恢复的状态，不要求全员停下开发补历史日志。
- 验收门槛：缺历史资料不阻塞 mock 开发；涉及字节映射、时间单位和真实后端支持范围的缺口，必须在相应联调前验证。第二周真实运行须完整留证，否则不能验收该运行。

成员二补身份、workload/拓扑/config 原件与日志；成员三补 Linux PD/主基线原始记录；成员四补基线日志及 trace 精度核验。细分安排统一见 Week 2 第 1.2 节。无法恢复者以新编号补跑，不倒填历史字段；trace 精度未核验前不使用相关数值作精度结论，不阻塞固定矩阵闭环。

## 9. 第二周验收口径

唯一完成标准见 [Week 2 计划第 7 节](../week2/WEEK2_PLAN.md#7-必做测试与验收)，以 W2-A01–A09 为准。必须含至少一个真实后端 EP→Vidur 回写；只有 mock 判为部分完成。

同配置 analytical/ns-3 对照、16 GPU/2 节点、非均匀网络实验均在 P0 闭环后条件推进，不是第二周基础闭环的额外前置条件。TP1/EP 或非均匀矩阵若不支持，须显式说明，不能用其他配置的成功冒称覆盖。复杂并发/重叠和大规模实验留待后续阶段。

## 10. 成果整合顺序

- 优先评审成员四分析脚本、JSON/事件表和文献材料；模块代码没有在这两条分支中更改，整合时保留生成物来源和脚本版本。
- 成员三选取任务/实验文档，修正接口落点与单位；`.ua` 图谱及 `.gitignore` 变更另行评审，避免与验收文档一起盲目合并。
- 成员二补齐完整实验包，原始日志/CSV 留在归档存储，通过哈希清单引用；不要将大体积结果直接纳入主仓库。
- 成员一实际结果已汇总于验收表，原始归档仍保留。审核状态为三位成员成果均已取得，验收表统一维护当前待办。

负责人决策：第一周成果“具备启动接口开发的基础，团队统一验收待补证”；第二周先对齐、当天开工、补证并行，优先贯通固定 EP 纵向路径。动态 KV 竞争、完整双 micro-batch 重叠和 EP32/EP128 大规模实验放到小规模闭环及跨节点可观测性完成之后。
