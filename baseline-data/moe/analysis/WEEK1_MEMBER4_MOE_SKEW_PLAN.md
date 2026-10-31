# 成员四：第一周工作四——MoE 偏斜数据生成与实验方案

## 技术摘要

本方案把 MoE 路由偏斜固定为三类可复现输入：均匀、热点和长尾。默认样例保持
16,384 tokens、Top-K=8、256 experts，即每个场景均有 131,072 次 expert assignment；
只改变 assignment 在 expert 和 EP rank 之间的分布，因此后续性能差异不能由 token 总量变化解释。

样例覆盖 EP32 与 EP128。均匀场景的最忙 rank/平均 rank 负载为 1；热点场景约为 4.92；
Zipf 长尾场景在 EP32 为 8.50、EP128 为 32.53。相同 expert 分布在更大的 EP 规模下产生
更高 rank 偏斜，说明实验必须把“专家概率”和“专家到 rank 的放置”作为两个独立因素记录。

这些数据是受控压力测试，不是真实路由真值。DeepSeek 公开 trace 使用绝对均衡路由，只能作为
均匀场景的时序参考，不能验证热点或长尾场景的绝对性能。

## 固定输入与三种模式

| 项目 | 默认值 | 固定原因 |
|---|---:|---|
| Tokens | 16,384 | 与公开 Prefill profile 的每卡 token 规模对齐，作为可控样例 |
| Top-K | 8 | 每个 token 产生 8 次 expert assignment |
| Routed experts | 256 | 允许同时被 EP32 与 EP128 整除 |
| 总 assignments | 131,072 | `tokens × top_k`，所有场景严格相同 |
| Expert→rank 映射 | 连续 ID 分块 | 简单、确定、容易检查放置效应 |
| 随机种子 | 20250321 | 固定长尾 expert 排列 |

三种模式定义如下：

1. **均匀（uniform）**：每个 expert 概率相同；默认每个 expert 接收 512 assignments。
2. **热点（hotspot）**：前 10%（四舍五入为 26 个）experts 接收 50% assignments，其余
   230 个平分另一半；热点 expert 连续放置在低 ID rank，用于显式制造网络热点。
3. **长尾（long_tail）**：expert 概率服从 Zipf 分布，`alpha=1.2`；概率排名通过固定种子
   映射到 expert ID，避免每次运行随机漂移。

整数 assignment 使用最大余数法分配，确保非负且总数精确守恒。

## 样例的偏斜强度

| 模式 | Expert 最大/均值 | Expert CV | Expert Gini | Top 10% expert 占比 | EP32 rank 最大/均值 | EP128 rank 最大/均值 |
|---|---:|---:|---:|---:|---:|---:|
| 均匀 | 1.000 | 0.000 | 0.000 | 10.156% | 1.000 | 1.000 |
| 热点 | 4.924 | 1.319 | 0.398 | 49.989% | 4.922 | 4.924 |
| 长尾 | 64.928 | 4.666 | 0.796 | 75.974% | 8.497 | 32.526 |

长尾场景的 expert 最大/均值在 EP32 与 EP128 中相同，因为 expert 概率没有变化；rank
最大/均值明显变化，是 expert 聚合粒度和放置共同造成的。后续不能只报告 expert Gini，必须同时
报告 destination-rank 偏斜，否则无法判断网络层真正看到的负载不均衡。

## 指标框架

### 主要结果指标

| 指标 | 定义 | 适用阶段 | 它回答的问题 |
|---|---|---|---|
| EP communication makespan P99 | 每层从首个 EP 消息发出到最后一个 EP 消息完成的 P99 | Prefill/Decode | 偏斜是否制造通信拖尾 |
| P99 TTFT 相对均匀基线变化 | `(skew_p99_ttft - uniform_p99_ttft) / uniform_p99_ttft` | Prefill | 偏斜是否传导到首 token 尾时延 |
| P99 TPOT 相对均匀基线变化 | `(skew_p99_tpot - uniform_p99_tpot) / uniform_p99_tpot` | Decode | 偏斜是否传导到逐 token 尾时延 |

吞吐作为同级运行结果报告，但不替代尾时延：偏斜可能先恶化少数请求而尚未显著改变平均吞吐。

### 驱动指标

- Expert 最大/均值、CV、Gini、Top 10% share：描述路由输入强度。
- Destination-rank 最大/均值与 CV：描述 EP rank 实际接收的工作量。
- Hottest-link utilization 与 queueing P99：定位是否由网络热点造成。
- Exposed communication ratio：`未被计算覆盖的 EP 时间 / EP 总时间`。
- Compute/communication overlap ratio：必须基于消息发出与完成时间，而不只使用 launch kernel。

### 守护指标

- 每个对比组的 tokens、Top-K、总 assignments、hidden size、dtype 和总理论字节数相同；
- 模型输出质量或路由丢弃率不因 capacity/drop 策略暗中变化；
- 模拟器 wall-clock、峰值内存和 ns-3 事件数同时记录，避免只追求精度而忽略成本；
- 解析模型与 ns-3 必须使用相同输入矩阵，禁止分别生成随机输入。

当前不设置武断的性能提升/恶化阈值。第二周先得到均匀基线方差，再用置信区间设置最小可检测效应。

## 实验矩阵

| 维度 | 取值 |
|---|---|
| Phase | Prefill、Decode |
| Routing mode | uniform、hotspot、long_tail |
| EP size | 32、128 |
| Network backend | analytical、ns-3 |
| Placement | clustered、seeded-permutation；后续增加 round-robin |
| Seed | 均匀 1 次；热点/长尾至少 10 个固定种子或热点旋转位置 |
| 重复 | 每个确定输入至少 3 次，确认模拟器本身是否存在运行波动 |

每一行实验必须同时保存输入哈希、Git SHA、子模块 SHA、命令、随机种子、运行时间和输出目录。

## 可检验假设

- **H1：输入偏斜单调增强。** 在默认参数下，expert 与 rank 的 CV/Gini 应满足
  `uniform < hotspot < long_tail`；若不满足，先检查 expert 放置和整数取整。
- **H2：总量不变但拖尾增加。** 三种模式总 assignments 与理论总字节保持相同，但
  hotspot/long_tail 的 EP makespan P99、最热链路利用率和队列 P99 高于均匀场景。
- **H3：尾部指标比均值敏感。** P99 TTFT/TPOT 的相对恶化幅度应大于平均 TTFT/TPOT；
  若只有均值变化，需要检查是否真正模拟了 rank/link 竞争。
- **H4：Decode 对暴露等待更敏感。** Decode 的计算空隙更短，预计相同 rank 偏斜对
  TPOT 的相对影响更大；Prefill 可能通过跨 stream 计算覆盖更多 EP 时间。该方向必须由实验验证。
- **H5：解析模型低估热点代价。** 仅按平均带宽计算的 analytical 后端预计低估 ns-3 中的
  queueing 和 P99 通信完成时间，且误差随 rank CV 增大。
- **H6：放置可以改变结论。** 保持 expert load multiset 不变，仅改变 expert→rank 映射，
  rank CV 和网络拥塞仍会变化；因此不能把 expert 偏斜直接等同于网络偏斜。

这些是假设，不是本周已经证实的结论。

## 数据接口草案

本周产物是 expert/rank 期望负载向量。JSON 中每个场景包含：

```text
scenario metadata
  ├─ mode, EP size, seed, distribution parameters
  ├─ expert_metrics / rank_metrics
  ├─ expert_loads: expert_id, rank_id, assignments, share
  └─ rank_loads: rank_id, assignments, share
```

第二周接入 Vidur→SimAI 时，应扩展为逐 micro-batch 的 flow 表：

| 字段 | 含义 |
|---|---|
| `scenario_id` | 场景与参数版本 |
| `request_id` / `microbatch_id` | 请求和双 micro-batch 关联 |
| `phase` / `layer_id` | Prefill/Decode 与 MoE 层 |
| `src_rank` / `dst_rank` | EP 流量矩阵坐标 |
| `expert_id` | 路由目标 expert |
| `token_count` | 本 flow 的 assignment 数 |
| `bytes` | dtype、hidden size 和协议决定的有效载荷 |
| `issue_ts` / `finish_ts` | 网络发出与完成，用于计算暴露等待 |
| `correlation_id` | 与任务图、SimCCL flow 和请求指标对齐 |

若缺少 `src_rank→dst_rank`，当前负载向量只能描述目的端压力，不能唯一确定链路级拥塞。

## 与当前代码的边界

AICB 当前只定义 `RoundRobin` 和 `UniformRandom`。`UniformRandom` 使用无固定 seed 的
multinomial 分布，随后只返回最忙 rank 的平均 expert 负载；它没有保存完整 expert/rank 矩阵，
也不能表达指定热点或 Zipf 长尾。训练模型中还存在“假设 token 均匀分配”的 TODO。

因此本周不修改 AICB 核心逻辑。独立生成器先提供稳定实验输入和校验结果；第二周接口冻结后，
再决定由 AICB 读取矩阵，还是由 Vidur 请求调度层按 micro-batch 产生矩阵。

## 限制与稳健性检查

- 样例是 assignment 聚合，不保留同一 token 的 Top-K expert 共现关系；
- 未模拟 expert capacity、token drop、辅助负载均衡损失或动态 expert placement；
- 热点默认聚集于低 ID rank，会刻意放大 rank 偏斜；必须用热点轮换和随机放置做敏感性分析；
- Zipf `alpha=1.2` 是压力参数，不是来自生产 trace 的估计；至少扫描 `0.8/1.0/1.2/1.5`；
- 当前只生成目的端负载向量，网络实验前必须补齐 source→destination flow；
- DeepSeek 公开 trace 只覆盖均衡路由，不能证明任何偏斜场景的绝对结果。

## 复现方法

在仓库根目录执行：

```bash
python scripts/generate_moe_skew_scenarios.py
```

默认生成：

- `docs/data/moe_skew_scenarios.json`：完整配置、指标、expert/rank 负载；
- `docs/data/moe_skew_expert_loads.csv`：每个 expert 的可审计长表；
- `docs/data/moe_skew_summary.csv`：六个场景的偏斜指标摘要。

调整参数示例：

```bash
python scripts/generate_moe_skew_scenarios.py \
  --tokens 16384 --top-k 8 --num-experts 256 --ep-sizes 32 128 \
  --seed 20250321 --hotspot-fraction 0.10 --hotspot-share 0.50 \
  --zipf-alpha 1.20
```

生成器会检查 assignment 守恒、非负性及 `num_experts % ep_size == 0`。

## 后续问题

1. flow 矩阵应由请求调度层生成，还是作为 AICB workload 的外部输入？
2. 字节量应按 BF16 combine、FP8 dispatch 分开，还是先使用统一 dtype 基线？
3. Expert placement 是否固定，还是需要单独加入动态迁移实验？
4. 第一版闭环优先回写 TTFT/TPOT，还是先只验证逐层 EP makespan？
