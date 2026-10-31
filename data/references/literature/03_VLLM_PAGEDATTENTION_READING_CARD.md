# vLLM / PagedAttention 阅读卡

- **论文**：*Efficient Memory Management for Large Language Model Serving with PagedAttention*
- **作者**：Woosuk Kwon 等
- **会议**：SOSP 2023
- **原文**：`2309.06180v1.pdf`
**页码说明**：下文 `PDF p.N` 按所给 PDF 文件从首页起计数。

## 1. 研究问题

LLM 的 Decode 会为每个请求维护不断增长的 KV cache。已有系统通常按最大序列长度预留连续
显存，不仅产生内部/外部碎片，还让尚未使用的保留空间长期占用显存。论文画像中，真正保存
token state 的空间只占 KV cache 区域的 20.4%-38.2%，导致可同时进入 batch 的请求数受限。
（PDF p.1-4）

论文要解决的是：如何在不改变模型语义的前提下接近零浪费地管理 KV cache，并让更多请求并行，
提高 LLM serving throughput？

## 2. 三类显存浪费

1. **Reserved space**：输出长度事先未知，却为最大输出预留空间。
2. **Internal fragmentation**：请求结束后，预留块内从未使用的槽位成为浪费。
3. **External fragmentation**：不同连续内存块之间留下难以利用的空洞。

此外，并行采样、beam search 和共享前缀会产生相同 KV 内容；连续布局让这些内容难以共享。
（PDF p.2-4）

## 3. PagedAttention

PagedAttention 借鉴操作系统分页，把序列的 KV cache 划分为固定 token 数的逻辑块，并允许这些
块存放在不连续的物理显存中。Block table 保存逻辑块到物理块的映射，attention kernel 在计算时
按映射读取对应 K/V。（PDF p.5-6）

```text
Sequence logical KV blocks
  -> block table
  -> non-contiguous physical KV blocks
  -> PagedAttention kernel
```

新 token 到来时，仅当最后一个逻辑块已满才分配新物理块。因此一个请求的内部浪费最多限制在
最后一个未填满块，无需为最大序列长度提前保留整段空间。（PDF p.6-7）

## 4. vLLM 系统设计

- 中央 scheduler 每轮选择可运行 sequence，决定 batch，并向 GPU worker 下发 token ID 与
  block table。（PDF p.5、p.9）
- KV cache manager 管理 GPU/CPU 物理块、逻辑映射和引用计数。
- 内存不足时，scheduler 可抢占请求，选择 swap 或 recompute KV cache。（PDF p.8-9）
- 分布式模型执行使用 tensor parallel，worker 间以 all-reduce 同步中间结果。（PDF p.9）
- 自定义 CUDA kernel 融合 block write、block read + attention 以及非连续 block copy。
  （PDF p.9）

## 5. 复杂解码中的 KV 共享

### Parallel sampling

多个输出共享相同 prompt 的 KV block。只有某个 sequence 修改共享块时才进行 block-level
copy-on-write。（PDF p.7）

### Beam search

不同 beam candidate 的大部分历史 KV block 可以共享；只有分叉并写入旧共享块时复制一个块，
避免频繁复制完整 KV cache。（PDF p.7-8）

### Shared prefix

系统可以缓存公共前缀对应的物理块，新请求直接映射这些块，只计算请求独有的后缀。
（PDF p.8）

## 6. 实验设置

- 模型：OPT-13B/66B/175B 与 LLaMA-13B。
- GPU：NVIDIA A100；大模型使用多 GPU tensor parallel。
- Workload：ShareGPT 与 Alpaca 的真实 input/output length 分布。
- 数据集没有到达时间，作者以不同 request rate 的泊松过程合成到达。
- 基线：FasterTransformer、Orca (Max/Pow2/Oracle)。
- 主指标：normalized latency，即请求端到端 latency 除以 output length；观察请求率升高时
  latency 曲线何时爆炸。（PDF p.10）

## 7. 主要结果

- 总体上，在相近 latency 下相对 FasterTransformer/Orca 获得 2-4 倍 throughput。
  （PDF p.1、p.14）
- ShareGPT 基础采样中，相对知道真实输出长度的 Orca (Oracle)，vLLM 可承受 1.7-2.7 倍更高
  request rate。（PDF p.11）
- 共享更多 few-shot 示例时，相对 Orca (Oracle) 的 throughput 最高提升 3.58 倍。（PDF p.12）
- PagedAttention 动态块映射使 attention kernel latency 增加 20%-26%，但端到端内存与 batch
  收益更大。（PDF p.12）
- Block 太小会降低 kernel 并行效率，太大增加碎片；实验默认 block size 为 16。（PDF p.12）

## 8. 对 SimInfer 的直接启发

KV cache 必须成为请求状态机的一部分，而不是固定模型参数。每轮 Decode 后至少更新：

- 请求的 prompt/generated token 数；
- 逻辑/物理 KV block 数与剩余槽位；
- batch composition 与可用显存；
- shared prefix / sequence 引用关系；
- 是否抢占，以及 swap/recompute 的额外时间。

SimInfer 还应以 iteration 为调度粒度，因为新 Prefill 与已有 Decode 如何交错会改变 batch、KV
占用、计算输入形状和通信时间。内存策略会通过并发度与排队产生二阶性能影响。

## 9. 与 SimInfer 目标的差异

vLLM 是真实 serving engine，不是仿真框架。论文主要研究 KV cache 内存和请求调度，并未提供：

- 少量画像到未测 batch/context 组合的完整预测方法；
- 网络 topology、链路排队和 packet/RDMA 级解释；
- MoE 专家路由、EP dispatch/combine AllToAll；
- PD 分离下的 KV cache 跨实例传输。

其分布式通信重点是 TP all-reduce。SimInfer 需要在 vLLM 请求/KV 状态机外再接入 DistServe 的
PD 边以及 MoE EP 通信。

## 10. 不能直接套用的假设与局限

- Orca 未开源，论文中的 Orca 是作者复现；Oracle 还假设提前知道真实输出长度。
- 请求到达为合成泊松过程，不能覆盖所有突发和相关到达。
- normalized latency 适合观察容量拐点，却会混合 TTFT 与 Decode 体验；SimInfer 应分别保存
  TTFT、TPOT/TBT 和 E2E。
- 默认 block size 16 是特定模型、kernel 与 workload 下的工程选择，不应硬编码进通用模拟器。
- Kernel 额外开销必须随硬件和实现重新画像，不能只复用论文比例。

## 11. 组会一句话总结

vLLM 通过分页、按需分配和 copy-on-write 显著提升 KV cache 利用率；对 SimInfer 而言，关键是
让请求生命周期、KV 内存和 iteration-level batching 共同演化，而不是只回放固定算子时长。
