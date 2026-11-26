# H800 1P1D 实验与DAG预测交接

2026-11-27更新：正式GPU采集 **30轮、960请求完成并对账**。冻结后的CPU预测回放仍在完成最后轮次，总体评分和详细报告尚未全部交付。不要沿用早期“0/960”的诊断快照作为当前进度。

- [原始实验计划](hardware-measurement-plan.md)：保留原文，实际执行差异在最终报告披露。
- [冻结组合费用与重验收](environment/diagnostics/composite-fee-reacceptance-20261126/README.md)：比较角色、三阶段独占费用、固定近似、冻结SHA256。
- [正式数据与分段预测备份](environment/diagnostics/formal-validation-20261127/README.md)。
- [30轮原始数据Release](https://github.com/SimulLM/SimAI/releases/tag/dev-formal-raw-30rounds-20261127)：960条成功记录，原始日志、输入、事件及空闲证据。
- [预测证据分段Release](https://github.com/SimulLM/SimAI/releases/tag/dev-formal-predictions-20261127)：每3轮一包，按完成进度上传；上传清单和SHA256见正式数据目录的`incremental/`。

未经修改原版`cef83f9...`独立保留。**费用适配参考版**与DAG共享最终组合费用，二者不能混称“未经修改原版”。自然组批差异和资源占用近似限制机制归因；本轮预测改善不等于DAG机制单独贡献已被隔离。

旧`acceptance-report.json`及`environment/01-environment.md`包含多次历史诊断快照。最终报告生成时将提供新的明确验收状态，并保留历史原件。费用、源码、输入和评分在正式测量后没有为追求误差改动；重新启动和CPU并行只改变外部编排。
