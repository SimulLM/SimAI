# 阶段6功能验收记录 · 2026-11-17

开发分支dev-v6，基于8e64002加本轮未提交工作区。公共v1契约保持兼容。Python 3.15.2 / Windows，正式运行退出2：功能passed，精度blocked_missing_matched_pd_reference。

| 验收项 | 结果 |
|---|---|
| 完整回归 | 259 passed，0 failed，0 skipped；原有224项及新增35项 |
| 原CLI | 单请求、双请求、容量背压、TP2/PP2、无需后续Decode五组通过 |
| 请求语义 | 所有请求结束，Token计数正确，StageEnd与各图terminal各一次 |
| Decode门控 | 首次Decode实际Stage启动不早于KVReady |
| 背压 | 第二请求实际等待目标容量0.030568248888889288s后前进 |
| KV生命周期 | 源存储保持到KVReady；commit不重复计费，最终存储/pin/预留清空 |
| 资源与事件 | 容量检查通过，宿主队列清空，全部图依赖满足 |
| 故障与截断 | 中止清理、重复动作、接收故障、真实Simulator截断/失败测试通过 |
| 精度 | 无匹配PD参考；未计算虚构误差，未声称硬件精度改善 |

正式目录为 `results/dag/phase6/20261117-phase6-final-01/`。259项回归约325秒，包含前置阶段及PD两组原CLI专项回归。五组正式原CLI检查另行执行，使用明确标为synthetic的预测器训练画像与PD链路参数。

已逐项验证manifest的237份源文件和371份产物哈希，均匹配。另存 `results/dag/phase6/final-output-review.json`，独立检查所有五组图依赖、逐事件KV容量边界、源释放时刻、传输费用公式和Decode门控。

正式结果包为 `results/dag/phase6/20261117-phase6-delivery.zip`，包含正式产物、manifest、测试时源码快照和独立产物核验。排除pytest临时目录与预测器缓存。结果包继承Git忽略规则，需单独传递或从README命令重新运行。

开发过程中有依赖安装未完成、首次回归的异常处理/PYTHONPATH和运行中源码变化失败，均保留原日志；正式运行已在修复后通过。正式CLI启动期间恢复了request.py未修改区域的原始混合换行，AST完全一致，诊断见results/dag/phase6/newline-repair.json。完整回归在该维护结束后运行，正式manifest中的源码哈希与最终实现一致。

无需后续Decode的请求在Prefill完成时结束，未创建PD传输。该场景的ITL等额外Decode指标没有定义，原指标库可能产生统计提示；验收使用请求完成、Token、资源与迁移状态，不将此类指标用于精度结论。

后续工作：补齐匹配PD参考与三方误差对照，校准独立链路费用；PD+MoE、异构分片/格式转换、抢占重启、迁移重试、流级共享带宽和大规模优化继续保持未验收状态。验收在提交前工作区完成，精确实现由manifest源码哈希与交付包中的源码快照固定；最终提交版本见dev-v6历史。
