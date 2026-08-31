# 项目分析

## 目标与基线

SimInfer 是基于 SimAI 的维护型 Fork，作为高保真 LLM 推理仿真的基础。精确上游基线、许可证与子模块固定版本见 [UPSTREAM.md](../UPSTREAM.md)。本分析描述当前检出的代码，不代表上游所宣传的全部功能均已达到生产可用状态。

## 模块地图

| 模块 | 角色 | 关键路径 |
|---|---|---|
| AICB | GPU 工作负载生成、回放与算子画像 | `aicb/aicb.py`、`aicb/workload_generator/` |
| SimCCL | 将集合通信决策转换为点对点 FlowModel | `SimCCL/src/main.cc`、`SimCCL/src/mock/v2.30/MockNcclGroup.cc` |
| Astra-Sim | 工作负载执行、并行策略、集合通信与统计 | `astra-sim-alibabacloud/astra-sim/system/`、`astra-sim-alibabacloud/astra-sim/workload/` |
| ns-3 后端 | Astra-Sim flow 的分组级网络执行 | `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/`、`ns-3-alibabacloud/` |
| 解析后端 | 基于 bus-bandwidth 的快速通信估计 | `astra-sim-alibabacloud/astra-sim/network_frontend/analytical/` |
| 物理后端 | RDMA 流量生成模式 | `astra-sim-alibabacloud/astra-sim/network_frontend/phynet/` |
| Vidur | 请求级推理事件仿真、调度和指标 | `vidur-alibabacloud/vidur/` |
| DeepSeek profile-data（外部参考） | V3/R1 的公开 PyTorch Profiler trace，用于计算—通信重叠行为校准 | `https://github.com/deepseek-ai/profile-data` |

## 执行与数据流

```text
AICB/AIOB 或模型配置
  -> 工作负载/画像数据
  -> Astra-Sim Workload + Layer 调度
  -> 集合通信的 SimCCL FlowModel
  -> 解析后端 或 ns-3 分组 或物理 RDMA 模式
  -> CSV 统计结果

Vidur 请求生成器
  -> 事件队列 -> 全局/副本/阶段调度器
  -> 执行时间预测器（Vidur、AICB、SimAI 解析、SimAI ns-3）
  -> 指标、JSON trace、Chrome trace
```

`vidur/main.py` 创建 `SimulationConfig` 并运行 `Simulator`；`vidur/simulator.py` 推进基于堆的事件队列；`BaseExecutionTimePredictor.get_execution_time()` 选择预测后端；`communication_time_predictor.py` 中的 `TPTimePredictor` 调用 SimAI 二进制文件并缓存 CSV 结果。

核心仿真中，`astra-sim-alibabacloud/astra-sim/workload/Workload.cc` 的 `Workload::call` 选择并行策略，`Layer` 记录端到端与详细结果。解析可执行程序入口为 `network_frontend/analytical/AnalyticalAstra.cc`，ns-3 入口为 `network_frontend/ns3/AstraSimNetwork.cc`。

## 已确认扩展点

1. **推理工作负载生成**：`aicb/workload_generator/SimAI_inference_workload_generator.py` 为推理模型生成 TP AllReduce 与 `ALLTOALL_EP` 语义。
2. **集合通信 Flow 建模**：`SimCCL/src/mock/v2.30/MockNcclGroup.cc` 选择/生成 AllReduce、AllGather、ReduceScatter、AlltoAll、Broadcast 的 flow。
3. **Astra-Sim AllToAll**：`astra-sim-alibabacloud/astra-sim/system/collective/AllToAll.cc` 与 `Sys::generate_all_to_all` 提供核心实现。
4. **PD 调度**：Vidur 配置和集群实体包含 Prefill/Decode 专用配置；`vidur-alibabacloud/tests/test_pd_separation.py` 覆盖基础 PD 集群行为。
5. **通信后端**：`BaseExecutionTimePredictor` 支持 `vidur`、`aicb`、`simai_analytical`、`simai_simulation` 后端标签。

## 当前缺口与风险

- Vidur 的 SimAI 桥接以 TP AllReduce 为中心。AICB 会生成 `ALLTOALL_EP`，Astra-Sim/SimCCL 也支持 AllToAll，但当前代码尚未建立“请求级动态 EP 流量矩阵 -> ns-3 -> Vidur”的闭环。
- `aicb` 执行时间后端有意将 TP 通信时间设为零（`BaseExecutionTimePredictor` 中存在 TODO），不能把它作为高精度基线。
- `TPTimePredictor` 使用子进程、固定命令假设和基于文件的缓存；在并发实验前，应为缓存键加入完整拓扑/配置版本。
- 构建脚本面向 Bash/Linux。`scripts/build.sh -c ns3` 会改动生成目录，文档中的 ns-3 构建时间可达 5–15 分钟。
- 根 Dockerfile 的路径移动逻辑应在作为开发镜像之前复核；已列为首批 Issue，而非在本次治理中修改。
- 除 ns-3 外，目前仅有聚焦 Vidur PD 的 pytest；此前没有顶层 CI 工作流。
- ns-3 的 GPL-2.0 分发风险见 [UPSTREAM.md](../UPSTREAM.md#许可证说明)。
- AIOB 的真实算子画像需要 GPU；但公开 DeepSeek profile-data 可在无 GPU 条件下用于解析和比对 trace。它采用均衡 MoE 路由，且不是端到端服务压测，不能替代偏斜 MoE 或 TTFT/TPOT 的真实校准。

## 校准数据边界

DeepSeek 的 V3/R1 `profile-data` 是第一阶段的行为校准参考：比较 Prefill/Decode 中计算、AllToAll、等待事件的顺序、持续时间占比和重叠比例。它不构成端到端服务时延真值。正式的 TTFT、TPOT、P95/P99、吞吐和网络拥塞精度结论，必须在后续通过带有明确硬件/拓扑元数据的真实或可信实验数据验证。完整策略见 [CALIBRATION.md](CALIBRATION.md)。

## 建议的粒度模型

目标应采用混合粒度，而不是让每个请求都新启动一次 ns-3：

- 请求/批次级：Vidur 到达、批处理、SLO 指标；
- 算子/DAG 级：计算与通信依赖图；
- 集合通信/flow 级：SimCCL 与 Astra-Sim 通信操作；
- 分组级：仅用于高保真通信评估和经校准的缓存条目。

这能在关键处保留分组级精度，同时使设计空间探索保持可控。
