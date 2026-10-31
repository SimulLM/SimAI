# Clockwork 阅读卡

- **论文**：*Serving DNNs like Clockwork: Performance Predictability from the Bottom Up*
- **作者**：Arpan Gujarati 等
- **会议**：OSDI 2020
- **原文**：`osdi20-gujarati.pdf`
**页码说明**：下文 `PDF p.N` 按所给 PDF 文件从首页起计数。

## 1. 研究问题

传统模型服务认为组件时延难以预测，因此使用公平排队、动态缓存、并发线程、自动扩缩等反应式
机制。它们可能改善平均性能，却会把波动传播到排队和上层服务，最终放大 tail latency。

Clockwork 从相反观察出发：固定输入形状的 DNN inference 是确定的数学操作序列，在独占 GPU
上执行时间高度可预测。论文追问能否从这一原子事实出发，构建主动满足请求级 latency SLO 的
分布式 serving system。（PDF p.2-4）

## 2. 核心原则：Consolidating Choice

Clockwork 尽可能减少底层组件在性能关键路径上的自主选择，把缓存、排队、批处理、模型放置和
负载均衡集中给全局 Controller。其逻辑是：选择越分散，内部状态与执行路径越难预测；把选择权
集中后，上层才能用已知状态提前安排资源。（PDF p.5-6）

代价是组件耦合更紧、架构模块化程度下降。论文并不要求绝对确定，而是让可预测执行成为常态，
把少量偏差显式视为错误。（PDF p.5）

## 3. 系统结构

```text
用户请求与 deadline
  -> 中央 Controller
     - 全局队列
     - 模型缓存/放置状态
     - LOAD/INFER 时间预测
     - batching、调度与提前拒绝
  -> Worker
     - 独占一组 GPU
     - 按时间窗口执行 action
```

Controller 为 `LOAD` 和 `INFER` action 指定预计时长及执行窗口。若某请求即使立即执行也会错过
deadline，则提前拒绝；若可以在 deadline 内合批，就等待并批处理。Worker 无法按时执行时立即
中止 action，恢复到后续计划，不做本地 best-effort 补救。（PDF p.5-7）

## 4. 如何建立可预测执行

- Worker 独占 GPU，避免其他进程、OS 调度和并发 kernel 引入随机干扰。
- 模型加载、输入/输出复制、推理分别作为显式 action，禁止隐式状态副作用。
- Controller 维护模型在 RAM/GPU 的位置，不让 worker 自主淘汰缓存。
- GPU 上一次只执行一个 INFER，并与 LOAD 使用受控资源；是否 batching 由 Controller 决定。
- 执行时间预测采用历史测量的保守分位数，并持续比较预计与实际完成时间。
  （PDF p.6-9）

## 5. 调度目标

Clockwork 不是让所有请求都进入系统，而是最大化在 deadline 前完成的 goodput：

- 对可能按时完成的请求做 earliest-deadline-aware 调度与 batching；
- 对不可能完成的请求尽早拒绝，避免无效工作拖累其他请求；
- 对 latency-sensitive 与 batch 用户做性能隔离，在空闲窗口服务后台请求；
- 在 overload、cold start 和 burst 下保持 SLO，而不是让队列无限增长。

## 6. 实验设置

- 真实 worker 主要使用 NVIDIA Tesla V100。
- 模型来自 ONNX Model Zoo 与 GluonCV，包括 ResNet、DenseNet 等多种 DNN。
- 使用泊松合成负载以及 Microsoft Azure Functions 两周 trace 的片段。
- 大规模实验使用 12 个 worker、61 种模型并复制为 4,026 个实例。
- 指标包括 throughput/goodput、latency、tail latency、SLO violation、模型数、隔离性与预测误差。
  （PDF p.10-13、p.20）

## 7. 主要结果

- 摘要报告：支持数千模型时，99.9999% 请求满足 100 ms latency target。（PDF p.2）
- Azure trace 重放 6 小时，平均 9,638 req/s；约 2.08 亿请求中只有 58 次 action timing
  misprediction，且无请求超过 100 ms SLO。（PDF p.12-13）
- `INFER` action 的 99 分位 overprediction/underprediction 分别为 144 μs 和 55 μs。
  （PDF p.13）
- 对 latency-sensitive 与 batch workload，SLO-aware scheduling 能维持前者达标率，同时在空闲
  区间继续服务 batch 请求。（PDF p.12）
- Emulated worker 实验中 goodput 随 worker 数近线性增长；110 worker 时达到 103,387 req/s，
  之后中央 Controller 成为瓶颈。（PDF p.13-14）

## 8. 对 SimInfer 的直接启发

1. **预测值要带误差分布**：画像至少保存 P50/P95/P99、over/underprediction，而非单个均值。
2. **计划与实际分开记录**：事件同时保存 planned start/end 和 simulated/actual start/end。
3. **deadline 是调度输入**：到达时就根据队列、计算、内存和通信状态决定调度或拒绝。
4. **尾部优先**：报告 P95/P99、SLO attainment、rejected requests 和 goodput，不能只看平均值。
5. **误差需要沿事件图追踪**：计算或网络轻微 underprediction 可能改变 batch 与后续排队。

## 9. 与 SimInfer 目标的差异

Clockwork 把一次固定形状 DNN inference 当作原子动作，而 LLM 请求包含 Prefill、不断增长的
KV cache、多轮 Decode 以及 TP/PP/EP 通信。SimInfer 必须把原子动作展开为事件 DAG。

论文还假设 worker 独占机器/GPU，Controller-worker 网络大体可预测；SimInfer 研究的 MoE
AllToAll 拥塞、PD KV 传输和共享网络竞争可能主动破坏这一假设。（PDF p.14）

## 10. 不能直接套用的假设与局限

- 不覆盖 autoregressive LLM、continuous batching、动态 KV cache 和 PD 分离。
- 不覆盖用户自定义 CPU 预处理/后处理。（PDF p.14）
- 原型把 input/output 经过中央 Controller，大规模时会形成网络瓶颈。（PDF p.14）
- 集中调度器在 110 个 emulated worker 后成为吞吐瓶颈。
- 要求对主要瓶颈资源有控制或保证；共享 GPU、不可预测网络下结论需要重新验证。
- 未解决大规模 fault tolerance 和多租户安全隔离。（PDF p.14-15）

## 11. 组会一句话总结

Clockwork 的核心价值不是“所有系统都用中央调度”，而是证明底层可测时，可以用保守预测主动
调度 SLO；SimInfer 应把同一原则扩展到 LLM 的计算、KV、PD 与 EP 网络事件，并显式量化误差。
