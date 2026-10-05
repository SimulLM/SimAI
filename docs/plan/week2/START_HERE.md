# 第二周开工阅读与对齐清单

更新日期：2026-10-05。面向成员一至四；这是阅读导航，不另设排期或接口。任务和验收标准以 [Week2 计划](WEEK2_PLAN.md) 为准，通用协作规则以 [贡献指南](../../CONTRIBUTING.md) 为准。

不要求全员读完整仓库。先读共同必读，再按角色读对应部分；历史成果用于确认限制，不执行旧排期。阅读不能代替代码定位、样例运行和评审。

## 1. 全员共同必读（按顺序）

| 顺序 | 文档与部分 | 必须弄清楚 |
|---|---|---|
| 1 | [仓库 README](../../../README.md)：三分钟了解项目、当前执行：第二周接口开发 | 项目组件及本周固定 EP→后端→Vidur 链路；不是从零重写仿真器 |
| 2 | [Week2 计划](WEEK2_PLAN.md)：第 1–3 节 | D1 上午对齐、当天开发、补证并行；P0 和暂不做的内容；固定计算仅用于受控测试 |
| 3 | [架构](../../ARCHITECTURE.md)：组件关系、核心执行路径、接口边界 | Vidur 管请求/执行依赖，SimAI 提供通信预测；现有代码路径不代表 EP 已闭环；目标架构并非已实现 |
| 4 | [Week2 计划](WEEK2_PLAN.md)：第 4 节全部 | estimate 的输入/输出、bytes 矩阵方向、秒单位、rank/节点映射、失败语义、缓存及回写日志；草案需 D1 正式确认 |
| 5 | [Week2 计划](WEEK2_PLAN.md)：第 5 节本人任务、第 6–10 节 | 今日交给谁什么成果；里程碑、W2-A01–A09、评审分工、风险裁决 |
| 6 | [贡献指南](../../CONTRIBUTING.md)：基本规则、分支命名及同步、Issue 流程、PR 流程、周计划与验收文档、测试要求、完成定义 | 从 dev 起步；小任务与非作者评审；merge 同步/合并；合并不等于验收；禁止提交生成物 |
| 7 | [PR 模板](../../../.github/pull_request_template.md)、[实验记录模板](../../templates/experiment_record.md)第 1、3–9 节、[Week2 验收表](week2_acceptance.md) | 如何提供实际命令、版本/输入身份、日志获取位置、限制和审核；尚无证据不能标通过 |

## 2. 成员一：接口、集成与验收（共同必读之后）

1. [Week1 审核报告](../week1/WEEK1_TEAM_REVIEW_AND_NEXT_PLAN.md)第 1、3–6、10 节；[Week1 验收表](../week1/week1_acceptance.md)第 1、4 节：掌握三人的已交付能力、待补证和不可宣称的结论，不重新安排一个全员补证日。
2. [项目分析](../../PROJECT_ANALYSIS.md)的“模块地图、执行与数据流、已确认扩展点、当前缺口与风险”：识别接口实施边界、TP 缓存与 AICB 重复计时风险。
3. 回看 Week2 第 4、5 节成员一任务、第 7–9 节：形成最小契约、mock、非法输入测试、合并顺序和非作者验收安排。
4. [Week1 基线清单](../week1/week1_baseline_manifest.md)第 1–4 节、[CI 配置](../../../.github/workflows/ci.yml)：确认源码/子模块身份及现有自动检查范围；确认远程 dev 保护、评审权限，不能把文档规定当成已配置。

带到启动会：固定演示场景、契约字段未决项、拟定文件归属、dev 起始 SHA、评审人、首批任务卡和验收安排。启动会上记录确认结果，未决项列负责人/时限；未实现前不称接口已冻结/已运行。

## 3. 成员二：通信后端（共同必读之后）

1. Week1 审核报告第 3、6 节：核对输入/config/拓扑身份缺项、不可比后端对照及 TP1/EP 的 0 collective 问题。
2. 项目分析的“模块地图、执行与数据流、已确认扩展点、当前缺口与风险”；架构的“SimAI 解析模式、SimAI ns-3 模式、接口边界”：掌握 Workload/Layer→SimCCL FlowModel→后端的路径，区分标量 collective、矩阵及诊断 CSV。
3. [安装指南](../../getting_started/installation.md)的 Prerequisites、Clone and Initialize、Compile SimAI-Analytical、Compile SimAI-Simulation；[构建参数](../../configuration/build-options.md)的 Build Modes、SimAI_simulator Parameters、SimAI_analytical Parameters、Topology Generator Parameters：弄清 Linux 工作目录、构建输入和输出参数。先读，不要求先完成完整 ns-3 构建才接 mock。
4. Week1 基线清单第 1–5 节；Week2 第 4.2、4.3 节及成员二任务：确认消息字节是 per-peer/per-rank/全组哪种，EP 到物理 GPU 映射、单位转换、支持范围、归档身份与缓存。

带到启动会：共用 EP4 输入能否被后端表达、字节映射的待验证点、真实配置候选、adapter 文件位置及首个独立运行命令。首先交映射证据和 adapter 骨架；未支持的矩阵返回 unsupported，不平均化；0 collective 不算成功。

## 4. 成员三：Vidur 接入（共同必读之后）

1. Week1 审核报告第 4 节：明确 EP MoE 与 PD KV 不同；已有 TP 路径尚不能证明端到端通过；识别秒/ms、层/迭代次数及指标语义问题。
2. 项目分析的“执行与数据流、当前缺口与风险”；架构的“多请求推理模式、接口边界”：从实际 heapq 事件循环、预测器到执行完成/指标定位代码，不误用遗留队列。
3. [Vidur README](../../../vidur-alibabacloud/README.md)的 Environment Setup、Key Input Parameter Reference（含 PD Disaggregation Parameters）、Key Output Interpretation：理解运行配置、画像依赖和输出含义。Running Examples 只按需要参考，历史大模型样例不是本周最小测试的前置任务；团队 Python 要求以贡献指南为准。
4. Week2 第 4.1、4.3、4.4 节及成员三任务，重点 W2-A03/A04/A06/A08：明确调用位置、默认关闭开关、逻辑时间推进、失败传播、避免重复计算及受控测试。

带到启动会：候选文件/函数、请求归属、一次 dispatch/compute/combine 调用次数、已知延迟如何改变关键路径、默认关闭回归方案。首先交 mock 接线与受控测试，不等待真实后端；不能以修改 KV 延迟代替 EP 回写。

## 5. 成员四：矩阵与输入（共同必读之后）

1. Week1 审核报告第 5、6 节：区分目的负载向量与 source→destination 矩阵，确认 per-rank/全组 token、Top-K、trace 精度和原始日志缺项。
2. Week2 第 4.2、4.3 节及成员四任务，重点 W2-A01/A02/A09：明确行列、单位、对角、12 MiB EP4 样例、映射、输入哈希、派生字节统计和非法输入。
3. [校准策略](../../CALIBRATION.md)的“第一周公开参考：DeepSeek profile-data”（含可以/不能校准的内容）、“结果报告规则”；项目分析的“校准数据边界”：合成偏斜和可见 kernel 重叠不是实际端到端性能真值。
4. Week1 基线清单第 2、5 节；实验记录模板第 4–8 节：统一 LF 文件身份、seed、生成配置、守恒统计及补证方式。

带到启动会：EP4 uniform JSON 草案、行/列/总量预期值、dispatch/combine 分别如何生成、fixture 和生成器文件归属。首先交固定输入及校验；不能无依据假设 combine 是 dispatch 的转置，也不能把向量冒称网络矩阵。

## 6. 阅读结束后的共同确认

每人向组长提交一张简短开工卡，不新增重复的状态文档；放在对应任务 Issue 或启动会记录中：

```text
我负责：
我准备修改的文件/函数（待会上一致确认）：
输入来自谁、具体样例：
输出交给谁、具体样例：
首项交付与截止工作日：
验证命令/预期结果（未确定标待确认）：
评审人及依赖：
未弄清的问题、所需协助：
```

组长在本周目录建立启动会记录，记录日期、共同基线、文件归属、接口决定、任务 Issue 和未决项；本清单不冒充已召开的会议记录。不能回答“今天改哪里、跑什么测试、交给谁”时，只暂停有歧义部分，请组长当天确认，不让全组停等。

不作为开工必读：上游 README 全文、完整 Tutorial、四篇论文、所有旧分支材料和总体路线图全部 backlog。涉及许可证、子模块或校准扩展时再按贡献指南补读对应文档。
