# 成员四：实验记录与校准数据模板

## 1. 目的

本模板保证每个性能结论都能回答：使用了什么代码和输入、在哪个环境运行、比较哪个层级、
误差如何计算、运行成本是多少，以及哪些因素尚未建模。

配套机器可读模板：

- `docs/data/experiment_record_template.csv`：一次 run 一行，记录复现上下文与结果。
- `docs/data/calibration_table_template.csv`：一个 run 的一个 metric 一行，记录参考值、仿真值和误差。

提交实验结果时复制模板并改名，不直接覆盖空模板。大体积原始 trace、二进制、`results/` 和
ns-3 临时输出不进入 Git；仓库只保存摘要、哈希和可重新生成它们的命令。

## 2. 实验目录规范

```text
experiments/<experiment_id>/
  manifest.yaml          # 环境、版本、输入、命令、假设
  metrics.csv            # 机器可读结果
  calibration.csv        # 参考值与仿真值逐指标对齐
  summary.md             # 结论、图表、限制与异常
  checksums.sha256       # 未提交原始输入/输出的哈希
  logs/                  # 本地保存；只提交必要错误摘录
```

`experiment_id` 建议格式：

```text
YYYYMMDD-<phase>-<model>-<routing>-<backend>-<short-seq>
```

示例：`20260907-prefill-deepseekv3-hotspot-ns3-001`。

## 3. 实验记录必填字段

### 身份与版本

| 字段 | 说明 |
|---|---|
| experiment_id / run_id | 实验组与单次重复的唯一 ID |
| created_at / operator | 带时区时间与执行人 |
| git_branch / git_sha | 主仓库分支和完整提交 SHA |
| submodule_shas | SimCCL、AICB、ns-3 的固定 SHA |
| dirty_worktree | 必须为 false；否则解释差异 |

### 输入与环境

| 字段 | 说明 |
|---|---|
| source_kind / source_uri | synthetic、trace、real_run；来源路径或 URL |
| input_files / input_sha256 | 所有输入及原始字节哈希 |
| os / kernel / python / compiler | 可复现工具链 |
| hardware | CPU、GPU 型号/数量、显存；无 GPU 时明确写 none |
| topology / bandwidth | 节点、GPU/节点、链路和带宽参数 |

### Workload 与模型

| 字段 | 说明 |
|---|---|
| model / dtype / phase | 模型、精度、Prefill/Decode/Mixed |
| input/output length | 固定值或分布摘要与数据文件 |
| arrival_process / rate | 到达过程、单位和请求率 |
| TP/PP/EP/DP | 各并行维度 |
| batch policy / scheduler | 调度器和所有参数 |
| KV policy / PD placement | KV block、抢占、PD 资源与放置 |
| routing mode / seed | uniform、hotspot、long_tail 或 trace；随机种子 |

### 执行与结果

| 字段 | 说明 |
|---|---|
| backend | real、vidur、aicb、simai_analytical、simai_simulation |
| command | 完整可执行命令，不省略环境变量 |
| exit_code / status | passed、failed、partial |
| output_path / output_sha256 | 结果路径、哈希和是否提交 |
| repetitions | 重复次数；聚合规则另行写明 |
| wall_time_s / peak_rss_mb | 仿真运行成本 |
| notes / limitations | 警告、异常、未建模因素、结果边界 |

## 4. 校准表粒度

校准表采用 long format：每行只比较一个 metric、一个统计量和一个比较层级。禁止把 TTFT、
通信时间、吞吐等异质指标放在同一单元格。

| 层级 | metric 示例 | 参考来源 |
|---|---|---|
| Event | operator/collective duration、start order、overlap ratio | profiler trace、微基准 |
| Communication | AllToAll makespan、exposed time、queueing、hottest-link utilization | DeepSeek trace、真实网络、ns-3 |
| Request | TTFT、TPOT/TBT、E2E、P95/P99 | 真实 serving run 或可信公开数据 |
| System | throughput、goodput、KV/GPU utilization | 真实 serving run |
| Cost | simulator wall time、peak RSS、ns-3 event count | 本次运行测量 |

`comparison_scope` 必须写明比较的是行为、绝对数值还是相对趋势：

- `behavior_only`：只验证事件顺序、依赖和重叠形状；
- `absolute_value`：有同硬件、同输入、同定义的参考值；
- `relative_trend`：比较配置变化方向，不宣称绝对精度。

## 5. 误差公式

当 `reference_value` 有效且非零时：

```text
signed_error   = simulated_value - reference_value
absolute_error = abs(simulated_value - reference_value)
relative_error = absolute_error / abs(reference_value)
relative_error_percent = relative_error * 100
```

P95/P99 不是误差公式，而是对样本分布取分位数。若要报告 P95/P99 error，必须先在相同 request
或 event ID 上计算逐样本误差，再对误差分布取分位数；不能用 `simulated_p99 - reference_p99`
冒充“P99 误差”。后者应命名为 `p99_quantile_gap`。

参考值为零时，`relative_error` 留空并写 `zero_reference`，不得除零。`NaN/-nan` 必须转换为缺失值，
并在 `notes` 中说明是不适用、解析失败还是上游异常。

## 6. 最低验收规则

一次实验只有同时满足以下条件才能标为 `passed`：

- Git、子模块、输入哈希和完整命令齐全；
- 程序退出码为 0，输出存在且可解析；
- 守恒条件通过，例如 token、assignment 和理论字节总量不因对照组变化；
- metric 单位、统计量和样本数明确；
- 至少记录 wall time；高成本运行还应记录 peak RSS/ns-3 event count；
- 参考值与仿真值来自相同模型、输入、硬件/topology 和指标定义，或明确降级为行为/趋势比较；
- 报告失败和异常值，不删除不利样本。

## 7. 第一轮校准表设计

| 顺序 | 场景 | 比较层级 | 参考 | 预期产出 |
|---:|---|---|---|---|
| 1 | DeepSeek Prefill/Decode | behavior_only / Event | 公开 profiler trace | 事件顺序、kernel duration、可见 overlap |
| 2 | 单 collective 微基准 | Communication | 真实或可信 NCCL 数据 | analytical/ns-3 communication error |
| 3 | 固定 KV/batch 状态 | Request/Execution | vLLM/Vidur 可复现实跑 | iteration 与内存状态一致性 |
| 4 | PD 共置与分离 | Request | DistServe 风格实跑 | TTFT、TPOT、KV transfer、goodput |
| 5 | uniform/hotspot/long_tail | Communication + Request | 真实多节点或校准 ns-3 | 偏斜到 P99 的传播 |

当前 DeepSeek trace 采用均衡路由且没有端到端请求到达信息，因此第一行只能标为
`behavior_only`；不得填写 TTFT、TPOT 或偏斜场景的绝对误差。

## 8. 第一周模板自检

- 两份 CSV 表头均包含计划要求的真实值、仿真值、绝对/相对误差、P95/P99 误差和运行成本。
- 增加了单位、样本数、比较层级、参考/仿真配置哈希，防止错误对齐。
- 增加 zero reference、NaN 和 quantile gap 规则，避免产生无意义百分比。
- 模板不伪造尚未取得的真实值；未知值为空并由 `status/notes` 解释。
