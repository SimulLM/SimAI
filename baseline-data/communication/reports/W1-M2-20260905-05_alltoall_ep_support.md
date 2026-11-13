# W1-M2-20260905-05：ALLTOALL / ALLTOALL_EP 支持验证

## 1. 实验编号

`W1-M2-20260905-05`

## 2. 实验名称

最小 `ALLTOALL` / `ALLTOALL_EP` workload 的 analytical 与 ns-3 对照验证

## 3. 实验目的

验证以下通信链路是否真实成立：

```text
最小 workload
  -> Astra-Sim 通信语义解析
  -> AllToAll flow model
  -> analytical / ns-3 执行
  -> EndToEnd CSV
  -> 上层 latency 读取
```

本实验重点确认：

- `ALLTOALL` 是否能够被计算并执行；
- `ALLTOALL_EP` 是否能够进入 EP group 的 AllToAll 路径；
- ns-3 是否真正发行 collective，而不是只生成空 CSV；
- 拓扑规模与 workload 的 GPU 配置是否必须匹配。

## 4. 实验时间

- 日期：2026-09-05
- 环境：WSL/Linux
- 记录人：未记录

## 5. 实验环境与输入

### Workload 文件

- [workload_alltoall_minimal.txt](../example/workload_alltoall_minimal.txt)
- [workload_alltoall_ep_minimal.txt](../example/workload_alltoall_ep_minimal.txt)

两份 workload 都只有一个 layer，通信量均为 `16777216` bytes。

普通 `ALLTOALL`：

```text
model_parallel_NPU_group: 8
 ep: 1
all_gpus: 8
```

`ALLTOALL_EP`：

```text
model_parallel_NPU_group: 2
ep: 4
all_gpus: 8
```

EP 版本采用 `TP=2, EP=4`，乘积为 8，与总 GPU 数量一致。若将模型并行组设置为 1，前向维度会全部关闭，导致 ns-3 不发行 collective。

### ns-3 拓扑

```text
Rail_Opti_SingleToR_8g_8gps_200Gbps_H20
```

生成命令：

```bash
python3 ./astra-sim-alibabacloud/inputs/topo/gen_Topo_Template.py \
  --ro -g 8 -gt H20 -bw 200Gbps -nvbw 2400Gbps
```

## 6. 实验命令

### 6.1 ALLTOALL analytical

```bash
./bin/SimAI_analytical \
  -w ./example/workload_alltoall_minimal.txt \
  -g 8 -nv 8 -nic 100 -n_p_s 8 -g_p_s 1 \
  -r alltoall-minimal-
```

日志：

- [analytical.log](W1-M2-20260905-05_alltoall/analytical.log)

### 6.2 ALLTOALL_EP analytical

```bash
./bin/SimAI_analytical \
  -w ./example/workload_alltoall_ep_minimal.txt \
  -g 8 -nv 8 -nic 100 -n_p_s 1 -g_p_s 8 \
  -r alltoall-ep-minimal-
```

日志：

- [analytical.log](W1-M2-20260905-05_alltoall_ep/analytical.log)

### 6.3 ALLTOALL ns-3

```bash
AS_SEND_LAT=3 AS_NVLS_ENABLE=1 ./bin/SimAI_simulator -t 8 \
  -w ./example/workload_alltoall_minimal.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c astra-sim-alibabacloud/inputs/config/SimAI.conf
```

日志和输出：

- [run.log](W1-M2-20260905-05_alltoall/ns3_rail8/run.log)
- [ncclFlowModel_EndToEnd.csv](W1-M2-20260905-05_alltoall/ns3_rail8/ncclFlowModel_EndToEnd.csv)

### 6.4 ALLTOALL_EP ns-3

```bash
AS_SEND_LAT=3 AS_NVLS_ENABLE=1 ./bin/SimAI_simulator -t 8 \
  -w ./example/workload_alltoall_ep_minimal.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c astra-sim-alibabacloud/inputs/config/SimAI.conf
```

日志和输出：

- [run.log](W1-M2-20260905-05_alltoall_ep/ns3_rail8_tp2_ep4/run.log)
- [ncclFlowModel_EndToEnd.csv](W1-M2-20260905-05_alltoall_ep/ns3_rail8_tp2_ep4/ncclFlowModel_EndToEnd.csv)

## 7. 关键观察

### 7.1 Analytical 结果

| 场景 | `total exposed comm` | `Total time` | 状态 |
|---|---:|---:|---|
| `ALLTOALL` | 25 | 25 | 成功 |
| `ALLTOALL_EP` | 3030 | 3030 | 成功 |

两个 workload 都被 analytical 入口成功打开并识别为 all-to-all 通信。

### 7.2 ns-3 结果

| 场景 | `total exposed comm` | `Total time` | collective | stream 完成率 | 状态 |
|---|---:|---:|---:|---:|---|
| `ALLTOALL` | 52 | 52 | 1 | 100% | 成功 |
| `ALLTOALL_EP` | 45 | 45 | 1 | 100% | 成功 |

ns-3 日志中均出现：

```text
Total collectives issued for this layer: 1
Percentage of finished streams: 100 %
```

说明两类通信都真正进入了网络仿真，而不是只生成空结果文件。

注意：日志中的仿真 tick（普通 `ALLTOALL` 为 52227，`ALLTOALL_EP` 为 45090）与 EndToEnd CSV 中的统计值（52、45）不是同一个展示单位，报告中应分别保留，不直接混算。

## 8. 异常与修正过程

### 8.1 使用 128 GPU 拓扑时崩溃

最初使用 `Spectrum-X_128g_8gps_100Gbps_A100` 拓扑运行 8 GPU workload，ns-3 在启动后报错：

```text
terminate called after throwing an instance of 'std::bad_array_new_length'
```

将线程参数从 `-t 16` 改为 `-t 8` 后仍然失败，因此根因不是线程数量，而是拓扑规模与 workload 的 GPU 配置不匹配。

### 8.2 改用匹配的 8 GPU 拓扑

改用：

```text
Rail_Opti_SingleToR_8g_8gps_200Gbps_H20
```

并使用 `-t 8` 后，普通 `ALLTOALL` 和 `ALLTOALL_EP` 均成功运行。

### 8.3 EP 并行组设置错误

最初的 EP workload 使用：

```text
model_parallel_NPU_group: 1
ep: 8
```

ns-3 日志显示：

```text
all dims disabled, no forward pass collective
Total collectives issued for this layer: 0
```

修正为：

```text
model_parallel_NPU_group: 2
ep: 4
```

之后日志变为：

```text
all-to-all forward pass collective issued for layer: alltoall_ep_test
Total collectives issued for this layer: 1
Percentage of finished streams: 100 %
```

## 9. 结果分析

本实验确认：

1. `ALLTOALL` 可以进入 analytical 和 ns-3 执行路径；
2. `ALLTOALL_EP` 可以被识别为 EP group 的 AllToAll 通信；
3. 两类通信都能够生成有效 EndToEnd CSV；
4. ns-3 确实发行并完成了 collective；
5. workload 的并行组配置和拓扑规模必须与实验规模一致。

### 9.1 Vidur 上层回读验证

检查文件 [communication_time_predictor.py](../vidur-alibabacloud/vidur/execution_time_predictor/communication_time_predictor.py) 后发现，当前 SimAI 预测器路径存在以下限制：

- `get_execution_time()` 生成的 workload 类型写死为 `ALLREDUCE`；
- workload 文件名使用 `allreduce_{workload_identifier}.txt`；
- 结果文件使用 `ncclFlowModel_EndToEnd_{command_identifier}.csv`；
- 没有根据 `ALLTOALL` 或 `ALLTOALL_EP` 的 workload 标识读取本次实验的 CSV。

因此，本实验可以确认 CSV 已由 ns-3 生成，但不能确认当前 Vidur 预测器已经消费这两份 `ALLTOALL` / `ALLTOALL_EP` 结果。准确结论是：

> SimAI 网络层已经生成有效 AllToAll 结果；当前 Vidur SimAI predictor 仍主要支持写死的 AllReduce 回读路径，AllToAll/EP 结果尚未接入上层预测接口。

这也是本次实验发现的真实闭环缺口，而不是实验失败。

## 10. Analytical 与 ns-3 对比

### 10.1 定量结果

| 场景 | analytical `Total time` | ns-3 `Total time` | 绝对差异 | 相对差异 | ns-3 collective |
|---|---:|---:|---:|---:|---:|
| `ALLTOALL` | 25 | 52 | 27 | 108.00% | 1 |
| `ALLTOALL_EP` | 3030 | 45 | 2985 | 98.51% | 1 |

相对差异计算为：

```text
abs(ns3 - analytical) / analytical
```

两组实验的输入通信量均为 `16777216` bytes，使用 8 GPU、8 GPU 匹配拓扑和相同 ns-3 配置。两种后端都生成了非空 EndToEnd CSV，且 ns-3 日志确认 collective 和 stream 均完成。

### 10.2 模型差异分析

- analytical 直接依据通信模型、带宽和并行组计算统计时延，不需要逐包运行网络事件，适合快速扫描参数和大规模 workload；
- ns-3 使用具体拓扑和网络事件推进，能够反映链路、队列和流传输行为，运行成本更高；
- `ALLTOALL` 的结果从 25 变为 52，说明具体网络路径相较解析估计产生了额外开销；
- `ALLTOALL_EP` 的结果从 3030 变为 45，差异方向与普通 `ALLTOALL` 相反，说明当前两种后端对 EP group、通信组规模或统计口径的处理存在明显差异，不能直接解释为 ns-3 更准确；
- 在完成通信组映射、单位和 topology 配置的进一步核对前，不能把这组数值当作精度结论。

### 10.3 步骤 10 结论

当前可以确认模型的适用边界：

| 模型 | 适合用途 | 当前证据 |
|---|---|---|
| analytical | 快速扫描、参数搜索、基础通信趋势分析 | 两种最小 workload 均成功输出 |
| ns-3 | 拓扑、链路、队列、流完成情况和拥塞场景验证 | 两种最小 workload 均完成 collective |
| Vidur SimAI predictor | 当前主要是 AllReduce 的上层回读 | 代码路径写死 `ALLREDUCE`，尚未覆盖本实验两种 AllToAll |

因此，步骤 10 已完成“基础结果对比”和“适用范围初判”，但 EP 结果差异还需要后续做通信组和统计口径核对。

因此，在当前最小验证范围内，可以将结论写为：

> `ALLTOALL` 和 `ALLTOALL_EP` 的基础通信支持已经验证通过，且 ns-3 路径能够产生有效网络仿真结果。该结论不代表已经完成复杂 MoE 的专家负载偏斜、热点拥塞和尾延迟验证。

## 11. 当前限制

本实验还没有验证：

- 不同专家负载分布；
- 热点专家导致的拥塞；
- 多层 MoE 连续通信；
- 多节点跨机通信；
- analytical 与 ns-3 的误差来源；
- Vidur 对这两份新 CSV 的实际 latency 回读；当前代码证据表明该路径尚未接通。

## 12. 下一步

1. 在 Vidur predictor 中增加通信类型和 workload 文件的可配置入口；
2. 让 `ALLTOALL` / `ALLTOALL_EP` 使用各自的 CSV 结果回读 latency；
3. 重新验证上层请求级预测闭环；
4. 设计专家负载均衡与热点专家对照 workload；
5. 在更大规模拓扑上验证跨节点 `ALLTOALL_EP`；
6. 将本实验结论汇总到最终报告。

## 13. 结论

本次最小对照实验成功完成了 `ALLTOALL` 和 `ALLTOALL_EP` 的 analytical/ns-3 基础路径验证。两类 workload 均可被解析并生成通信结果，ns-3 也成功完成 collective 和流传输。但当前 Vidur SimAI predictor 的代码路径仍写死为 AllReduce，尚未消费本次两份 AllToAll CSV。系统能力应表述为“基础网络通信路径已验证，AllToAll/EP 到 Vidur 的上层回读仍未闭环”，而不是“复杂 MoE 场景已经完整支持”。
