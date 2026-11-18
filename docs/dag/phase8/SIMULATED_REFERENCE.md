# 阶段八模拟参考实验

本实验使用 CPU 上新运行的 ns-3 通信结果作为参考，固定计算画像和请求调度，
比较旧 SimAI、相同费用的 DAG SimAI、校准通信费用后的 DAG SimAI 的请求 E2E。
这是通信模型对请求指标影响的受控实验，不能据此认定真实 GPU、计算算子、
PD 或动态 MoE 的预测精度已经验证。

## 冻结的实验范围

- Llama-2-7b 结构，逻辑 8×H20，TP=8、PP=1、EP=1、FP16。
- 每次运行一个请求，完整 Prefill、逐 token Decode，不混入组批或争用。
- 校准请求为 2048 Prefill / 2 Decode；验证请求为 3072/2、5120/4、6144/8。
- 全部路径共享同一合成计算画像与原请求调度器。计算画像只提供受控背景费用。
- 参考路径为原 CLI 的 `legacy + simai_simulation`，通信输入来自新执行的 ns-3。
- 旧路径为 `legacy + simai_analytical`；同费用新路径为 `dag_expanded + simai_analytical`。
- 校准只拟合一个每次 collective 的固定开销：校准请求的 E2E 差值除以其 TP 任务数，
  下限为零。参数冻结后不根据验证结果调整。
- 主要指标为三个验证请求的平均相对误差；同时保存逐请求 E2E、TTFT、TPOT。

所有请求定义及分组在运行参考之前写入 `experiment-freeze.json`。
校准/验证的 Prefill payload 与完整请求输入不同；所有请求共享单 token Decode 的
64KiB 通信输入。这是对新请求和 Prefill 大小的验证，不是对所有通信输入的完全留出。
样本量为一个校准、三个验证，没有测量噪声区间或泛化保证。

## 生成与复现

以下命令在项目根目录执行。Windows 使用阶段八现有 Python 环境和 WSL Ubuntu 22.04；
Linux 可直接运行对应 Python/Bash 命令。无需 GPU 或 PyTorch。

1. 在 WSL 项目根目录运行以下命令，复用阶段五构建脚本生成两个仿真器：

```bash
python3 scripts/dag_phase8/build_reference.py --output .cache/phase8-simulation-build-new
```

适配器规范脚本换行，并将源码/动态库保存在 Linux 用户的持久缓存目录，避免 WSL 重启清理
`/tmp` 后二进制无法启动。构建需要 CMake、C++ 编译器和 make；记录构建日志、
子模块版本和二进制哈希。输出目录必须是新目录。后续 `--binaries` 使用同一目录。
2. 冻结输入并生成共享计算画像：

```powershell
& ./.cache/phase8-repro-env/Scripts/python.exe scripts/dag_phase8/simulated_reference.py --output results/dag/phase8/20261118-simulated-reference-01 --prepare
```

3. 在 WSL 中运行新参考。将以下路径前缀替换为本机仓库的 Linux 路径：

```bash
cd /mnt/c/Users/zhongjiahui/Desktop/FinalSimAI/SimAI
python3 scripts/dag_phase8/simulation_backend.py \
  --inputs results/dag/phase8/20261118-simulated-reference-01/inputs \
  --binaries .cache/phase8-simulation-build-new \
  --output results/dag/phase8/20261118-simulated-reference-01/backend-reference
```

4. 回到 Windows，用真实原 CLI 执行四条路径并评分：

```powershell
& ./.cache/phase8-repro-env/Scripts/python.exe scripts/dag_phase8/simulated_reference.py --output results/dag/phase8/20261118-simulated-reference-01 --backend-evidence results/dag/phase8/20261118-simulated-reference-01/backend-reference
```

为在 Windows 消费 Linux 仿真结果，工具把原始 CSV 字节放进原预测器的缓存路径。
每次输入必须与原 CLI 实际生成的 collective workload 完全一致，拓扑、配置、参数、
二进制和原始输出均保留哈希。没有插值、修改参考数值或用验证值替换新系统的费用。
新系统只使用 analytical 输出与冻结的校准参数。

实验拒绝覆盖已经执行的目录。首次运行及复现都应使用新的结果目录。
退出码 0 只表示该受控模拟实验主指标通过；2 表示未改善，完整结果仍保留。
项目总体验收始终单列为 pending，不自动替代四场景的最终精度验收。

## 输出及结论边界

- `simulation-report.json`：有限范围的主指标、改善/持平/退化计数与限制。
- `request-comparison.csv`：校准与全部验证请求的四路 E2E、TTFT、TPOT。
- `accuracy/`：沿用阶段八准入工具的逐样本误差与汇总。
- `parameter-freeze.json`、`calibration.json`：冻结参数与数据分组身份。
- `backend-reference/`：新执行的 CPU 仿真命令、日志和原始 CSV。
- `runs/`：每个请求四条路径的实际原 CLI 命令、日志、请求指标和 DAG 时间线。
- `run-manifest.json`：被测源文件、环境和全部产物哈希。

默认 `configs/dag/phase8/validation.json` 继续要求 dense/PD/MoE/joint 四场景，
不会因本实验只覆盖 dense 而缩小要求。该实验生成的独立 `validation.json` 明确只声明
受控 dense 范围。若误差降低，应表述为“在固定合成计算背景下，相对 ns-3 通信参考模型，
校准后的请求 E2E 误差降低”。相同费用路径单独报告，避免把校准收益归因于 DAG 调度。

## 2026-11-18 实际结果

运行目录：`results/dag/phase8/20261118-simulated-reference-01/`。
新构建和执行两个 CPU 仿真器，生成五种通信输入各两份原始输出；
四个请求各运行参考、旧、同费用 DAG、校准 DAG 四条真实原 CLI 路径，共16次。
校准请求单列，不计入以下验证统计。固定的每次 collective 开销为 **81.654μs**。

| 验证请求 Prefill/Decode | 参考 E2E/ms | 旧 SimAI/ms | 同费用 DAG/ms | 校准 DAG/ms | 旧相对误差 | 校准后相对误差 |
|---|---:|---:|---:|---:|---:|---:|
| 3072/2 | 22.029 | 11.463 | 11.463 | 21.914 | 47.96% | 0.52% |
| 5120/4 | 40.731 | 20.679 | 20.679 | 41.583 | 49.23% | 2.09% |
| 6144/8 | 68.820 | 30.344 | 30.344 | 72.151 | 55.91% | 4.84% |

| 指标 | 验证样本数 | 旧平均相对误差 | 校准后平均相对误差 | 改善/持平/退化 |
|---|---:|---:|---:|---|
| E2E（主要指标） | 3 | 51.03% | 2.48% | 3/0/0 |
| TTFT | 3 | 31.46% | 5.65% | 3/0/0 |
| TPOT | 3 | 72.75% | 11.22% | 3/0/0 |

E2E平均绝对误差由23.031ms降至1.432ms。相同费用DAG与旧系统的差异仅在浮点舍入量级，
本轮收益应归因于通信费用校准，不能归因于DAG调度或计算通信重叠。
两个较大请求的校准后预测高于参考值，完整数值保存在CSV中。

当前285个独立测试用例分次执行后均通过。首轮完整回归为282通过、1个子进程导入环境失败；
第一次复测期间新增缓存测试触发源码一致性保护，冻结源码后的最终复测通过。
缓存键修正后另执行19项精度/回放测试，均通过。原始失败日志、复测XML和按当前用例清单
合并的`regression-summary.json`全部保留，没有将首轮失败记录改写为成功。

首次CPU参考启动缺少ns-3动态库，改用持久构建目录后重新运行；失败启动记录也保留。
正式参考位于`backend-reference-03/`。本次未使用阶段五历史验证值充当新样本。
外部捕获的运行日志在进程退出后收尾，初始manifest保留为`run-manifest.initial.json`；
最终manifest重新记录完整产物哈希，数值结果和被测源码未改动。

[下载本轮模拟参考证据包](artifacts/20261118-phase8-simulated-reference.zip)。
包内包含完整运行、构建记录、206份运行源码/协议/依赖文件及25份测试文件快照；
校验和见同目录`SHA256SUMS`。结果按项目相对路径保存，可解压到项目根目录审计，
源码快照单独位于`tested-source/`，不会覆盖当前源码。

本轮结论为：**在固定合成计算画像和原调度器的TP8稠密请求中，相对新执行的ns-3通信参考模型，
冻结通信校准后的验证集请求E2E平均相对误差降低。** PD、MoE、联合场景和真实硬件精度仍未验收。
