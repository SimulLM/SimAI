# 第五阶段验收交接

代码固定版本为 `aaacab19a2904948f4270cd988b8ce0091b21849`（`dev-v5`），包含归档字节修复
`6833e47`。验收在结算修复提交前启动，运行 manifest 记录了启动时的 HEAD 和工作区差异。

- Stage 在 terminal 回调时按最终 DAG 结算。`expanded_service_s` 汇总所有分项费用，
  `model_execution_time` 汇总非 CPU 分项并回写请求。Stage 实际耗时取首次启动到 terminal 的时钟差。
- 第七阶段启用动态 MoE 时，初始图省去对应层的 `moe.compute` 和 `moe.ep`，
  该层的 Expert 计算和 EP 通信由追加的 dispatch／expert／combine 子图计费。
- 初始图建立 `route → join → 下一层`。路由结果就绪后，宿主在交付 route 完成事件前调用
  `append`，此时 join 仍为 `PENDING`。追加的分支经 combine 汇入 join，事件继续进入同一队列。
  详细约定见 [PD 和 MoE 共用接口](README.md#pd-和-moe-共用接口)。

交付包位于本目录的 `artifacts/`，可随交接提交一起检出。[下载第五阶段交付包](artifacts/20261113-phase5-delivery.zip)

解开外层 ZIP 后，将内部两个 ZIP 分别解压到
仓库的 `results/dag/phase5/`。正式验收目录 `20261113-phase5-handoff-01/` 中，
`collective-evidence/data-pairs.csv` 和 `collective-evidence/calibration.json` 提供 WSL
配对与冻结校准，`accuracy-comparison.csv` 和 `accuracy-summary.json` 提供误差报告，
`acceptance-report.json` 和 `run-manifest.json` 提供验收状态与产物哈希。另一份 ZIP
提供 `--refine-from` 要求的三份原始记录。外层包附有两个内部 ZIP 的 `SHA256SUMS`。

WSL 验收退出码为 0，193 项测试通过。32 MiB TP8 AllReduce 相对 ns-3 的误差从 35.25%
降至 2.32%。请求级 E2E 主指标仍为 `pending`。历史通信候选、AllToAll 和真实 AICB
画像的证据缺口见正式验收目录中的 `blockers.json`。动态路由及子图由第七阶段接入，
请求级主指标由第八阶段独立验收。

在 Ubuntu 22.04 的仓库根目录激活 Python 虚拟环境、安装依赖，再执行以下命令。
构建和验收输出目录均使用新名称。

```bash
git switch --detach aaacab19a2904948f4270cd988b8ce0091b21849
python -m pip install -r scripts/dag_phase4/requirements.txt
bash scripts/dag_phase5/build_wsl.sh .cache/phase5-wsl-build-new
export PYTHONPATH="$PWD/vidur-alibabacloud:$PWD"
python scripts/dag_phase5/main.py --wsl-build .cache/phase5-wsl-build-new \
  --refine-from results/dag/phase5/20261112-phase5-wsl-acceptance-01 \
  --output results/dag/phase5/20261113-phase5-handoff-02
```
