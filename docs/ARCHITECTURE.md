# 系统架构

## 组件关系

```text
AICB / AIOB（工作负载、画像）
          |
          v
Astra-Sim（Sys、Workload、Layer、集合通信调度）
     |                         |
     v                         v
SimCCL（FlowModel）        解析后端（busbw 估计）
     |
     v
ns-3 / 物理后端（分组或 RDMA 执行）

Vidur（请求事件模型） -> 执行时间预测器 -> AICB / SimAI / Vidur 模型
```

## 核心执行路径

### SimAI 解析模式

`network_frontend/analytical/AnalyticalAstra.cc` 解析 `UserParam`，创建 `AnalyticalNetWork` 与 `AstraSim::Sys`，触发工作负载，再运行 `AnaSim`。`Layer.cc` 通过 bus-bandwidth 模型计算通信时间，并向 `results/` 写入结果。

### SimAI ns-3 模式

顶层 `scripts/build.sh` 将 `ns-3-alibabacloud` 子模块复制到 Astra-Sim 生成的网络后端目录，然后调用 Astra-Sim ns-3 构建。SimCCL FlowModel 向 ns-3 前端传递集合算法/协议信息。`AS_SEND_LAT` 可覆盖表格导出的发送延迟，详见 `docs/configuration/env-variables.md`。

### 多请求推理模式

`vidur/main.py` 构建 `SimulationConfig`；`Simulator` 创建请求并按优先级处理事件。全局与副本调度器选择批次和阶段；`BaseExecutionTimePredictor` 返回计算、TP、PP 及后端推导时间；`MetricsStore` 输出请求指标和可选 Chrome/JSON trace。

## 接口边界

| 边界 | 当前接口 | 维护规则 |
|---|---|---|
| AICB → 仿真器 | CSV/文本工作负载与画像 | 新增字段前先版本化 schema |
| Astra-Sim → SimCCL | mock NCCL 头文件/FlowModel | 明确保持 mock 版本兼容（`SIMAI_NCCL_VERSION`） |
| SimCCL → ns-3 | flow 元数据与前端发送操作 | 不修改复制生成的 ns-3 文件 |
| Vidur → SimAI | 子进程命令、工作负载文件、结果 CSV | 逐步替换为版本化通信结果契约 |
| Vidur → 使用者 | 指标 CSV 与可选 trace | 将输出 schema 视为公开实验接口 |

## 目标架构方向

计划引入版本化推理任务图：节点表示计算、TP 通信、EP dispatch/combine AllToAll、PP 传输与 PD KV 传输；边表示数据和资源依赖。通信请求应包含组成员、拓扑标识、张量 dtype，以及可选的源-目的字节矩阵。ns-3 结果应返回延迟和队列/传输分解，并以完整实验输入作为缓存键。

这是已确认的架构方向，尚非已实现代码。实施顺序与验收标准见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)。
