# 成员四：第一周任务完成度复审

## 复审结论

复审日期：2026-09-07。验收依据为 `大创_第一周plan.md` 中的统一基线要求和成员四交付清单。

复审前发现两项缺口：统一解析主基线与 Vidur PD 测试未实际归档；实验记录和校准表仅散落在
方案描述中，没有形成可直接复制的模板。本次已补跑基线并新增 Markdown/CSV 模板。

补齐后，成员四的第一周专属交付 **7/7 已具备**，统一基线中与成员四相关的环境、版本、输入、
解析主运行和 PD 测试均有可追溯记录。尚未实现的请求-通信-网络闭环属于计划明确的第二周及后续
研发内容，不计为第一周缺失。

## 逐项验收

| # | 验收项 | 状态 | 证据 | 复审说明 |
|---:|---|---|---|---|
| 1 | 环境、主仓库、三个子模块、输入哈希 | 完成 | `WEEK1_MEMBER4_ENVIRONMENT_RECORD.md` | Ubuntu 24.04 WSL/ext4；SHA 与哈希齐全 |
| 2 | 解析后端构建与主通信基线 | 完成 | 环境记录第 7 节 | 构建成功；运行退出 0；结果行数、哈希和成本已记录 |
| 3 | Vidur PD 基线 | 完成 | 环境记录第 7.3 节 | `10 passed`；隔离环境与依赖可复现 |
| 4 | 主工作负载字段与 AllToAll 统计 | 完成 | `WEEK1_MEMBER4_WORKLOAD_ANALYSIS.md`、JSON | 1,789 行与 12 字段通过；AllToAll 18 GiB、EP 72 GiB |
| 5 | DeepSeek Prefill/Decode 关键事件表与 trace 卡 | 完成 | `WEEK1_MEMBER4_DEEPSEEK_TRACE_ANALYSIS.md`、CSV/JSON | EP32/EP128、事件、重叠、来源和校准边界齐全 |
| 6 | MoE 均匀/热点/长尾方案与假设 | 完成 | `WEEK1_MEMBER4_MOE_SKEW_PLAN.md`、CSV/JSON | 固定总量、seed、偏斜指标、实验矩阵和假设齐全 |
| 7 | 四篇核心文献阅读卡 | 完成 | `paper_reading/` 四文件及 summary | 独立卡片；按 Vidur→DistServe→vLLM→Clockwork 串联 |
| 8 | 实验记录模板 | 完成 | `experiment_record_template.csv` 与说明文档 | 版本、输入、命令、输出、随机种子和运行成本齐全 |
| 9 | 初版校准数据表设计 | 完成 | `calibration_table_template.csv` 与说明文档 | 真实/仿真、绝对/相对、P95/P99 和成本齐全 |
| 10 | 三个成员四分析脚本可重复运行 | 完成 | `scripts/` 与 `docs/data/` | 本次重跑后 Git 无差异，说明生成结果确定 |

## 本次实际复核

### 统一 Linux 基线

- 固定代码：`cf9ed25e41887a633c220ba1661a995ccab6d131`。
- `./scripts/build.sh -c analytical`：成功，退出码 0。
- 计划中的 `SimAI_analytical` 主命令：成功，退出码 0，wall-clock 1.24 s，峰值 RSS 7,620 KiB。
- `results/example-EndToEnd.csv`：1,792 行，SHA-256 为
  `b3d73975f0081c119094852f15b7926b288afb33b337aa19fd46ed6a20acdd69`。
- `pytest tests/test_pd_separation.py -q`：10 passed in 0.13 s。

### 成员四脚本

以下脚本均退出 0，重新生成后 Git 无内容差异：

```text
scripts/analyze_workload.py
scripts/analyze_deepseek_trace.py
scripts/generate_moe_skew_scenarios.py
```

这证明已提交的 JSON/CSV 与当前脚本和固定输入一致。

## 仍需保留的边界

- `workload_analytical.txt` 是训练型可控基线，不是 LLM serving 的 TTFT/TPOT 真值。
- 解析主结果在无通信/零字节字段上产生 `-nan` 带宽，解析时必须作为不适用值处理。
- DeepSeek trace 采用均衡路由，只能校准事件顺序、kernel 时长和部分可见 overlap。
- Decode RDMA 网络进度没有独立 trace 标记，不能从 GPU kernel 条直接推导完整网络隐藏率。
- MoE hotspot/long-tail 是可控假设数据，目前尚无真实多节点结果验证其绝对时延。
- analytical 与 ns-3、EP 动态矩阵与 Vidur 请求级指标的闭环尚未实现；这是后续研发目标。
- 本周没有 GPU/RDMA 实机条件，不能宣称端到端预测已经达到某个绝对误差范围。

## 提交前判定

第一周交付已达到“结果可复现、来源可追溯、边界明确”的验收目标。可以提交并推送；对外说明时
应使用“第一周基线与方案完成”，不能表述为“MoE/PD 高精度仿真功能已经实现”。
