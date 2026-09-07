# 成员四：第一周工作三——DeepSeek Prefill/Decode Trace 解析

## 技术摘要

本次解析固定使用 DeepSeek 官方 `profile-data` 仓库提交
`449602428a1b023acb8a505d4f34fef536535db6` 的 rank 0 PyTorch Profiler trace。
两份文件的结构、时间字段、GPU kernel 和分布式元数据均通过检查。

- Prefill 使用 H800、TP1、EP32、4K prompt、每卡 16K tokens 和两个 micro-batch。
  在可见 GPU kernel 时间线上，EP dispatch/combine 区间的 85.207% 与已分类计算 kernel
  直接重叠，呈现出 stream 16 通信与 stream 7 计算并行的结构。
- Decode 使用 H800、TP1、EP128、4K prompt、每卡 128 requests 和两个 micro-batch。
  EP 的 `dispatch_ll`/`combine_ll` 大多与计算出现在同一条可见 kernel 时间线上，直接
  kernel 区间重叠仅 0.006%。这不等于网络通信没有重叠：官方说明 Decode 在发出 RDMA
  后释放全部 GPU SM，并在计算结束后等待 AllToAll 完成；trace 没有独立暴露 RDMA
  传输区间，因此不能只用 kernel 条宽度计算端到端通信隐藏率。

这两份 trace 可以校准计算和 EP 通信的事件顺序、kernel 持续时间及 Prefill 的直接
GPU-kernel 重叠；不能作为 TTFT、TPOT、P95/P99、吞吐、真实网络字节量或专家偏斜的绝对真值。

## 数据与配置

| 阶段 | 文件 | SHA-256 | 设备 | 并行配置 | 输入与批量 | 路由 |
|---|---|---|---|---|---|---|
| Prefill | `prefill.json` | `b96f9faf...6433b0ce2` | NVIDIA H800 | TP1、EP32 | 4K prompt；16K tokens/GPU；2 micro-batches | 绝对均衡 |
| Decode | `decode.json` | `6dd02bfb...9ebfb62` | NVIDIA H800 | TP1、EP128 | 4K prompt；128 requests/GPU；2 micro-batches | 绝对均衡 |

原始 trace 只保存在本地 `tmp/deepseek-profile-data/`，不会提交到本仓库；分析结果记录了
官方仓库提交、文件大小和完整 SHA-256，可重新下载后核验。

## 关键事件表

下表中的开始时间相对同一 trace 的首个 GPU kernel；`P50`、`P95` 和累计时间单位均为
微秒。累计时间是各事件持续时间相加，会包含并发；重叠计算使用合并后的区间，不重复计数。

| 阶段 | 事件类别 | 首次开始 | 次数 | P50 | P95 | 累计时间 | stream | 并行/等待关系 |
|---|---|---:|---:|---:|---:|---:|---|---|
| Prefill | EP dispatch layout | 104,906 | 116 | 135.5 | 191 | 16,853 | 16 | dispatch 前置布局 |
| Prefill | EP notify dispatch | 105,093 | 116 | 893.5 | 2,690 | 123,618 | 16 | 99.562% 与计算直接重叠 |
| Prefill | EP dispatch | 107,883 | 116 | 4,560.5 | 4,942 | 532,860 | 16 | 99.365% 与计算直接重叠 |
| Prefill | EP combine | 123,846 | 116 | 8,618 | 10,139 | 1,006,189 | 16 | 84.853% 与计算直接重叠 |
| Prefill | Attention compute | 29,708 | 244 | 1,179.5 | 3,031 | 372,233 | 7 | 94.098% 与 EP kernel 重叠 |
| Prefill | Expert compute | 29,926 | 470 | 646.5 | 3,687 | 764,006 | 7 | 86.756% 与 EP kernel 重叠 |
| Decode | EP dispatch | 6,234 | 235 | 37 | 82 | 11,921 | 7/16 | 可见 kernel 几乎不与计算重叠；RDMA 区间未单列 |
| Decode | EP combine | 8,090 | 235 | 18 | 21 | 5,138 | 7/16 | 可见 kernel 不与计算重叠；RDMA 区间未单列 |
| Decode | Attention compute | 1,922 | 364 | 11 | 243 | 32,217 | 7 | 与 EP kernel 串行可见 |
| Decode | Expert compute | 7,958 | 236 | 56.5 | 81 | 13,599 | 7 | 仅 1 μs 边界重叠 |

完整表位于 `docs/data/deepseek_key_events.csv`。

## Prefill：独立通信 stream 实现显式重叠

Prefill 的可见 GPU 时间窗为 2,120,106 μs。合并区间后：

```text
EP kernel union          = 1,662,667 μs
classified compute union = 1,783,450 μs
direct overlap           = 1,416,701 μs
overlap / EP union       = 85.207%
```

dispatch、notify 和 combine 主要在 stream 16，attention、expert GEMM 等计算主要在
stream 7。两条 stream 的区间交叉是 trace 可直接观察的事实。Combine 的中位持续时间
约 8.618 ms，长于 dispatch 的约 4.561 ms，而且 combine 的直接重叠比例较低
（84.853% 对 99.365%），因此在本 trace 中 combine 更可能留下可见尾部。

注意，这里的事件次数不能直接当作模型层数。官方采用两个 micro-batch，且一个逻辑 MoE
层会产生 dispatch、combine 及其准备事件；应先按相关 ID 或模型层标记关联后再做逐层计数。

## Decode：RDMA 进度不能由 GPU kernel 条直接测量

Decode 的可见 GPU 时间窗为 95,889 μs。EP kernel 合并区间为 17,059 μs，非 EP kernel
合并区间为 69,082 μs，直接相交只有 1 μs。原因不是官方策略没有计算—通信重叠，而是
Decode 的 low-latency AllToAll 在发出 RDMA 后释放 SM；网络进度没有作为独立 GPU kernel
区间存在于 trace 中。

`dispatch_ll` 和 `combine_ll` 都出现 235 次。按时间顺序相邻配对可看到稳定的双调用形状：

| 事件 | 可配对组数 | 第一次调用 P50 | 两次调用间隔 P50 | 第二次调用 P50/P95 | 最大第二次调用 |
|---|---:|---:|---:|---:|---:|
| `dispatch_ll` | 117 | 17 μs | 105 μs | 67/83 μs | 1,603 μs |
| `combine_ll` | 117 | 20 μs | 352 μs | 17/17 μs | 356 μs |

这支持如下**受限推断**：dispatch 两次调用之间存在约 105 μs 的可用于计算的窗口，第二次
dispatch 通常比第一次更长；combine 两次调用间隔更长且第二次通常仍很短，符合“更多通信
被中间计算覆盖”的形状。但 trace 没有 DeepEP 网络完成标记或逐消息关联 ID，因此不能把
第二次调用时长直接命名为纯等待时间，也不能由此计算精确的暴露网络尾部。

## 数据质量

两份 trace 的以下检查均通过：

- `traceEvents` 非空；
- 所有 complete event 均有数值型 `ts` 与 `dur`；
- 没有负持续时间；
- 存在 GPU kernel 事件；
- `distributedInfo` 的 world size 为正，且文件为 rank 0；
- 存在 H800 设备元数据。

Prefill 有 3,368 个、Decode 有 36 个 `cuda_runtime` 事件名为 `INVALID`。这些事件仍有
合法时间和 correlation ID，且本分析的关键统计只使用 `cat=kernel` 的事件，因此没有把它们
判为结构错误；它们也不应被解释成失败的 GPU kernel。

## Trace 阅读卡

### 可以用于校准

- Prefill/Decode 中 attention、expert GEMM、EP dispatch 和 combine 的先后顺序；
- 单个 GPU kernel 的持续时间分布；
- Prefill 跨 stream 的计算—EP kernel 直接重叠；
- Decode 双 micro-batch 调用形状，以及可能出现暴露等待的位置；
- H800、TP1、EP32/EP128 和固定输入规模下的相对时序。

### 不能用于校准

- 请求到达、排队、调度、TTFT、TPOT、P95/P99 时延和吞吐；
- 真实的 AllToAll 字节量、链路利用率、交换机拥塞或 RDMA 完成时间；
- 多 rank 差异和跨节点尾部，因为公开文件只观察 rank 0；
- 专家负载偏斜，因为官方明确使用绝对均衡 MoE 路由；
- 跨硬件、跨 EP 规模或不同 batch 的绝对外推。

### 对 SimInfer 的约束

1. 任务图必须能表达两个 micro-batch 之间的依赖和交叠，不能把 Prefill/Decode 简化为单条串行链。
2. Prefill 至少要区分通信 stream 与计算 stream，并能记录未被计算覆盖的 combine 尾部。
3. Decode 需要把“RDMA 已发出但 GPU SM 空闲”建模为独立网络活动；只模拟 GPU kernel 会漏掉等待。
4. 后续 EP 接口要提供 correlation/message 标识、字节量、发出时间和完成时间，才能计算真实隐藏比例。
5. 校准时应分别比较事件顺序、kernel 时间和网络完成时间，不能用一个总耗时误差掩盖内部错配。

## 复现方法

下载官方数据后，在仓库根目录执行：

```bash
git clone --depth 1 https://github.com/deepseek-ai/profile-data.git tmp/deepseek-profile-data
python scripts/analyze_deepseek_trace.py
```

程序会生成：

- `docs/data/deepseek_trace_analysis.json`：完整元数据、质量检查、区间统计和 Decode 配对观察；
- `docs/data/deepseek_key_events.csv`：可直接纳入实验记录的关键事件表。

## 来源

- DeepSeek 官方数据与配置说明：<https://github.com/deepseek-ai/profile-data>
- 本次固定提交：`449602428a1b023acb8a505d4f34fef536535db6`
- AICB 现有 PyTorch trace 解析入口：`aicb/workload_generator/analysis_pytorch_trace.py`

现有 AICB 解析器只查找 `nodes` 中以 `nccl:` 开头的事件，而官方文件使用
`traceEvents`，且 DeepEP AllToAll 以 `dpsk::ep::internode::*` GPU kernel 呈现；因此不能直接
用该解析器得到本次关键事件表。
