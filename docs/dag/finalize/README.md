# 跨阶段最终收尾

本目录与 phase1–phase8 并列，负责修复、补证、复现和最终交付。历史阶段记录不迁移、不改写。

本轮分支 **dev-finalize**，基线提交 `6a8499eb83ee4a49998b7b0ecae7f6412217f630`。被测实现还包含未提交改动，精确身份由工作区差异、源码 SHA-256 和 runtime-source.zip 固定，不能把基线 HEAD 单独当作完整被测版本。

首轮长路径完整回归为373通过、1个新路径校验兼容性失败；第二轮374通过且dense实验通过，但编排器误用旧函数返回码而中止。临时根隔离与返回值适配修正后，本轮完整复跑通过。原失败、原源码快照与原始 XML 均保存在 prior-attempts/，以短序号保存并另列原 run_id，不删除失败样本或改写历史记录。

**工程收尾与 Codex 自动化复现确认通过；完整四场景 E2E 精度仍待补证，整体 pending。** 本轮未开展新的 GPU 实测，用户不要求额外自然人签字。此政策仅适用于本轮，不改写历史签字记录。

| 项目 | 结果 |
|---|---|
| Windows 长输出目录完整回归 | 378 passed，0 failed；pytest 临时目录改为短且独占的项目缓存路径 |
| Linux 本地干净检出完整回归 | exit 0，原始 XML 与日志保留 |
| 原 CLI 联合执行、背压、三档规模 | passed；唯一完成、KVReady、最终费用、资源释放均检查 |
| 独立 CPU 机制参考 | 24场景 passed；合成组件级一致性，不冒充完整请求精度 |
| 已有策略对照复跑 | 466 次请求评估；108 改善、358 持平、0 退化 |
| 新通信后端与冻结 dense 校准 | E2E 平均相对误差 51.0343% → 2.4833%；本轮未重新拟合 |
| DeepSeek 原始 trace | prefill/decode 固定提交与原始 SHA；仅行为参考，缺少匹配独立预测和完整身份，不计算虚构精度 |
| ns-3 工作树差异 | 批量 Git blob 比较完成；原始字节、换行和模式差异分别记录，子模块无未解释实质差异 |
| Codex 独立环境复现确认 | passed；Windows/Linux 关键数量及时间、24场景、dense 与 trace 解析核对 |
| 独立输出审计 | 146 输出、2072 图、134006 任务 passed |
| 原计划四场景请求 E2E | blocked_missing_matched_reference；不能用局部指标或合成参考替代 |

DeepSeek 原件显示 H800、rank 0，prefill world_size/EP32、decode EP128。当前文件的 kernel 时间字段为整数；解析器保留小数精度的能力由测试覆盖，不声称本轮原件出现了小数截断改善。不能从单 rank GPU kernel 推断整个 RDMA 完成或请求到达/完成边界。

三档开销在其他实验之前单独测量；后续策略实验并发，其墙钟不作为孤立性能基线。

| 请求数 | 任务数 | 宿主事件 | 墙钟/s | RSS峰值/MiB | 队列峰值 |
|---:|---:|---:|---:|---:|---:|
| 1 | 760 | 789 | 22.33 | 202.75 | 5 |
| 2 | 1520 | 1578 | 37.10 | 209.06 | 7 |
| 4 | 2688 | 2802 | 62.07 | 221.52 | 7 |

## 入口与证据

统一入口：`python scripts/dag_finalize/main.py --output results/dag/finalize/<run_id> --environment-evidence <环境证据目录> --reference-data <固定DeepSeek原件目录>`。
run_id 为 `YYYYMMDD-finalize-purpose-NN`，拒绝覆盖。`--pytest-basetemp` 可选，必须是项目 `.cache` 下不存在的目录；默认 `.cache/p8t/`，不删除调用者已有目录，不修改 Windows 全局配置。

首次环境准备使用 linux_environment.py，在 WSL Linux 本地磁盘固定源码与子模块，独立安装 CPython 3.12.10、两个 venv 并构建后端。DeepSeek 用 deepseek.py 按 configs/dag/finalize/deepseek-source.json 固定提交获取。完整实际 argv、环境版本、构建日志和哈希都在证据包。

主入口默认运行全部工作；`--replay` 仅供 bridge 执行 Linux 主要结果重放，其前置完整回归由 bridge 单独记录。运行前冻结源文件，运行结束再次核验；执行过程中不可编辑被测代码或配置。

退出码：1=运行/功能失败或无效输入；2=功能完成但必需精度参考/复现门槛未齐；0=声明门槛全部满足。本轮正式入口返回 **2**，不把组件通过升级为项目精度通过。

- [结构化报告](acceptance-report.json)、[环境](environment.json)、[参考准入清单](reference-inventory.json)、[自动化复现确认](reproduction-confirmation.json)。
- [剩余缺口与关闭条件](remaining-gaps.md)。
- [正式证据包](artifacts/20261119-finalize-independent-acceptance-long-path-03.zip) 和 [SHA256SUMS](artifacts/SHA256SUMS)。
- 原始运行：`results/dag/finalize/20261119-finalize-independent-acceptance-long-path-03/`，受 Git 忽略。ZIP 包含原件、命令、日志、XML、冻结费用、源码快照和时间线，排除 venv、预测缓存及 pytest 临时目录。

本轮不自动提交、合并或推送。受控路径修复兼容旧 phase8 入口；旧文档、历史结果和 ZIP 保持原样。
