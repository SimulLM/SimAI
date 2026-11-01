# 大模型推理 DAG 时间域仿真

基于 [SimAI](https://github.com/aliyun/SimAI) 的大模型推理仿真改造项目。我们计划构建依赖驱动、资源约束的 DAG 执行引擎，统一描述计算、通信和同步时序，并以原模型参考数据、原 SimAI 结果和改造后的结果进行对照，验证预测精度的改善。

**当前处于设计与开发准备阶段。DAG 执行核、PD 和动态 MoE 改造尚待实现，精度提升尚未完成验证。**

## 项目目标

- 接入现有请求调度和推理执行流程，让 DAG 实际控制任务执行和仿真时间推进。
- 显式建模任务依赖、GPU/通信资源竞争以及计算通信重叠。
- 支持 PD 分离中的 KV 传输、接收就绪、容量背压与 Decode 准入。
- 支持 MoE 动态路由、Expert 负载差异、Dispatch/Combine 和同步拖尾。
- 输出任务与请求时间线、资源等待和推理指标，解释预测误差及性能瓶颈。

完整交付流程：

```mermaid
flowchart LR
    W[请求与配置] --> S[调度与组批]
    S --> G[DAG 构图]
    G --> E[依赖与资源约束执行]
    E --> C[事件推进与完成回调]
    C --> M[请求指标与任务时间线]
```

## 当前基础与改造重点

| 部分 | 当前基础 | 改造重点 |
|---|---|---|
| 推理调度 | 请求生成、组批、逐 Token 迭代和 Stage 队列 | 保留策略，将执行边界接入 DAG |
| 时序与依赖 | 离散事件推进、请求 DAG 数据结构、底层集合 flow 依赖 | 接通任务就绪、资源申请、完成释放和后继激活 |
| 计算通信 | 预测器和 Stage 汇总耗时 | 选择性展开计算、通信和同步任务，避免重复计费 |
| PD | P/D 配置、KV 大小估计和静态传输延迟 | KVReady 门控、源缓存保留、目标容量预留及争用 |
| MoE | 层级估时与聚合负载近似 | 动态任务图、Expert 独立耗时和共享资源等待 |
| 数据与验证 | 已归档基准、通信日志、负载数据和分析材料 | 对齐配置与单位，建立独立验证集和误差对照 |

图结构、任务顺序和共享资源是不同概念：依赖边表示必须遵守的先后关系，资源管理器决定就绪任务能否启动。

## 八阶段实施路线

| 阶段 | 主要产出 |
|---|---|
| 1. 定义任务图与执行边界 | 图 schema、接口、支持配置、原 SimAI 误差基线 |
| 2. 实现最小 DAG 执行核 | 依赖跟踪、Ready/事件队列、完成解锁 |
| 3. 加入资源约束 | 计算/通信资源、原子申请释放、等待与并行 |
| 4. 接入现有推理执行链 | 原入口下运行 DAG，保持请求与 Token 状态正确 |
| 5. 拆分计算与通信任务 | 层级计算、TP/PP/EP 通信、分项 cost 和同步 |
| 6. 扩展 PD 分离 | KV 传输、KVReady、源 pin、目标 reserve 与背压 |
| 7. 扩展动态 MoE | 路由、Expert/Group、Dispatch/Combine 与拖尾 |
| 8. 回归、校准与规模优化 | 独立验证集误差、运行开销和可复现交付 |

PD 与 MoE 在共享执行基础完成后并行推进。每阶段由成员自行认领，任务、交付、验收和 DDL 见[八阶段分工与验收计划](<docs/DAG 改造八阶段分工与验收计划.md>)。

## 文档与数据

| 入口 | 内容 |
|---|---|
| [第一阶段交付与交接](docs/dag/phase1/README.md) | 冻结契约、手算图、源码核验、数据配对与验收命令 |
| [DAG 架构与改造计划](docs/dag架构与改造计划.md) | 目标、架构、接口和验证设计 |
| [DAG 实现现状与缺陷](docs/DAG实现现状与缺陷.md) | 已有实现与源码定位 |
| [八阶段分工与验收计划](<docs/DAG 改造八阶段分工与验收计划.md>) | 阶段认领、排期、交付与精度验收 |
| [基准数据说明](baseline-data/README.md) | 分类、可用范围、待核验项和隔离样本 |
| [基准文件索引](baseline-data/INDEX.md) | 具体数据、脚本和实验记录的位置 |
| [SimAI 使用文档](docs/simai/README.md) | 继承组件的安装、运行与配置说明 |

`baseline-data/` 保存历史原件和分析产物；新实验结果应另存到 `results/`，保留运行配置和输入身份，不覆盖基准文件。

## 环境与运行

当前沿用 SimAI/Vidur 的环境和入口。初始化子模块：

```bash
git submodule update --init --recursive
```

- SimAI 编译与运行：[中文安装](docs/simai/CN/getting_started/installation.md)、[快速开始](docs/simai/CN/getting_started/quickstart.md)。
- 推理环境、请求生成与场景配置：[Vidur-AlibabaCloud](vidur-alibabacloud/README_CN.md)。
- 原有 PD 配置测试，在按推理文档准备好 Python 环境后运行：

```bash
cd vidur-alibabacloud
python -m pytest tests/test_pd_separation.py -v
```

该测试覆盖配置与集群构造，不能代替 DAG、KV 传输或端到端精度验收。独立 DAG 命令入口随执行核实现后补充。

## 验证标准

**功能正确性**：验证 DAG 拓扑、依赖、时间单调性、确定性、资源容量和请求完成回调；使用可手算用例检验串行、并行、争用与同步。

**精度提升**：在相同模型、硬件、输入、并行配置和指标定义下，比较原模型参考数据、原 SimAI 和新 DAG 系统。校准数据与独立验证数据分开，报告绝对/相对误差、样本数、退化情况和运行开销。

原模型数据的测量或估计属性需明确。合成测试通过、历史模拟结果导入或新旧输出不同，都不能单独证明真实硬件预测更准确。

## 仓库结构

```text
baseline-data/          历史基准、输入、日志、分析与隔离样本
docs/                  DAG 设计、分工与技术文档
  simai/               SimAI 教程、配置与图片
  upstream/simai/      原 SimAI 多语言 README
vidur-alibabacloud/     请求调度、推理事件与性能预测
aicb/                  计算画像与工作负载
astra-sim-alibabacloud/ 集合通信仿真
SimCCL/                集合通信 flow model
ns-3-alibabacloud/      网络仿真
scripts/               现有构建与运行脚本
example/               现有示例输入
```

## 原 SimAI 项目

本项目保留 SimAI、Vidur-AlibabaCloud、AICB、Astra-Sim、SimCCL 和 ns-3 的已有实现作为改造基础。原项目说明已归档：[中文](docs/upstream/simai/README_CN.md)、[English](docs/upstream/simai/README.md)、[日本語](docs/upstream/simai/README.ja.md)。许可证见 [LICENSE](LICENSE)。
