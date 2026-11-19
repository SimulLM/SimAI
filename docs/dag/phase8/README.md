# 第八阶段：联合回归、精度准入与规模开销

新增[FCFS 就绪队列修复与逐请求不退化验证](DAG_FCFS_FIX.md)：38 场景、466 次请求评估，
相对修复前 DAG 为 108 改善、358 持平、0 退化。费用和 FCFS 参考保持一致，默认提交优先级保持兼容。

分支 `dev-v8` 基于 `dev-v6` 的 `0decd78`，已包含阶段七。阶段六、七是历史交付，
其中“不支持 PD+MoE”的说明对应当时版本；本阶段新增两者的组合运行。

## 实现与支持范围

原入口仍是 `python -m vidur.main --execution_mode dag_expanded`。
同时提供 `--dag_pd_config`、`--dag_moe_config`、`--dag_resource_config` 启用组合。
MoE 保留原单组配置，并增加 `{"schema_version":"1.0","groups":[原MoE配置,...]}` 格式。
每个 GPU 恰好属于一个配置组；EP 组不能跨 Prefill/Decode 角色。

示例配置在 `configs/dag/phase8/`，两块 P 设备和两块 D 设备，各有四个 Expert。
两侧独立按轮次在 balanced/hotspot 路由间切换，PD 图搬运 KV。
计算、EP 通信和 PD 传输共用同一个执行器、容量管理器、宿主事件堆与秒时钟。
源 KV pin、目标预留、接收 commit、KVReady、Decode 实际启动与最终释放沿用阶段六协议。
没有为 PD 或 MoE 建立独立时间推进循环。

已验证范围以验收记录为准：联合配置 TP=1、PP=1、同构 P/D、完整 Prefill、逐 token Decode、
单一 dtype、显式 EP 组和端点许可。原阶段六 TP/PP 分片与原阶段七非 PD 回归继续保留。
联合原 CLI 使用 Llama 形状的合成计算画像和合成 MoE 结构夹具，不能当作真实 Llama/MoE 硬件结果。
AICB 实际画像联合运行、异构分片、格式转换、重启重试和真实流级带宽共享尚未验证。

## 完整验收与快速复现

在项目根目录使用 Python 3.12。`scripts/dag_phase8/requirements.txt` 固定已验证的顶层依赖；
完整环境版本另保存在 manifest。创建工作环境：

```powershell
python -m venv .cache/phase8-env
& ./.cache/phase8-env/Scripts/python.exe -m pip install -r scripts/dag_phase8/requirements.txt
$env:PYTHONPATH = "$PWD\vidur-alibabacloud;$PWD"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:WANDB_MODE = 'disabled'
& ./.cache/phase8-env/Scripts/python.exe scripts/dag_phase8/main.py --output results/dag/phase8/20261117-team-01
```

运行前输出目录必须不存在。Linux 虚拟环境解释器在 `bin/python`，PYTHONPATH 分隔符为 `:`。
完整验收包括：

1. 冻结精度数据的准入检查、阶段五历史通信证据包哈希复核。
2. 同一四设备配置下 1、2、4 请求的三档联合运行与开销记录。
3. 四请求较长 Decode 的目标容量背压场景。
4. 导出快照优化前后的微基准，以及阶段一至八完整回归。
5. 可选的独立虚拟环境重放，与 small 档的任务/事件/图/路由数和模拟完成时间比较。

启用第五项，需要先创建另一个不共享 site-packages 的虚拟环境并安装相同 requirements，
然后为完整命令增加 `--repro-python <另一个环境的Python路径>`。
该子进程会移除父进程的额外依赖搜索目录。它验证自动化环境复现；
“由另一位队友复现并签字”单独保持 pending，不能由同一个代理冒签。

仅快速验证原 CLI 联合链路，使用 `--smoke`，该模式不替代完整回归或三档规模验收。
退出码：1 为运行/功能失败或数据被拒绝；2 为功能运行通过但精度或独立环境复现仍有缺口；
0 为完整自动化功能、精度及独立环境门槛通过。人工交接状态始终另列。

## 精度和参考数据

进一步的[311请求扩展实验](DAG_MECHANISM_EXPANDED.md)覆盖规模、到达、长度和顺序。
FCFS主参考下平均误差13.84%→5.23%，但保留21个退化请求和更大的最坏误差，单独解释调度策略敏感性。

新增[同费用DAG机制贡献实验](DAG_MECHANISM_COMPARISON.md)：原生与DAG保持费用相同，
在共享PP通信端点场景中对照独立FCFS排队参考，单独检验资源等待建模的贡献，完全不使用通信校准。

查看[原生与改进版误差对照](MODEL_ERROR_COMPARISON.md)可直接阅读版本定义、图表和逐样本结果，
并用`python scripts/dag_phase8/compare_versions.py`从已提交证据重新生成展示，无需GPU或重新编译仿真器。

新增 [CPU 模拟参考实验](SIMULATED_REFERENCE.md)：在固定合成计算画像与调度器的条件下，
使用新生成的 ns-3 通信结果，对 TP8 稠密请求进行旧路径、同费用 DAG、校准费用 DAG 对照。
该实验独立声明有限范围；结果不能替代 PD/MoE/联合场景或真实硬件精度验证。

默认 `configs/dag/phase8/validation.json` 的 samples 为空，明确输出精度阻塞。
不会把合成请求、合成 Expert 费用或手算图当作真实硬件参考。
阶段五 TP8 通信历史结果单列为 `historical-component-evidence.json`；
它证明历史组件证据完整，不计入本阶段独立 request E2E 验证集。

提供新数据时，通过 `--validation-data <项目内JSON路径>` 指定：

- 顶层为 schema_version=1.0、primary_metric=request_e2e、reference_nature、
  required_scenarios、parameter_freeze、samples。reference_nature 只允许 measured/simulated，
  两种参考性质不能混合汇总。required_scenarios 必须在看验证结果之前确定。
- 每个 sample 包含 pair_id、group_id、split（calibration/validation）、scenario、attribution，
  以及 reference_record、old_record、same_cost_record、revised_cost_record 四个项目相对路径。
  四种记录沿用阶段一元数据、原单位、来源性质及证据哈希校验。字段模板见
  `configs/dag/phase1/record-template.json`；synthetic 不具备精度参考准入资格。
- parameter_freeze 为 `{path,sha256}`。冻结文件包含 calibration_group_ids、
  calibration_reference_sha256、validation_input_sha256，以及 scenarios 映射。
  每个 scenario 声明 scope（model/hardware/tp/pp/ep/dtype）和 cost_config_sha256。
- old 和 same-cost 记录必须有相同的 cost_config_sha256；revised 记录需给出
  parameter_freeze_sha256，且其 cost_config_sha256 匹配冻结文件中该场景的参数。
  不允许用验证参考反写费用、不允许同一工作负载或参考证据跨数据组泄漏。

逐样本保留旧误差、相同费用 DAG 误差、修订费用 DAG 误差、时序差异及费用差异，
并报告改善、持平、退化数量。只有必需场景齐全且独立验证主指标改善时才标通过；
对 simulated 参考只能声称相对该参考模型的改善。新增受控 dense 实验已有匹配样本，
但尚未覆盖默认四类场景，项目总体验收仍待补证；具体结果与限制见上述模拟参考实验说明。

## 开销与输出

`scale-overhead.csv` 保存真实原 CLI 的三档请求数、任务数、全部宿主事件数、图/路由数、
墙钟、事件队列峰值、进程 RSS 峰值和模拟最终时刻。每档由独立进程运行，墙钟包含导入、
预测器、仿真、指标和导出；RSS 每 50ms 采样，Windows 同时读取 peak_wset。
规模结果描述当前机器，不推导硬件模型精度或保证线性扩展。

优化集中在只读结果处理：MoE 导出由每轮重复复制图改为一次获取最终快照；
PD 接收改为只读取所需图，PD 导出复用一次快照。`snapshot-overhead.json` 保存同一批
最终图的复制次数、三次前后墙钟与 Python 临时分配峰值、相同任务数量校验。
这是导出快照步骤的微基准，不能当作端到端加速比；一次持有多图也可能增加临时内存。
完整图和逐 token 路由仍保留，超大规模回收没有在本阶段无证据地启用。

各 case 保存 checks.json、原 CLI 命令/日志、执行 summary、最终图、任务和资源时间线、
费用明细、KV 事件/容量、PD 迁移、MoE 路由/矩阵/负载和任务级 Chrome trace。
顶层包含 acceptance-report.json、accuracy/、历史组件证据、pytest.log/xml、
可选 reproduction-report.json、完整 run-manifest.json。manifest 固定起止一致的源文件与输入哈希、
启动时 Git 状态、依赖版本和产物哈希；运行中源码或冻结数据变化会使验收失败。

## 队友交接清单

- 用不同输出目录复现 --smoke 或完整验收，记录操作者、解释器、提交和结果。
- 核对 PD 等待、KVReady、Decode 实际启动及 MoE join 时间线，确认没有资源泄漏。
- 核对三档规模与已声明支持范围，不能把未验证组合写成通过。
- 补齐独立精度样本后重跑，保留全部退化样本；人工确认后记录交接签字。
- 交付功能通过、参考模型精度状态和真实硬件校准状态三项独立结论。
