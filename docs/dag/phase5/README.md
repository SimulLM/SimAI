# 第五阶段 · 拆分计算与通信任务

从项目根目录运行。使用阶段四的 Python 3.10+ 推理环境及
`scripts/dag_phase4/requirements.txt`。本地 Python 3.14.5 可使用阶段四的隔离依赖。

```powershell
$env:PYTHONPATH = "$PWD\.cache\phase4-deps;$PWD\vidur-alibabacloud;$PWD"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m vidur.main --help
python scripts/dag_phase5/main.py --output results/dag/phase5/20261111-phase5-acceptance-01
```

验收命令使用合成画像训练原预测器，运行五组 `legacy`、`dag_coarse`、`dag_expanded`
对照，并用默认通信占用策略额外运行 PP 争用场景。测试同时检查合成 EP 的 prefill 和 decode、
接收端争用、资源独立时的重叠与前四阶段回归。兼容对照对 PP 显式使用独立通信端点。
退出 0 表示功能与阶段五精度门槛均通过，1 表示功能或运行失败，2 表示功能通过且精度门槛
仍有阻塞或未达到。

## 费用和调度

- 原 Vidur 默认路径为 `legacy`。原入口加 `--execution_mode dag_expanded` 后，每个 Stage
  从一个预测快照构图。同一 Simulator 推进计算、通信和同步。唯一 terminal 交回原 StageEnd，
  后续组批、PP Stage 到达、token 和请求结束由原事件负责。
- 每层计算按 attention、MLP 和 residual add 收费，分项原值保存在任务 metadata。
  TP=2 等多 rank 配置每层两次 AllReduce，Vidur 的 NCCL launch/skew 随原 TP 估值计入。
  非末 Stage 一次 PP 聚合费用。TP/PP metadata 中 payload 是预测器输入所代表的单次
  逻辑消息大小。CPU 前后开销按原字段分配。DAG 费用账本采用 Stage 预测原值，Stage 原聚合值
  用于对账。实际服务区间包含图内资源等待，启动前等待独立记录。旧 MetricsStore 的分项仍
  是预测口径，`timeline.csv` 和 `cost-breakdown.csv` 提供实际执行与冻结费用的逐任务对应。
- SimAI ns-3 和 analytical 使用现有 TP 适配器，PP 使用原 send/recv 预测器。本地未发现可运行
  二进制，当前完成适配代码并保留待验证状态。AICB 特殊模型只接 PP=1、TP=1 和显式 EP 组，
  读取层画像 ns 并转换一次。聚合 EP 使用画像的 `comm_size` 和配置的阶段带宽。源画像只提供
  聚合通信，输出一个 EP 节点，dispatch/combine 由独立费用证据和后续扩图提供。AICB 的
  合成探针记录旧总值与修订结果，真实画像运行待补证。支持边界见
  [support-matrix.csv](../../../configs/dag/phase5/support-matrix.csv)。

## PD 和 MoE 共用接口

`GraphBuilder.build(context)`、`CostProvider.estimate(task, context)`、`DagExecutor.submit/append`、
`ResourceManager.try_acquire/release`、`KVCapacity` 与 terminal callback
`(graph_id, now_s) -> EventIntents` 沿用 [v1 契约](../phase1/execution-contract.md)。
一个 batch iteration 在一个 Stage 上对应一个 fragment，任务身份为 `(graph_id, task_id)`。
任务费用随 fragment 冻结，`demands` 决定资源占用。MoE 可在 PENDING 屏障保护下追加
已知费用的 dispatch、expert、combine 并汇入同一个 terminal。PD 在消费该 terminal 后
通过 KV 协议管理存储字节，传输费用使用独立的 wire bytes。

通信任务的 metadata 包含 `op`、`layer`、`source`、`components`、`communication_type`
（`tp`、`pp` 或 `ep`）、`group`、`endpoints`、`payload_bytes`、`topology`、
`occupies_gpu`。PP 带 `rank_pairs`，聚合 EP 带 `granularity`、`phase` 和
`bandwidth_bytes_per_s`。通信组成员位于 `placement.device_ids`。

默认每设备、每副本 CPU 和每逻辑通信端点各一个许可，通信占参与 GPU。可以通过
`--dag_resource_config <json>` 显式共享端点、指定独立的通信类型或定义 EP 组。
以下为两个副本的合成 EP 映射示例，端点名称相同表示共享同一个许可。

```json
{
  "endpoints": {"gpu:0:0:0": "nic0", "gpu:1:0:0": "nic1"},
  "independent_comm": [],
  "ep_groups": {
    "experts": {
      "members": ["gpu:0:0:0", "gpu:1:0:0"],
      "bandwidth_bytes_per_s": {"prefill": 1000000, "decode": 2000000},
      "evidence": "synthetic fixture"
    }
  }
}
```

## 数据、结果和交接

精度增量使用 `configs/dag/phase5/data-pairs.csv` 和 `dataset-split.csv`，分别按
`pair_id` 和 `group_id` 覆盖阶段一对应行。配对准入继承阶段一身份、单位、证据哈希和
calibration/validation 分组。每个新增合格配对填写 `same_cost_record`、
`revised_cost_record` 和 `attribution`。用 `scripts/dag_phase1/import_results.py`
导入实际结果，按四个记录保存参考值、旧预测、同费用展开和修订费用预测。当前七项候选
仍有阻塞，优先补 microAllReduce、TP8 AllToAll、TP2/EP4 AllToAll 的匹配记录。
恢复失败的历史运行需用同一 workload 和拓扑重跑旧后端及独立参考，并使用已核验单位的
单次 collective 区间。合成验收记录仅用于功能证据。

正式目录为 `results/dag/phase5/YYYYMMDD-phase5-<purpose>-NN/`，每次使用新目录。
场景目录包含 `requests.csv`，模式目录包含命令、退出码和进程日志，原生时间戳目录包含
原指标、配置、任务／资源时间线、Chrome trace、`cost-breakdown.csv`、`overlap.csv`
和 `graphs/stage-*.graph.json`。顶层保存三份功能对照、精度逐样本与汇总、阻塞清单、
pytest 日志与 JUnit、验收报告和运行 manifest。秒值使用 `_s` 后缀，Chrome trace 使用微秒。
同名 ZIP 单独交接，排除 `pytest-tmp/` 和 `predictor-cache/`。交接时同时提供代码版本、
运行命令、验收结果和遗留问题。

## WSL 后端复验

在 Ubuntu 22.04 的项目目录执行。构建使用顶层 HEAD 与锁定的子模块 Git 归档，输出二进制、
编译日志和哈希。验收使用 WSL 内安装了阶段四 requirements 的 Python 虚拟环境。

```bash
bash scripts/dag_phase5/build_wsl.sh .cache/phase5-wsl-build-new
export PYTHONPATH="$PWD/vidur-alibabacloud:$PWD"
python scripts/dag_phase5/main.py --wsl-build .cache/phase5-wsl-build-new \
  --output results/dag/phase5/20261112-phase5-wsl-acceptance-01
```

复验先跑原双 collective 冒烟，再冻结 8 卡 H20、TP8、FP16 的 16 MiB 校准与 64 MiB 验证输入。
ns-3 为模拟参考。读取单次 forward collective service 的 `fwd total comm`（微秒），
并将原 CLI 的两个 SimAI 后端与实际 DAG TP 节点时间线核对。Analytical 的 H20 网络参数由
显式 CLI 选项传入，实验把 CPU launch/skew 置零以对齐通信口径。校准配置只在
对应 analytical 模型、TP/PP、拓扑和配置哈希下生效。所有配对记录和配置增量归入正式运行
的 `collective-evidence/`，并由阶段一的严格配对规则复核。

若初轮比例模型在 64 MiB 验证退化，保留该轮目录并使用 `--refine-from <初轮目录>`。
修订保留 analytical 的带宽项，仅从原 16 MiB 校准样本估计固定偏差，参数冻结后使用此前
未执行的 32 MiB 验证输入。原 64 MiB 结果以失败诊断保存在 `prior-validation.json`。
旧预测、同费用及修订路径共同使用整数 payload 序列化修复和相同的显式网络配置。
