# 推理仿真基准数据

归档旧分支的实验数据、分析产物和原始通信结果，供DAG开发、解析测试、回归和后续精度对照使用。文件通过复制迁入，原始备份和外部压缩包保留，未恢复或合并旧分支。

## 目录

| 目录 | 内容 | 使用范围 |
|---|---|---|
| [baselines/environment](baselines/environment/) | 环境、版本、输入身份与实验记录 | 书面基线记录；部分完整运行日志缺失 |
| [baselines/inputs](baselines/inputs/) | 记录基线提交中的workload、配置、PD测试文件原件 | 复现候选输入，不能反推它们就是压缩包历史运行时使用的原件 |
| [pd/config_test](pd/config_test/) | PD配置测试截图和实验记录 | 配置逻辑，不验证KV传输时序 |
| [pd/analysis](pd/analysis/) | Vidur执行链、PD与指标分析 | 源码分析和接口参考，草案不等于实现 |
| [communication/analytical](communication/analytical/) | analytical主基线、AllToAll/EP日志和结果 | 历史运行与解析测试，cost使用前补身份和单位 |
| [communication/ns3](communication/ns3/) | 有完成证据的microAllReduce、AllToAll、TP2/EP4原始日志、CSV和flow | 历史通信执行记录，不直接视为真实硬件测量 |
| [communication/reports](communication/reports/) | 通信实验说明与索引 | 辅助理解输入和结果 |
| [moe/loads](moe/loads/) | 均匀、热点、长尾的Expert/rank负载JSON与CSV | 合成输入、守恒和placement测试 |
| [moe/analysis](moe/analysis/) | 负载模型、指标与限制说明 | 设计参考，不作已完成性能实验 |
| [moe/scripts](moe/scripts/) | 原负载生成脚本 | 历史脚本参考 |
| [traces/deepseek](traces/deepseek/) | 派生统计、关键事件、分析文档和解析脚本 | 行为参考；原始trace未包含，时间精度需复核 |
| [workloads](workloads/) | workload统计、说明与解析脚本 | 输入字段和通信量分析 |
| [references](references/) | 文献阅读、模板和历史文档 | 归档参考，不作为当前执行计划或指令 |
| [quarantine](quarantine/) | 失败、错配、零collective、不完整运行及空输出 | 错误检测/拒绝测试，不进入有效cost表 |
| [raw/results.zip](raw/results.zip) | 原始压缩包，按字节保留 | 回查原始条目与编码 |

详细文件列表见 [INDEX.md](INDEX.md)，原路径、提交、校验和及使用状态见 [manifest.json](manifest.json)。

## 已核查的结果与限制

- PD截图显示 **10 passed in 0.68s**，文字记录为0.91s。可确认配置测试通过，不能将两者拼成同一次精确运行记录。
- microAllReduce成功日志有 **2/2 streams完成**；作业包含计算和多个通信操作，不能将作业总时间作为一次AllReduce节点时延。
- 普通AllToAll成功例在 `communication/ns3/alltoall_tp8/`；EP成功例在 `communication/ns3/alltoall_ep_tp2_ep4/`。两者日志均有1 collective、1/1 streams完成。
- EP成功例包含偶数rank `{0,2,4,6}` 和奇数rank `{1,3,5,7}` 两组。不能直接将其cost用于不同TP/EP配置。
- 六组MoE数据的Expert总assignments与rank总assignments均为 **131072**，参数为tokens=16384、top-k=8、256 Experts、EP32/128。数据没有逐token选择和源目的通信矩阵。
- 主analytical结果SHA-256与环境记录所记值一致，但相同输出不能补全另一份实验缺失的环境或运行SHA。
- DeepSeek仅归档派生分析及原始数据身份信息，**没有原始prefill.json/decode.json**。原解析脚本截断微秒小数，重叠比例应重算后再作数值依据。
- 历史通信记录尚未完成严格cost核验：运行SHA、拓扑/config/workload原件和单位存在缺项。当前manifest中没有任何文件标为可直接使用的核验cost。

本目录并不自动构成完整的端到端硬件真值集。精度评估前仍需按模型、硬件、输入、并行配置和指标逐条匹配参考数据。

## 隔离区

| 子目录 | 原因 |
|---|---|
| `failed_or_mismatched/` | 原AllToAll的ns3/ns3_t8失败目录含与microAllReduce字节相同的CSV，不是对应AllToAll成功结果 |
| `zero_collective/` | EP TP1配置未实际执行通信：0 collective、0 streams，不能当作零时延成功样本 |
| `incomplete_run/` | microAllReduce的`-01`仅有不完整启动证据，不与`-02`成功记录混用 |
| `empty_outputs/` | 空输出文件，仅保留原件；空的可选明细表不否定同一有效目录的成功日志 |

## 完整性与版本

| 输入 | 固定身份 | 迁入文件数 |
|---|---|---:|
| role3的mydocs成果 | `cfea1491872edb3616054fcbc82831cc6b2226c4` | 5 |
| smwy/week1的实验文档、数据、脚本及阅读材料 | `f2ac89a60102e69c1f81de62071733ce23a33af5` | 23 |
| 原results.zip全部文件条目 | `41e4e54e5a086a11429ad280c9a4ac6223931ce62664633b1d915c85d8fdbf4c`（SHA-256） | 48 |
| 基线输入文件 | `cf9ed25e41887a633c220ba1661a995ccab6d131` | 5 |
| 原始ZIP副本 | 同上archive SHA-256 | 1 |

合计82份迁入文件，另有本目录README、INDEX、manifest、SHA256SUMS与.gitignore。未复制整个旧仓库、编译产物或自动生成的代码图谱。

本次全部迁入文件按原始字节保留，无编码转换；manifest记录原件和副本SHA-256，转换字段均为`none`。原始ZIP也完整保留。未修订历史数据数值、状态或分析结论。

## 使用方式

1. 从INDEX查找场景，再查看manifest的`status`、`purpose`和`note`。
2. 合成负载用于逻辑测试，隔离区用于拒绝测试；原始后端结果先核对费用与单位，再作为cost候选。
3. 需要严格复现时补齐输入和运行身份；无法恢复的历史字段通过新run_id补跑，不倒填旧记录。
4. 脚本保留原实现，未执行、未修改默认路径。迁移后运行前显式指定输入/输出参数或适配路径，避免默认路径写入错误位置。
5. 历史报告的相对链接未逐一改写；按manifest中的`source_path`到INDEX定位新位置。

`data/.gitignore`允许归档的日志和通信CSV被Git识别，避免根目录通用忽略规则漏掉基准文件。本次仅创建文件，未自动提交或推送。
