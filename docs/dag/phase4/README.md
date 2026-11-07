# 阶段四：原推理链 coarse DAG 接入

基线为 `dev-v3` 的 `7cbf682`。先在该分支通过 125 项回归，再从该提交建立 `dev-v4`。
本阶段将原 BatchStage 映射为 `coarse -> terminal`，保持原预测器、组批、token 推进、
Stage 忙状态与原 StageEnd 的业务职责。算子、TP/PP/EP 分项图在阶段五展开。

## 原入口与模式

原入口仍为 `python -m vidur.main`，增加 `--execution_mode legacy|dag_coarse`，默认 legacy。
在项目根目录运行时，将 `vidur-alibabacloud` 加入 PYTHONPATH；其余原 CLI 参数保持有效。
推理依赖安装到虚拟环境：

```powershell
python -m pip install -r scripts/dag_phase4/requirements.txt
$env:PYTHONPATH = "$PWD\vidur-alibabacloud;$PWD"
python -m vidur.main --help
```

需提供适配原模型/backend 的 profiling 数据和请求配置。正式兼容性验收命令自行生成
小规模、明确标记为 synthetic 的画像，并调用上述原 CLI；实际使用原随机森林训练、
估时、调度器、请求实体和指标事件，没有替换为手写 token 推进器。

```powershell
python scripts/dag_phase4/main.py --output results/dag/phase4/<new_run_id>
python -m pytest tests/test_dag_phase1_contracts.py tests/dag -q -p no:cacheprovider
```

## 接入与所有权

- `ReplicaStageScheduleEvent` 仍调用原 StageScheduler/预测器一次，获取已冻结的 BatchStage.execution_time。
- DAG 模式提交一张 coarse 图；coarse 直接使用原 `ExecutionTime.total_time` 的秒值，不再转换或叠加子费用。
- `CoarseDagAdapter` 只把执行器 EventIntent 包装成宿主事件；集成运行只有 Simulator 的事件堆，不运行 DagRunner。
- StageEnd 对象在旧路径相同位置分配排序身份，但只在 terminal 回调后入队。DAG 内部事件沿用该身份在同时间事件中的位置，避免新增零时长 terminal 改变组批。
- Stage 许可 `stage:<replica>:<stage>` 表达原 Stage 的串行边界，不代表真实 GPU 并发模型；不同副本或 PP Stage 不会被误并为一个全局锁。
- 原 StageEnd 释放原 `_is_busy`，DAG 释放自己的租约，两者各司其职。失败不触发成功回调，未完成图不允许被正常结束掩盖。
- 原 CLI 显式写出结果并传播输出异常；JSON trace 中历史 set 值转为有序列表。此修复对两模式一致，不改变费用或请求调度。

## 验收与数据

五组原 CLI 对照：单请求多轮 decode、多请求组批、PP=2、两个副本、TP=2。
在相同请求、seed、画像和预测器参数下逐字段比较请求与 Stage，整数/状态完全一致，
时间绝对容差固定为 1e-12 秒。原 MetricsStore 开启，逐请求比较有限的 E2E、prefill E2E 和
decode_time_execution_plus_preemption_normalized（沿用旧指标定义，不重命名为实测 ITL）。
检查预期 token 总数、全部请求终结、StageEnd/terminal 一次、
容量、最终占用为零、宿主队列清空，并验证 JSON/Chrome trace 可解析。

另存三项宿主探针：资源阻塞到 5s 后，2s coarse 的 StageEnd 必须到 7s；零时长链完成；
1s 故障注入停止宿主、回调为零、资源收尾为零。s 为探针中的受控单位。
单元测试还覆盖同时间排序、多 Stage/副本独立资源、重复完成、非法 cost、时钟检查和预测器只调用一次。

输出目录拒绝覆盖，包含：

- `acceptance-report.json`：功能状态、逐场景检查、宿主探针、精度状态。
- `request-comparison.csv` / `stage-comparison.csv`：逐请求/Stage 的旧新结果。
- `metrics-comparison.csv`：原 MetricsStore 的逐请求指标对照；各次运行保留原始 request_metrics.csv。
- 每个场景的请求 CSV、原 CLI command/exit code/process.log、完整 config 和 execution-summary。
- DAG `timeline.csv`、`resource_timeline.csv`、`events.csv`、summary 以及原 JSON/Chrome trace。
- `synthetic-profiles/`：训练画像、生成来源与用途；不冒作实测画像。
- `run-manifest.json`：代码/输入及产物 SHA-256、依赖版本、Git HEAD/status/diff、命令、退出码。
- 异常时保留失败报告、已有输出、operation-error 与 traceback；predictor-cache 是可复建缓存，不纳入正式产物哈希。

功能通过与参考精度对照分开。阶段一配对表当前 eligible=0，因此三方误差对照为 blocked；
本阶段结果证明同 cost 下的接入兼容性，不证明硬件精度提升。原 AICB 单位/TP/PP 等已知
问题保留原 cost 语义，不混入兼容性比较。ns-3/analytical、PD、动态 MoE 和其他模型配置
未经本次矩阵运行，不列为已验证支持。

原非 PD 请求指标中的 decode_arrived_at、pd_p2p_comm_size 等可能沿用 inf/空值哨兵，
不作为本阶段数值验收指标；不据此声称 PD 完成。原运行生成的 AICB lookup/log 属缓存，
已增加定向忽略规则，不提交验收时产生的缓存。
