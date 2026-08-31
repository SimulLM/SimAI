# 二次开发计划

## 计划状态

这是初始计划模板与治理 Backlog，用于区分已确认目标和仍需设计评审的实现细节。本文件不会创建远程 Issue。

## Goals（目标）

- 建设可复现、高保真的 LLM 推理仿真基础。
- 建设覆盖请求、计算、通信、网络、调度和校准六个层次的高精度预测能力。
- 建模请求级调度、PD 分离、MoE 动态专家负载及其通信影响。
- 以 ns-3 进行校准的分组级通信评估，而非让每个请求都单独启动 ns-3。
- 输出可解释的 TTFT、TPOT、端到端时延、吞吐、资源和通信指标。

## Scope（范围）

### In Scope（范围内）

- 仓库治理、可复现性、基线测试和上游同步纪律。
- 版本化推理工作负载/任务图契约。
- EP AllToAll、PD 资源与 KV 传输、MoE 负载矩阵建模。
- 使用明确来源的真实或可信画像数据进行校准。
- 第一阶段以 DeepSeek 公开的 V3/R1 `profile-data` trace 作为计算—通信重叠的行为校准参考；它不是端到端服务真值。

### Out of Scope（范围外）

- 整体替换 SimAI、ns-3、AICB 或 Vidur。
- 修改 NCCL、CUDA、RDMA 或 GPU kernel 实现。
- 没有可复现校准数据时宣称生产级精度。
- TODO：确认 Web UI、托管服务或公开 benchmark 平台是否属于后续阶段。

## Milestones（里程碑）

| 里程碑 | 产出 | 退出标准 |
|---|---|---|
| M1 环境与基线 | 可复现 Fork、文档、CI 冒烟、基线记录与校准清单 | Linux CI 通过，固定输入/输出基线与 trace 元数据已记录 |
| M2 通信集成 | EP AllToAll 的版本化输入输出路径 | 固定矩阵产生可复现 FlowModel 与时延 |
| M3 DAG 与 PD 调度 | 支持依赖、重叠策略、PD 资源分离、KV 传输 | TTFT/TPOT 变化可由关键路径解释 |
| M4 MoE 负载建模 | 均匀、参数化偏斜、trace 驱动矩阵 | 相同 token 数在不同偏斜下有可解释差异 |
| M5 验证与演示 | 校准套件、回归矩阵、实验报告 | 每个场景报告误差、运行成本、适用边界与局限 |

## Feature Backlog（功能待办）

| 优先级 | 功能 | 状态 |
|---|---|---|
| P0 | DeepSeek V3/R1 profile trace 的解析与计算—通信重叠校准 | 计划中 |
| P0 | 基线构建/测试矩阵与可复现实验清单 | 计划中 |
| P0 | 版本化通信请求/结果契约 | 计划中 |
| P0 | EP dispatch/combine AllToAll 到网络结果的桥接 | 计划中 |
| P1 | 推理 DAG 编译器与资源感知重叠 | 计划中 |
| P1 | PD KV 传输与网络竞争建模 | 计划中 |
| P2 | MoE 专家负载矩阵与 trace 导入 | 计划中 |
| P2 | 校准数据、误差报告、参数扫描 | 计划中 |
| P3 | 更丰富的可视化与实验工具 | TODO：产品决策 |

## Implementation Order（实施顺序）

1. 固化基线：记录编译器、Python、子模块 SHA、拓扑/配置哈希与预期冒烟输出。
2. 修改生产者或消费者前，先设计并评审工作负载/DAG/通信 schema。
3. 以固定矩阵和确定性测试实现 EP AllToAll 纵向切片。
4. 完善缓存键与并发安全结果处理。
5. 增加 DAG 调度和 PD KV 传输节点。
6. 解析 DeepSeek 公开 profile trace，先校验关键事件顺序、重叠比例和等待关系。
7. 增加 MoE 偏斜/trace 模型，再做端到端校准与实验扫描。

## Testing Strategy（测试策略）

- 单元：配置校验、流量矩阵、缓存键、DAG 依赖、PD 计数。
- 集成：AICB 工作负载 → SimCCL/Astra-Sim flow → 后端结果 → Vidur 指标。
- 回归：固定种子和小拓扑，至少一个 AllReduce 与一个 AllToAll。
- 校准：记录输入数据、硬件/拓扑元数据、误差指标与排除项；对 DeepSeek profile-data 只比较事件顺序、持续时间占比和计算—通信重叠，不将其误作端到端 TTFT/TPOT 真值。
- CI：每个 PR 执行快速 Linux 检查；环境固定后再运行耗时 ns-3/GPU 测试。

## Risks（风险）

- 跨仓库 API 漂移及生成的 ns-3 构建目录。
- 包含 ns-3 的分发存在 GPL-2.0 义务，见 [UPSTREAM.md](../UPSTREAM.md)。
- 过多 ns-3 进程启动会破坏仿真性能结论。
- 硬件/画像数据可能缺失或不可比；没有来源不得插值宣称精度。
- DeepSeek 公开 trace 使用均衡 MoE 路由，且不等同于完整服务压测；MoE 偏斜和端到端尾时延仍需单独校准。
- AIOB 的真实画像需要 GPU；但 M1/M2 的解析模式、SimCCL、Vidur 和小规模 ns-3 基线不依赖租用 GPU。多节点 GPU/RDMA 资源仅在端到端网络校准方案成熟后按需申请。
- TODO：M2 前确认受支持的 GPU/CUDA 与集群访问矩阵。

## 建议的首批 Issues

1. `chore: record Linux baseline and repair/verify container path assumptions`
2. `test: add deterministic SimCCL AllReduce/AllToAll smoke coverage`
3. `design: define versioned inference workload, DAG, and communication-result schemas`
4. `feat: bridge fixed EP AllToAll matrix from Vidur to SimAI backend`
5. `feat: model PD KV-transfer as an explicit task`
6. `feat: add configurable MoE load-skew generator`
7. `test: establish calibration dataset manifest and error-report template`
8. `design: ingest DeepSeek profile-data and define overlap-calibration metrics`

## 四人分工建议

| 方向 | 主要范围 |
|---|---|
| 核心/通信 | schema、SimCCL/Astra-Sim 桥接、ns-3 结果适配 |
| 调度 | DAG、PD、重叠、KV 传输资源 |
| 工作负载 | AICB 画像集成与 MoE 负载矩阵 |
| 验证 | CI、测试数据、校准、报告、发布检查 |
