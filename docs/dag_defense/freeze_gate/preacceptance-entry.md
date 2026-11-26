# 唯一当前执行入口：2048/128、并发 4、32 请求预验收

这轮由用户于 2026-11-26 指定，单独标记，不计入正式 validation。停止新增诊断变体。

```bash
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/run_preacceptance.py --output /root/autodl-tmp/dag-handoff/runs/<new-attempt-id>
```

入口执行现有轻量事件 1P1D 服务、4 条独立计数的预热请求、空闲观察、32 条实测、服务清理、原版及 DAG 的真实到达回放、逐请求评分和有效性断言。输出目录必须不存在。重试添加 `--retry-of <old-attempt-dir>`，旧尝试全部保留。

固定比较角色：

| 角色 | 源码与改动 | 用途 |
|---|---|---|
| `baseline` / pristine original | `cef83f9ddd96540e3e9f48934f11335d52d54fce`，独立检出，无 tracked 改动 | 未修改原版预测，缺陷作为观测保留 |
| `dag` / original fee provider | `b3ce1b661d39510192652457ce1266ebfa417b1b`，仅预测器替换为原版文件 | 当前唯一 DAG 候选；不加入就绪修复或调度改造 |
| 就绪修复、固定组批、动态首 token、whole-forward | 既有诊断工作树 | 排除于本次主比较，不能混称基线 |

计算、attention、CPU、通信 profile 与 255 Gibit/s 费用参数沿用 `pd-pull-calibration-replay-20261126`。不因本轮 E2E 结果改变费用。DAG 等待时长不是第二笔通信费用；配对费用比较用图中任务 duration 求和，排除资源等待。

主指标实测为 router `server_complete_ns-server_arrival_ns`；预测为最后模型批次完成减去同一实际到达。未建模的末端 host/router 残差保留在误差中，不加补偿常数。完整性、因果、覆盖和重复计费是门槛；小误差、相同批次、DAG 改善均不是门槛。

`formal_preflight.py` 的完整冻结前整合仍未验收；当前只复用其纯函数 `coverage` 检查主比较 profile 的特征范围。不能据该脚本存在而宣称已冻结或正式验证已启动。预验收结果及具体失败断言见同目录后续报告。
