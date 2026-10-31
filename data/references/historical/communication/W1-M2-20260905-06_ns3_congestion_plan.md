# W1-M2-20260905-06：ns-3 分组级拥塞验证初步方案

## 1. 方案目标

验证 MoE 的 EP `ALLTOALL_EP` 在不同专家流量分布下，是否会造成可观测的网络竞争、队列增长、ECN/CNP 反馈和流完成时间变化。

本方案是第一阶段的实验设计，不代表分组级拥塞实验已经执行完成。执行时不修改 SimCCL、Astra-Sim 或 ns-3 核心通信算法，只改变 workload、拓扑、流量分布和仿真配置。

## 2. 核心假设

在通信总字节数和 GPU 数量基本一致时：

1. 均衡专家流量的链路利用率更均匀，队列长度和流完成时间较低；
2. 热点专家会使少数交换机端口或队列出现更高占用；
3. 长尾专家流量会提高部分 flow 的 FCT，并扩大 P95/P99 与平均值的差距；
4. 如果网络拥塞控制和 ECN/CNP 生效，拥塞场景应能在 trace、队列、CNP 或 QP 速率输出中观察到；
5. 如果不同场景的 EndToEnd 结果完全不变，需要检查流量矩阵是否真正传入 ns-3，而不是直接得到了相同的静态通信量。

## 3. 实验分组

固定以下条件：

- GPU 数量：8 GPU 起步，后续扩展到 16 GPU/2 节点；
- EP 配置：`TP=2, EP=4`；
- 通信类型：`ALLTOALL_EP`；
- 单次通信总字节数：优先固定为 `16777216` bytes；
- 拓扑：`Rail_Opti_SingleToR_8g_8gps_200Gbps_H20`；
- ns-3 线程：`-t 8`；
- 配置文件：`astra-sim-alibabacloud/inputs/config/SimAI.conf`；
- 环境变量：先固定 `AS_SEND_LAT=3 AS_NVLS_ENABLE=1`，后续再做敏感性实验。

### 场景 A：均衡专家流量

所有 EP 对端收到近似相同的数据量。作为无明显热点的基线，用于确认网络本身和 workload 格式正常。

预期现象：

- 端口利用率较均匀；
- 队列长度没有明显单端口持续增长；
- flow FCT 分布较集中；
- CNP/ECN 数量较低或没有明显集中。

### 场景 B：单热点专家

保持总通信量不变，将较大比例的流量集中到一个或少数 EP 对端，形成 incast 或热点端口。

建议第一版比例：

```text
均衡：25% / 25% / 25% / 25%
热点：70% / 10% / 10% / 10%
```

预期现象：

- 热点端口队列长度明显高于均衡场景；
- 热点方向的 FCT 和 slowdown 增大；
- 可能出现更多 ECN 标记、CNP 或速率下降；
- EndToEnd 通信完成时间上升。

### 场景 C：长尾专家流量

使用多个专家的非均匀分布，例如：

```text
50% / 25% / 15% / 10%
```

预期现象：

- 平均值变化可能小于热点场景；
- P95/P99 FCT 和队列长度更能反映尾部影响；
- 部分 flow 受到持续竞争，出现长尾完成时间。

## 4. 执行步骤

### 4.1 固定基线

先运行已经验证成功的均衡最小 workload，确认每次实验都能看到：

```text
Total collectives issued for this layer: 1
Percentage of finished streams: 100 %
```

### 4.2 生成或准备流量矩阵

优先使用 workload 生成器或现有 workload 字段表达通信量。每份输入必须记录：

- 专家数量和 EP group；
- 每个源 rank 到目标专家的字节数矩阵；
- 总通信字节数；
- 是否均衡、热点或长尾；
- workload 文件 SHA256。

如果当前 workload 格式只能表达每个 collective 的总字节数，不能表达 rank-to-expert 矩阵，应明确记录为“当前接口缺口”，不要用总字节数变化冒充专家偏斜实验。

### 4.3 运行 ns-3

每个场景独立保存输出目录，命令模板为：

```bash
mkdir -p results/congestion/<scenario>
AS_SEND_LAT=3 AS_NVLS_ENABLE=1 ./bin/SimAI_simulator -t 8 \
  -w ./example/workload_alltoall_ep_<scenario>.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c ./astra-sim-alibabacloud/inputs/config/SimAI.conf \
  2>&1 | tee results/congestion/<scenario>/run.log
cp -f ncclFlowModel_* results/congestion/<scenario>/
```

每个场景至少重复 3 次；如果仿真完全确定性，记录这一点并保留一次完整原始日志即可。

## 5. 需要采集的指标

### 5.1 Astra-Sim/EndToEnd 指标

从 `ncclFlowModel_EndToEnd.csv` 记录：

- `total exposed comm`；
- `Total time`；
- `Expose_EP_comm`；
- `total comp`；
- collective 数量；
- stream 完成率。

### 5.2 ns-3 分组级指标

优先从 ns-3 monitor/trace 输出采集：

- flow completion time（FCT）；
- FCT 平均值、P50、P95、P99；
- slowdown：`FCT / standalone FCT`；
- 交换机端口队列长度峰值、平均值和持续时间；
- 端口吞吐和链路利用率；
- ECN 标记数量；
- CNP 数量；
- QP 当前发送速率变化；
- packet drop/PFC 事件；
- trace 中的 Enqueue、Dequeue、Recv、Drop 事件。

仓库已有分析入口：

- `ns-3-alibabacloud/analysis/fct_analysis.py`：FCT 和 slowdown 分布；
- `ns-3-alibabacloud/analysis/qlen_analysis.py`：交换机端口队列长度；
- `ns-3-alibabacloud/analysis/bw_analysis.py`：端口吞吐/带宽；
- `ns-3-alibabacloud/analysis/qp_rate_analysis.py`：QP 发送速率；
- `ns-3-alibabacloud/analysis/qp_cnp_analysis.py`：QP CNP 数量；
- `ns-3-alibabacloud/analysis/README.md`：trace_reader 输出格式和过滤方式。

trace 事件至少要区分：

```text
Enqu：入队
Dequ：出队
Recv：接收
Drop：丢包
```

## 6. 对照表

| 场景 | 总通信量 | 热点比例 | EndToEnd Total time | FCT P50 | FCT P95 | FCT P99 | 队列峰值 | CNP/ECN | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 均衡 |  | 0% |  |  |  |  |  |  | 基线 |
| 单热点 |  | 70% |  |  |  |  |  |  | 待测 |
| 长尾 |  | 50/25/15/10 |  |  |  |  |  |  | 待测 |

建议至少计算：

```text
FCT slowdown = FCT / standalone FCT
队列增长量 = 热点场景队列峰值 - 均衡场景队列峰值
尾延迟变化 = P99_hotspot - P99_balanced
```

## 7. 判定标准

只有同时满足以下条件，才能报告“观察到分组级拥塞”：

1. 热点或长尾场景的通信矩阵与均衡场景确实不同；
2. 总通信量、GPU 数量、拓扑和其他配置保持可比；
3. 至少一个交换机端口/队列出现可重复的队列增长或利用率集中；
4. FCT、slowdown、CNP/ECN 或 P99 指标相对均衡基线出现可解释变化；
5. 变化能够从 trace 或 monitor 输出定位到具体端口、流或专家通信方向。

如果只有 EndToEnd 总时间变化，但没有队列、流或 ECN 证据，只能报告“通信完成时间发生变化”，不能直接报告“已证明分组级拥塞”。

## 8. 当前风险与限制

- 当前最小 workload 只验证了 collective 和网络流完成，不等价于真实专家路由矩阵；
- 如果输入格式不能表达 rank-to-expert 字节矩阵，需要先扩展接口或使用已有 trace/replay 入口；
- analytical 与 ns-3 的统计口径目前存在差异，必须先统一单位和通信组映射；
- `ALLTOALL_EP` 到 Vidur 请求级指标的回写尚未完成，因此本方案先验证通信/网络层，不能直接推出 TTFT、TPOT 或 P99 请求时延变化；
- 8 GPU 单节点适合冒烟，跨节点拥塞应使用 16 GPU 或更大拓扑复验。

## 9. 第一阶段交付

本方案完成后，第一阶段可以交付：

1. 均衡、热点、长尾三组 workload 定义；
2. 每组 ns-3 原始日志和 flow/trace/monitor 输出；
3. FCT、队列、带宽、CNP/ECN 和 EndToEnd 对照表；
4. 明确的拥塞判定结论和失败边界；
5. 后续接入 Vidur 请求级指标所需的通信结果接口需求。
