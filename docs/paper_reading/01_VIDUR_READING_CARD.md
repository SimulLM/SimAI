# Vidur 阅读卡

- **论文**：*Vidur: A Large-Scale Simulation Framework for LLM Inference*
- **作者**：Amey Agrawal 等
- **会议**：MLSys 2024
- **原文**：`2405.05465v2.pdf`
**页码说明**：下文 `PDF p.N` 按所给 PDF 文件从首页起计数。

## 1. 研究问题

部署 LLM 推理服务需要同时选择 GPU 型号、TP/PP 并行度、副本数、调度策略、批量大小和
调度器专用参数。最佳配置还会随模型以及请求的输入/输出长度分布变化。若在真实 GPU 上遍历
配置空间，成本和耗时都难以接受。

Vidur 要解决的问题是：能否只做少量算子画像，就高保真地预测不同模型、硬件、工作负载和
调度策略下的端到端推理性能，并进一步搜索满足 SLO 的低成本配置？（PDF p.1-3）

## 2. 为什么 LLM 推理难以模拟

论文归纳出三项核心困难：（PDF p.2-4）

1. **时间粒度细**：训练迭代通常持续数百毫秒，而一次 Decode 迭代可能只有数毫秒。
2. **迭代形状不断变化**：每轮 batch 中请求的 context、Prefill token 和 Decode token 数不同，
   Prefill/Decode 的交错又受调度器影响。
3. **误差会级联**：某一轮执行时间预测偏差会改变后续请求到达、组批和排队状态，临近容量点时
   小误差可能演化成很大的端到端误差。

因此，简单的“固定每 token 时间 × token 数”或完整 trace replay 都不足以覆盖配置搜索。

## 3. 核心架构

```text
模型规格
  -> Profiler：选取并测量少量代表性算子输入
  -> Runtime Estimator：预测未画像输入，生成运行时查找表

工作负载 + 部署配置 + 调度器
  -> 事件驱动 Simulator
  -> 请求级、Replica 级、硬件级指标
  -> Vidur-Search 配置搜索
```

系统分为两个阶段：（PDF p.5）

- **模型接入阶段**：根据模型规格生成待画像算子，收集少量测量点并训练预测模型。
- **仿真阶段**：加载运行时查找表，在不同 workload、并行策略和调度器下推进事件。

## 4. Profiler 与运行时间预测

Vidur 按输入依赖把算子分为三类：（PDF p.5-6）

| 类别 | 主要依赖 | 例子与处理方式 |
|---|---|---|
| Token-level | 当前迭代 token 总数 | GEMM、归一化、激活；画像不同张量形状和 TP 切分 |
| Sequence-level | 各请求 context/prompt 长度 | Attention；Prefill 与 Decode 分开画像 |
| Communication | 传输量与 topology | all-reduce、all-gather、send-recv；模型无关地预画像 |

Attention 的输入组合空间很大，论文利用算子结构压缩画像维度；对于未画像形状，使用随机森林
回归插值。作者认为它比单一解析公式更能表达 CUDA kernel 的 tile/wave quantization，又比大型
神经网络更节省数据。（PDF p.6）

## 5. 调度与工作负载

Vidur 使用三级 hierarchical scheduler：（PDF p.6-7）

1. **Global scheduler**：在副本之间路由请求，支持 round-robin、least outstanding requests
   以及延迟绑定的 stateful routing。
2. **Replica scheduler**：负责 batching、KV cache 预算与请求抢占，可插拔实现 vLLM、Orca、
   FasterTransformer、Sarathi-Serve 等策略。
3. **Replica-stage scheduler**：处理 PP stage 的 micro-batch 调度。

Vidur-Bench 提供 Chat-1M、Arxiv Summarization、Bilingual Web Book 等 workload，覆盖短/长
Prefill、短/长 Decode 和不同 Prefill:Decode 比例。动态 workload 的到达过程使用泊松分布。
（PDF p.7-9）

## 6. 评价指标

| 层级 | 指标 |
|---|---|
| 请求级 | scheduling delay、prefill completion、TTFT、TBT、normalized E2E latency、抢占/重启次数 |
| Replica 级 | batch size、每轮 token 数、busy/idle time、KV cache 与 compute utilization |
| 硬件级 | GPU FLOPs utilization、memory utilization |
| 搜索目标 | 在 TTFT/TBT 等约束下最大化 QPS per dollar |

动态 workload 使用 `端到端延迟 / 输出 token 数` 的 normalized latency；静态 workload 排除
scheduling delay，只比较 execution latency，避免排队掩盖运行时间模型本身的准确度。
（PDF p.7-9）

## 7. 实验设置与主要结果

- 模型覆盖 LLaMA2-7B、InternLM-20B、LLaMA2-70B、Qwen-72B。
- 使用 A100/H100 及不同 TP 配置，在三类 workload 上比较真实 vLLM 与仿真结果。
- 静态 workload 中，P95 execution latency 的最大误差为 3.33%。
- 动态 workload 在容量 85% 的请求率下，几乎所有场景的 normalized E2E latency 误差低于 5%。
- 摘要概括的覆盖范围内，inference latency 误差低于 9%。（PDF p.1、p.8-9）
- 示例 SLO 为 TTFT P90 < 2 s、TBT P99 < 200 ms；Vidur-Search 比较 TP/PP、调度器、GPU
  型号等组合。（PDF p.10）
- LLaMA2-70B 搜索约需 1 小时 CPU；作者估算对应真机遍历需 42K GPU 小时，约 21.8 万美元。
  （PDF p.1-3）

## 8. 对 SimInfer 的直接启发

SimInfer 可以直接继承 Vidur 的上层请求与调度框架，但应保持以下分层：

```text
真实 trace / 微基准
  -> 版本化画像数据
  -> 算子与通信 Runtime Estimator
  -> 请求级事件仿真
  -> TTFT/TBT/E2E/SLO 指标
```

具体可借鉴点：

- 画像、预测器和事件模拟器分别校验，避免把误差来源混在一起。
- 按 token-level、sequence-level、communication 三类依赖设计特征，不使用统一 batch-size 模型。
- 在 75%、85%、95% capacity 等多个负载点验证，区分 execution error 与 queueing error。
- 用同一 run ID 关联请求、batch、rank/link 和仿真成本指标。
- 将 workload hash 与 model/config 一起作为配置搜索和缓存键的一部分。

## 9. 与 SimInfer 目标的差异

Vidur 主要覆盖 TP all-reduce/all-gather 和 PP send-recv，论文没有系统建模：

- MoE Expert Parallel 与动态专家路由；
- EP dispatch/combine AllToAll；
- 专家偏斜产生的源-目的字节矩阵；
- 多条通信流在交换机、队列和 RDMA 协议中的竞争；
- 分组级网络事件与 hottest-link 尾部。

Vidur 对 collective 通信采用按 topology 预画像的 runtime；SimInfer 的主要增量是把需要高保真
分析的通信下沉到 SimCCL/Astra-Sim/ns-3，再把完成时间回写到 Vidur 请求时间线。

## 10. 不能直接套用的假设与局限

- 泊松到达不能代表所有生产环境的突发性、周期性或相关到达。
- 论文结果依赖经过优化的 vLLM 分支和给定 GPU；新硬件、新 kernel 必须重新画像。
- 画像通信时间不等于解释网络拥塞机制，不能直接用于验证 MoE 热点。
- 附录显示在 95% capacity、较小 LLaMA2-7B 场景中误差最高可到 12.65%；“低于 9%”不是
  对所有模型和负载点的无条件保证。（PDF p.14）
- 当前 stage scheduler 的异步通信、sequence parallel 等能力仍有限。（PDF p.6）

## 11. 组会一句话总结

Vidur 证明了“少量算子画像 + 输入感知预测 + 请求级离散事件仿真”可以低成本评估 LLM 服务；
SimInfer 应复用这一上层框架，把创新重点放在 MoE EP AllToAll、动态偏斜与网络拥塞的高保真闭环。
