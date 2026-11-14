# 第七阶段：动态 MoE

开发分支为 `dev-v7`，基于阶段五交接提交 `e4b89ad`。本阶段实现可执行的动态子图，
与阶段六并列，不包含 PD 或 PD+MoE 联合验收。

## 已实现的路径

原入口 `python -m vidur.main` 使用 `--execution_mode dag_expanded`，再增加
`--dag_moe_config <JSON>` 即启用动态 MoE。不提供此选项时仍走阶段五路径；
`legacy` 和 `dag_coarse` 不接受此选项。

每个副本的 batch/iteration 独立编号，每层最初只有 `route → join → 后续层`。
路由完成事件到达后，宿主先生成、校验并原子追加下面的分支，再将 route 完成交给执行核：

```text
route → dispatch(source,destination) → expert.up → expert.down
                                             → combine(destination,source) → join
```

本地赋值保留在完整矩阵中，省去跨设备 dispatch/combine；本地 Expert 的 down 直接汇入 join。
同一设备上的多个 Expert 分别估时、共享 GPU 许可；不同设备可并行。
同一个源/目标对的通信按完整赋值矩阵聚合，combine 等该对所需的全部 Expert down。
空载 Expert 计数为零，不创建计算任务或收取最低费用。up 费用应覆盖该 Expert 的
上投影、门控/激活等前半段计算，down 覆盖下投影，不能在其他节点重复收费。

一次路由得到不可变 `RoutingResult`，保存 source/token/expert 三元组；up、down、
dispatch、combine 的 metadata 均引用同一 digest。无 drop 时严格校验
`assignments = tokens × top_k`，每 token 选择不同 Expert；输入错误、缺失路由或画像均报错。

动态节点复用原 `DagExecutor.append`、资源管理器、Simulator 时钟和事件队列。
公共 v1 图/资源接口没有修改。阶段五适配器仅提取了构图和初始费用检查两个内部方法；
其原有最终图结算仍用于动态费用、StageEnd 和请求统计，CPU 费用继续通过 `cpu.` 前缀排除。
并行任务费用之和是服务工作量，实际 Stage 耗时由 terminal 时刻决定，两者不应混为一谈。

## 当前支持范围

| 项目 | 支持范围 |
|---|---|
| 执行配置 | TP=1、PP=1、非 PD；一个显式 EP 组覆盖所有配置 GPU |
| Expert 放置 | 每个 EP rank 至少一个 Expert；允许多个 Expert 共卡 |
| batch 阶段 | 独立 prefill/decode；混合 batch 显式拒绝，演示设 batch size cap=1 |
| 实际请求源 | 每个原 Stage 的真实 token 属于该副本 GPU；其他源行计零，不将 token 人为平分 |
| 路由输入 | 均衡、热点、逐轮完整 trace；支持 top-k，无 drop、容量裁剪或重路由 |
| 通信 | 两端端点许可，默认占用两端 GPU；`independent_comm: ["ep"]` 可配置独立通信 |
| 费用 | 秒；payload 为整数 bytes；off-device 费用 = latency + wire bytes / phase bandwidth |
| 原 AICB MoE | 保留独立 attention/MLP，仅替换有 MoE 工作量的层；禁止重复收费 |
| 原 dense 模型 | 仅允许 synthetic 模式，替换 MLP 形成结构测试夹具；不代表 Llama 变成真实 MoE |

这是逻辑 GPU/端点争用模型，不模拟实际 CUDA stream、SM 分区、流级共享带宽或 collective 算法。
原 AICB 层的 MoE compute/EP 均为零时不插入 Expert；整份画像没有有效 MoE 层则拒绝启用。
GPU ID 沿用阶段五的副本映射；两请求可在同一 EP 组争用 Expert，但没有新增原子 EP 组批调度器。
图和逐 token 路由目前随运行保留，超大规模优化和 PD 联合场景留给阶段八。

## 输入与费用证据

示例配置为 [alternating.json](../../../configs/dag/phase7/alternating.json) 和
[resources.json](../../../configs/dag/phase7/resources.json)。四个 Expert 分布在两块逻辑 GPU，
`top_k=2`，每副本按轮交替 balanced/hotspot；热点集中到 e0/e1。
带宽、路由费用、每 assignment 费用和 payload 均是明确标注的合成值。

trace 模式的 `routing.traces[iteration]` 是该轮完整列表，例如：

```json
[{"source": "gpu:0:0:0", "token": 0, "experts": ["e0", "e2"]}]
```

列表必须覆盖该 batch 的全部源 token，同轮每层使用该列表；轮次不足不会回绕复用。
`patterns` 可为 `["balanced"]`、`["hotspot"]`、`["trace"]` 或交替列表。
合成路由器只用于可控实验，未实现实际模型 router 的数值计算。

存在匹配 Expert 画像时，AICB 路径可改用 `cost.mode="profile"`：

- 顶层 `scope` 必须包含 model、device、tp、pp、ep、dtype；前五项核对运行配置。
  dtype 是画像的显式声明，当前运行配置没有独立 dtype 字段，不宣称完成真实硬件精度核验。
- 删除 `up_s_per_assignment` 和 `down_s_per_assignment`，提供 `profiles` 列表。
  每条记录包含 `expert`、`phase`、`assignments`、`up_s`、`down_s`、完全相同的 `scope`、
  `nature`（measured/simulated/estimated）及 `evidence: [{"path": "...", "sha256": "..."}]`。
- 相对证据路径基于 MoE 配置所在目录；文件哈希必须匹配。输出逐任务保留证据路径与哈希。
  所有层共用该配置下同形状 Expert 的画像，异构层需要另行扩展画像键，不能混用。
- 查表键是 `(expert, phase, assignments)`，不插值、不外推、不回退合成函数。
  路由及网络时延仍是显式配置的估计值；Expert 画像匹配不等于端到端精度验证通过。

仓库现有 MoE 目的端负载统计没有完整源/token 路由与匹配时延，不能自动当作画像或真实参考。
当前仅交付逻辑/功能结果；精度报告为 `blocked_missing_matched_moe_reference`，不计算虚构误差。
后续需要一致的模型/设备/TP/PP/EP/dtype、Expert 负载画像、完整路由及独立逐轮/请求时延参考，
并分离校准集和验证集。

## 复现与验收

使用阶段四 Python 3.10+ 环境及 `scripts/dag_phase4/requirements.txt`；开发验证使用 Python 3.12。
从项目根目录运行，不需要实际 GPU 或 CUDA：

```powershell
$env:PYTHONPATH = "$PWD\vidur-alibabacloud;$PWD"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:WANDB_MODE = 'disabled'
python scripts/dag_phase7/main.py --output results/dag/phase7/20261114-phase7-acceptance-01
```

若已使用阶段四的 `.cache/phase4-deps`，将它也加入 PYTHONPATH；或在自己的虚拟环境安装依赖。
Linux 设置等价的 `PYTHONPATH="$PWD/vidur-alibabacloud:$PWD"`。输出目录须不存在，格式为
`results/dag/phase7/YYYYMMDD-phase7-<用途>-NN`。

脚本包含可手算的均衡/热点探针、原始 CLI 两请求多轮 prefill/decode、全部阶段一至五和新增
阶段七回归。原 CLI 使用合成数据训练原预测器，保留组批、token 推进及 StageEnd 原路径。
退出码 **2 表示功能通过但精度参考缺失**；1 表示功能或运行失败。当前没有宣称精度通过的退出 0。

输出包括：

- `acceptance-report.json`、`accuracy-report.json`、`pytest.log/xml`：功能和精度分开报告。
- `controlled-results.json`：均衡/热点耗时、共享资源等待、各 Expert 负载。
- 原 CLI 子目录的 `moe-routing.json`：逐轮完整 RoutingResult、digest 和矩阵；
  `moe-communication-matrix.csv`：含零单元及本地单元的完整矩阵和两个方向的 wire bytes。
- `moe-expert-loads.csv`、`moe-rounds.csv`：up/down 起止、工作量、等待、join 及 Expert 尾差。
- `timeline.csv`、`resource_timeline.csv`、`cost-breakdown.csv`、`graphs/`：最终图与费用对账。
- `moe-task-chrome.json`：所有任务的实际区间，可导入 Perfetto/Chrome trace；原宿主的
  `event_trace.json` 和 `chrome_trace.json` 同时保留。
- `run-manifest.json`：源码、输入/输出哈希、启动时 Git 状态和墙钟。生成目录和缓存不提交源码库。

主要实现：`vidur/dag/moe.py` 为路由/画像契约，`vidur/dag/moe_host.py` 为宿主动态展开，
`tests/dag/test_dynamic_moe.py` 覆盖守恒、矩阵、共卡/异卡、共享资源、join、跨轮、
AICB 旧费用去重、最终结算及失败清理。
