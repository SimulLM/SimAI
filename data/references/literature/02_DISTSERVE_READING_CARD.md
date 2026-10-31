# DistServe 阅读卡

- **论文**：*DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving*
- **作者**：Yinmin Zhong 等
- **版本**：arXiv v3，2024
- **原文**：`2401.09670v3.pdf`
**页码说明**：下文 `PDF p.N` 按所给 PDF 文件从首页起计数。

## 1. 研究问题

传统 LLM 服务系统把 Prefill 和 Decode 放在同一组 GPU 上执行，会同时产生：

1. **计算干扰**：长 Prefill 阻塞 Decode，使 TPOT 上升；Decode 也会拖慢 Prefill。
2. **资源耦合**：两阶段被迫共享 GPU 数和并行策略，但计算特征及 SLO 目标不同。

DistServe 的目标不是单纯提高 token throughput，而是在 TTFT、TPOT 和 SLO 达标率约束下，
最大化每块 GPU 能承载的请求率，即 per-GPU goodput。（PDF p.1-3）

## 2. 为什么 Prefill 和 Decode 应分离

### Prefill

- 一次处理整个 prompt，长输入下通常计算密集。
- 单个长请求就可能使 GPU 计算饱和；继续增大 batch 只会增加 TTFT。
- 严格 TTFT 往往偏好能降低单次执行时间的 intra-op/TP。

### Decode

- 每轮只生成一个 token，却反复读取权重和 KV cache，通常受显存带宽限制。
- 需要较大 batch 才能提高 GPU 利用率。
- TPOT 达标后，inter-op/PP 更适合扩大整体 rate capacity。

因此，两阶段不应强制使用相同 batch、并行度、副本数和资源比例。（PDF p.3-6）

## 3. 系统结构

```text
请求
  -> Prefill 队列与实例
  -> 首 token + KV cache
  -> KV cache 传输
  -> Decode 队列与实例
  -> 多轮 token 生成
```

Prefill 与 Decode 实例分别保存模型权重，可采用不同的 GPU 数、TP、PP、副本数和 batch 策略。
其代价是权重副本增加，以及阶段间必须传输 KV cache。（PDF p.2、p.4）

## 4. 配置与放置算法

DistServe 输入模型、workload、request rate、SLO、GPU 显存与网络条件，搜索：

- Prefill/Decode 各自的 intra-op、inter-op 配置；
- 两类实例的副本数；
- Prefill 与 Decode segment 的物理放置。

若跨节点带宽高，两阶段可以相对独立地选择最优配置。若跨节点带宽有限，论文按 PP stage 切分
实例，把 Prefill 与 Decode 中负责相同层的 segment 放进同一节点，使 KV cache 尽量经 NVLink
传输。该设计说明 PD 分离收益不能脱离 topology 讨论。（PDF p.6-8）

## 5. 在线调度

- 新请求发送给 Prefill 队列较短的实例。
- Prefill 完成后匹配负载较低的 Decode 实例。
- Decode 主动拉取 KV cache；流量突发时，Prefill GPU 可暂存 KV cache，避免 Decode 显存瞬时溢出。
- 系统监测到达率和长度分布，workload 显著变化时重新运行 placement 搜索。（PDF p.8-9）

## 6. 实验设置

- 4 个节点，共 32 张 A100 80GB；每节点 8 GPU，经 NVLink 连接。
- 跨节点带宽为 25 Gbps。
- 模型：OPT-13B、66B、175B，FP16、MHA。
- Workload：ShareGPT 聊天、HumanEval 代码补全、LongBench 摘要。
- 数据集没有时间戳，到达间隔由泊松分布生成。
- 比较对象：vLLM 与 DeepSpeed-MII。
- 主要目标：90% 请求同时满足 TTFT 与 TPOT。（PDF p.9-10）

## 7. 评价指标与主要结果

```text
Per-GPU Goodput
= 同时满足 TTFT、TPOT SLO 的最大请求速率 / GPU 数量
```

- Chatbot 相对 vLLM 可承受 2.0-4.6 倍更高请求率。（PDF p.10）
- Code completion 相对 vLLM 提高 5.7 倍请求率。（PDF p.11）
- Summarization 相对 vLLM 提高 4.3 倍请求率，并可承受 12.6 倍更严格的 SLO。（PDF p.11）
- 相对 DeepSpeed-MII，部分场景请求率最高提高 7.4 倍。（PDF p.10-11）
- 超过 95% 请求的 KV cache 传输延迟低于 30 ms；该结果依赖带宽感知放置。（PDF p.11）
- 内置 placement simulator 对 SLO attainment 的预测误差低于 2%。（PDF p.12）

## 8. 对 SimInfer 的直接启发

SimInfer 应把一次请求显式建模为：

```text
Prefill 排队
+ Prefill 执行
+ KV cache 等待/传输
+ Decode 排队
+ 多轮 Decode 执行
```

每条 PD 通信边至少记录请求 ID、两端实例与 GPU、model stage、KV 字节量、开始/完成时间、
topology、是否被计算覆盖，以及拥塞引入的等待。实验变量应同时覆盖 workload、PD 资源比例、
两阶段 TP/PP/batch 和网络放置。

## 9. 与 SimInfer 目标的差异

DistServe 尚未系统覆盖：

- MoE 专家路由与负载偏斜；
- EP dispatch/combine AllToAll；
- PD KV 流与 EP/TP 流共享网络时的竞争；
- 分组级 RDMA/ns-3 仿真；
- 网络模型误差向 P95/P99 的传播。

SimInfer 可把 DistServe 的 PD 生命周期作为上层模型，再插入动态 MoE 路由、EP 流量矩阵和
网络完成事件。

## 10. 不能直接套用的假设与局限

- KV 传输很小的结论依赖对应 PP stage 同节点放置，不能泛化为“PD 通信总可忽略”。
- 到达过程为合成泊松分布，SLO 由作者按应用人工设置，并非公开生产真值。
- 在线调度以 FCFS 为主，不支持抢占，长请求可能阻塞短请求。
- GPU 很少、只有单卡或可选 placement 很少时，PD 分离的优化空间有限。（PDF p.12-13）
- 离线且只关注总吞吐的任务中，混合批处理可能更合适。（PDF p.12-13）
- 长上下文会放大 KV cache 传输和内存压力，论文没有穷尽这一场景。（PDF p.13）

## 11. 组会一句话总结

DistServe 证明 Prefill 和 Decode 应按各自计算特征及 TTFT/TPOT 目标独立配置；但分离收益取决于
KV cache 传输和 topology-aware placement，通信成本不能被当作固定常数。
