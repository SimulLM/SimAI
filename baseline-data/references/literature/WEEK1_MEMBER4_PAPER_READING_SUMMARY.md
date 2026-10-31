# 成员四：四篇核心论文阅读总结

## 1. 阅读顺序

本组论文按以下顺序阅读：

1. **Vidur**：先建立“LLM 推理模拟器应该模拟什么”的总体框架。
2. **DistServe**：在请求级框架中展开 Prefill/Decode 分离、SLO 与 KV cache 传输。
3. **vLLM/PagedAttention**：继续深入 Decode 批处理背后的 KV cache 内存和请求状态。
4. **Clockwork**：最后回到更一般的方法论，理解画像预测、主动调度与尾时延控制。

四份独立阅读卡：

- [Vidur 阅读卡](paper_reading/01_VIDUR_READING_CARD.md)
- [DistServe 阅读卡](paper_reading/02_DISTSERVE_READING_CARD.md)
- [vLLM / PagedAttention 阅读卡](paper_reading/03_VLLM_PAGEDATTENTION_READING_CARD.md)
- [Clockwork 阅读卡](paper_reading/04_CLOCKWORK_READING_CARD.md)

## 2. 为什么从 Vidur 开始

Vidur 给出了最接近 SimInfer 的总体骨架：用少量真实画像建立 runtime estimator，再由事件驱动
模拟器推进请求到达、组批、KV cache、调度与模型执行，最终输出 TTFT、TBT、端到端延迟和资源
利用率。它回答的是：**如何在不遍历真实 GPU 配置的情况下评估 LLM 服务性能？**

对项目而言，Vidur 不是一篇普通参考论文，而是当前代码中的上层请求级基础。项目现有数据流可
理解为：

```text
Workload / request generator
  -> Vidur 事件与调度
  -> ExecutionTimePredictor
  -> AICB 或 SimAI 通信后端
  -> 请求级指标
```

但 Vidur 的通信主要覆盖 TP all-reduce/all-gather 与 PP send-recv，未解决 MoE 的 EP AllToAll、
动态专家偏斜和网络拥塞。因此它同时界定了项目的复用面与增量面：请求/调度框架尽量复用，通信
与 MoE 行为重点扩展。

## 3. 从 Vidur 到 DistServe：把 LLM 请求拆成两个不同阶段

Vidur 已经能表示 Prefill、Decode 与请求级指标，但 DistServe 进一步解释了为什么两阶段必须被
分别观察：

- Prefill 处理整个 prompt，通常更偏计算受限，核心体验指标是 TTFT。
- Decode 每轮生成一个 token，通常更偏显存带宽受限，核心体验指标是 TPOT/TBT。
- 两者共置时会相互干扰，并被迫共享同一资源和并行策略。

DistServe 因此把请求生命周期改写为：

```text
请求到达
  -> Prefill 排队与执行
  -> KV cache 传输
  -> Decode 排队与多轮执行
  -> 结果完成
```

这对 SimInfer 有两层意义。

第一，项目不能只输出单一 E2E latency。TTFT 与 TPOT/TBT 必须分别保存，配置搜索也应使用同时
满足双 SLO 的 per-GPU goodput。

第二，PD 分离引入了真实的网络依赖边。KV cache 的字节量、两端 placement、节点内/跨节点路径、
开始和完成时间、与计算重叠程度都必须进入事件图。DistServe 的实验说明合理放置可以让传输开销
很小，但也恰好说明这一结论依赖 topology，不能用固定常数代替网络模型。

## 4. 从 DistServe 到 vLLM：解释 Decode 为什么受 KV cache 制约

DistServe 告诉我们 Decode 需要大 batch 才能利用 GPU，并在 PD 之间传输 KV cache；vLLM 进一步
回答：**这些请求为什么能或不能同时进入 batch？**

关键约束并不只是算力，而是显存中的动态 KV cache。若系统为最大输出长度预留连续空间，碎片和
保留空间会大幅压缩并发请求数。PagedAttention 以分页、按需分配和 copy-on-write 提升内存利用率，
从而间接改变 batch、queueing、throughput 和 latency。

因此，SimInfer 中的请求状态不能只有 `arrival_time/input_len/output_len`，至少还要随每轮 Decode
更新：

- 当前 context 和 generated token 数；
- KV block 占用与可用显存；
- shared prefix / 多 sequence 的引用关系；
- 当前 batch composition；
- 抢占后的 swap 或 recompute 状态。

这也补充了 DistServe：PD KV 传输量不是只由模型规格决定，还取决于当时请求的 context、KV 格式、
并行切分和内存布局。

## 5. 从 vLLM 到 Clockwork：从机制回到可信预测

前三篇分别给出模拟器骨架、PD 架构和 KV 内存机制，但仍有一个基础问题：画像得到的时间是否能
支撑调度与 SLO 结论？Clockwork 提供了方法论答案：

1. 先让底层操作尽可能可预测；
2. 集中性能关键选择，避免隐式缓存或本地 best-effort 行为引入未知状态；
3. 用保守执行时间预测提前决定调度、合批或拒绝；
4. 同时记录预测值、实测值和误差分布；
5. 以 tail latency、SLO attainment 和 goodput 评价系统。

Clockwork 面向传统固定形状 DNN，不能直接套用于自回归 LLM。但它为 SimInfer 的“高保真”给出
了可操作定义：高保真不是功能多，也不是某一次曲线相近，而是每一层都有可追溯参考、预测误差，
并能说明误差如何传递到请求级尾时延。

## 6. 四篇论文之间的关系

| 论文 | 回答的问题 | 为下一篇留下的问题 |
|---|---|---|
| Vidur | 如何用画像、预测器和事件仿真评估 LLM 服务？ | Prefill/Decode 是否应共用资源与目标？ |
| DistServe | 为什么分离 PD，如何搜索资源并处理 KV 传输？ | Decode 的 batch 与 KV 容量由什么决定？ |
| vLLM | 如何管理动态 KV cache，使更多请求进入 batch？ | 这些运行时间能否可信地支撑 SLO 调度？ |
| Clockwork | 如何从可预测底层建立主动 SLO 调度和误差验证？ | 如何扩展到 LLM 多阶段、MoE 与动态网络？ |

可以把四篇论文合成一条逻辑链：

```text
Clockwork：可测操作 + 预测误差 + SLO 方法论
       ↓
Vidur：LLM 请求级离散事件框架
       ↓
vLLM：iteration batching + 动态 KV 内存状态
       ↓
DistServe：PD 独立资源 + KV 网络依赖
       ↓
SimInfer：加入 MoE EP AllToAll、偏斜流量矩阵与网络拥塞闭环
```

这里按“阅读顺序”从 Vidur 展开最容易理解项目结构；按“实现依赖”看，则是 Clockwork 的校准原则
支撑 Vidur，Vidur 承载 vLLM/DistServe 的状态与策略，SimAI/ns-3 再补足通信执行。

## 7. 与 SimInfer 各层的对应关系

| SimInfer 层次 | 主要论文依据 | 项目需要保留的状态或能力 |
|---|---|---|
| Workload | Vidur | arrival、input/output length、trace/hash、MoE routing mode/seed |
| Request scheduler | Vidur、vLLM | 请求状态、iteration、batch composition、queueing、preemption |
| KV memory | vLLM | block 占用、显存预算、共享、swap/recompute |
| PD architecture | DistServe | Prefill/Decode 实例、TP/PP/副本、placement、KV transfer |
| Execution prediction | Vidur、Clockwork | 算子特征、画像版本、预测分位数、planned/actual time |
| Collective flow | Vidur、SimAI 增量 | TP/PP/EP group、collective、src-dst bytes、依赖与 overlap |
| Packet/network | 项目主要增量 | topology、路由、链路利用率、queueing、RDMA 完成时间 |
| Validation | 四篇共同依据 | TTFT、TPOT/TBT、E2E、P95/P99、SLO attainment、goodput、误差 |

## 8. 项目最关键的研究增量

四篇论文已经较充分覆盖请求调度、KV cache、PD 分离以及画像式模拟，但它们之间仍留下一个共同
空缺：**MoE 路由偏斜如何通过 EP AllToAll 与共享网络传播到请求级尾时延。**

SimInfer 应形成以下闭环：

```text
请求与 Prefill/Decode 状态
  -> 每层 MoE router 产生 expert assignment
  -> expert placement 聚合为 source-destination bytes matrix
  -> SimCCL/Astra-Sim 生成 AllToAll flows
  -> analytical 或 ns-3 计算通信完成时间
  -> 完成时间回写 Vidur 事件队列
  -> 改变 batch、排队、TTFT、TPOT/TBT 与 goodput
```

重点不只是“支持 AllToAll”这个通信类型，而是保留非均匀矩阵。总字节相同的 uniform、hotspot、
long-tail 输入可能产生不同的 destination-rank 和 hottest-link 负载；如果只向后端传一个平均字节数，
就无法研究偏斜。

## 9. 统一评价指标

### 请求体验

- TTFT：Prefill 与首次返回延迟。
- TPOT/TBT：Decode 的平均或逐 token 间隔分布。
- E2E latency：完整请求完成时间。
- P50/P95/P99 与 SLO attainment。

### 系统效率

- throughput 与满足 SLO 的 goodput。
- batch size、queueing delay、GPU busy/idle、KV cache utilization。
- 每 GPU 的请求率与单位成本。

### MoE 与网络

- Expert/rank 的 max-to-mean、CV、Gini、Top 10% share。
- EP dispatch/combine makespan 与 exposed communication ratio。
- Hottest-link utilization、network queueing P95/P99。
- Analytical 与 ns-3 的绝对/相对误差和运行成本。

### 可信度

- 画像/参考来源、输入 hash、Git/submodule SHA、硬件与 topology。
- planned 与 simulated/actual 时间。
- 执行、通信、请求端到端三个层次的误差。

## 10. 不能混用或过度推广的结论

- Vidur 的低误差是特定模型、硬件、workload 和负载区间的结果，不是所有场景保证。
- DistServe 的低 KV 传输开销依赖 bandwidth-aware placement，不代表 PD 传输可忽略。
- vLLM 的 block size 16 是工程默认值，不是通用最优解。
- Clockwork 的可预测性建立在资源控制之上，共享网络和 MoE 热点需要重新校准。
- Throughput 只表示完成速率；goodput 还要求满足 SLO。
- TPOT 是请求内平均值，TBT 可保留逐 token 分布，两者不能只换名字。
- GPU kernel overlap 不等于 RDMA 已完成，网络传输必须有独立完成事件。
- DeepSeek 公开 trace 是均衡路由的行为参考，不能作为偏斜 MoE 或端到端 SLO 的真实真值。

## 11. 对后续实现的建议顺序

1. 按 Clockwork/Vidur 方法记录画像分位数和预测误差。
2. 在 Vidur 中固定请求、iteration 和 KV 状态机。
3. 复现 vLLM 风格的 KV 增长、batch composition 与抢占行为。
4. 增加 DistServe 风格的 PD 实例、placement 和 KV 传输依赖。
5. 定义版本化 MoE expert assignment 与 source-destination matrix schema。
6. 将固定 EP AllToAll 矩阵贯通 SimCCL/Astra-Sim analytical 后端。
7. 对少量代表配置调用 ns-3，校准并缓存网络结果。
8. 在 uniform、hotspot、long-tail 输入下测量网络差异如何传播到 TTFT/TPOT/P99。

## 12. 总结

Vidur 决定了模拟器的上层骨架，DistServe 补充 PD 分离和 KV 网络依赖，vLLM 补充动态 KV 内存与
iteration batching，Clockwork提供可预测执行和 SLO 校准方法。SimInfer 的合理定位不是替代这些
系统，而是把它们连接起来，并补上 MoE EP AllToAll、专家偏斜和分组级网络竞争到请求级指标的
高保真反馈路径。
