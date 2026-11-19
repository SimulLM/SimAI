# 第八阶段独立验收

本轮在 **dev8-v8-acceptance** 分支执行，被验收提交为 `c759601e9f295240bde2efd8f4f6ee53fc4a0cdb`。
执行者为 **Codex 自动化验收**；新增验收文档不改变被测版本，没有修改交付实现、费用、测试或冻结输入，也没有自动提交或推送。

**结论：已有范围的功能、开销、有限范围模拟精度与环境重放分别验收；项目总体验收仍 pending。**

| 项目 | 本轮结果 |
|---|---|
| 五个历史包、内部产物及源码快照 | passed；重算历史误差表 |
| 阶段一至八完整回归 | 313 项，failures=0，errors=0，skipped=0 |
| 原 CLI 联合执行／背压 | passed；费用结算、KVReady、资源清理均检查 |
| 同费用机制与 FCFS | passed；38 场景、466 请求评估；相对 submission：{'improved': 108, 'tied': 358, 'regressed': 0} |
| 新后端 dense 参考 | passed；验证 E2E 平均相对误差 51.0343% → 2.4833% |
| dense 费用来源独立核验 | 10 条原始 collective、2048 个实际 TP 任务；单位换算及冻结 offset 均通过 |
| 第二隔离环境重放 | passed；模拟时间容差 1e-12 秒 |
| 独立输出审计 | 94 份 CLI 输出、2016 图、132396 任务，passed=True |
| WSL 工作树差异诊断 | 根仓库／SimCCL／aicb 忽略行尾与模式后无差异；ns-3 诊断超时，保留 needs_review；后端使用锁定 archive 构建 |
| 正式四场景精度 | blocked；默认验证数据仍为空 |
| 真实硬件精度／自然人签字 | 未验证／待确认 |

正式入口退出 `2`，表示功能通过、综合精度仍阻塞，不能据局部实验标全部验收通过。
首轮正式入口退出 `1`：312 通过、1 个 Windows 路径长度失败；短路径诊断通过后完整复跑，以上回归结论采用复跑结果。原失败位于 full/，复跑归档于 formal-recheck/；原始复跑目录和搬运说明见 formal-recheck-location.json。
dense 同费用 DAG 与旧路径一致，收益来自费用校准；FCFS 实验保持费用不变，独立说明资源排队机制的贡献。
既有场景属于回归数据；新增场景的输入冻结覆盖不等于新的物理参考或硬件验证。

## 本机规模记录

| 请求数 | 任务数 | 宿主事件数 | 墙钟/s | RSS峰值/MiB | 队列峰值 |
|---:|---:|---:|---:|---:|---:|
| 1 | 760 | 789 | 25.68 | 202.86 | 5 |
| 2 | 1520 | 1578 | 41.69 | 209.83 | 7 |
| 4 | 2688 | 2802 | 66.95 | 223.12 | 7 |

以上是本机实际测量，不对其他机器承诺墙钟一致。规模与背压测量先完成，随后机制实验与回归并发。

## 证据与复现

- [结构化验收报告](acceptance-report.json)、[环境](environment.json)、[问题和边界](findings.md)。
- [正式证据包](artifacts/20261119-phase8-independent-acceptance-01.zip)，校验和见 [SHA256SUMS](artifacts/SHA256SUMS)。ZIP 内保存原始运行、全部命令／日志、测试 XML、构建日志、后端 CSV、冻结参数、图／时间线及 SHA-256 manifest。
- 原始目录：`results/dag/phase8/20261119-phase8-independent-acceptance-01/`，受 Git 忽略。ZIP 排除虚拟环境、可重建预测缓存和 pytest 临时目录。
- 历史交付包保持原样，位于上一层 artifacts。本轮 historical-audit 记录精确哈希及重算结果；不以历史运行替代新运行。

在仓库根目录执行下列步骤；复验必须使用新的 run_id 和 cache 目录，不能覆盖本轮。

```powershell
$base = 'D:/Environment/Python312/python.exe'
$run = 'results/dag/phase8/YYYYMMDD-phase8-independent-acceptance-NN'
$cache = '.cache/phase8-acceptance-new'
$formal = 'results/dag/phase8/YYYYMMDD-p8-check-NN'
& $base docs/dag/phase8/acceptance/review.py init --run $run --cache $cache
& $base docs/dag/phase8/acceptance/review.py audit --run $run --cache $cache
& $base docs/dag/phase8/acceptance/review.py environment --run $run --cache $cache
& $base docs/dag/phase8/acceptance/review.py prepare-dense --run $run --cache $cache
# 按交付方 SIMULATED_REFERENCE.md，在 WSL 新构建并生成参考；仓库路径为 /mnt/g/github/SimAI。
# 后端输出放到 $run/dense/backend-reference；本轮实际命令在 ZIP 的 build/ 中。
& $base docs/dag/phase8/acceptance/review.py score-dense --run $run --cache $cache
# Windows 使用短正式输出路径，避免测试内部再嵌套历史路径后超过 260 字符。
& "$cache/env-a/Scripts/python.exe" scripts/dag_phase8/main.py --output $formal --repro-python "$cache/env-b/Scripts/python.exe"
# 保留原目录；复制到总证据目录方便归档，报告中记录真实运行路径。
Copy-Item -LiteralPath $formal -Destination "$run/formal-recheck" -Recurse
& $base docs/dag/phase8/acceptance/review.py mechanism --run $run --cache $cache
& $base docs/dag/phase8/acceptance/audit_outputs.py --run $run
& $base docs/dag/phase8/acceptance/review.py checkpoint --run $run --cache $cache
```

`review.py` 是记录型编排器：每个操作的退出码在 operations/*/process-result.json；顶层 Python 正常返回不等于所有子操作通过。
完整门槛由正式报告分项判断。安装失败、缺失 manifest 或任何功能失败不能计为通过。
本轮完整环境 freeze、子模块身份和二进制哈希见证据包及 environment.json。自然人签字仍需实际操作者确认。
