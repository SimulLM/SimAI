# 实验记录：成员四第一周成果复核

> 本记录依据第一周实际完成的构建、测试、仿真与分析结果填写。未在原始执行过程中保存的信息不作推测，以 `N/A` 标记并说明原因。

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M4-20260907-01` |
| 负责人 | 成员四 |
| 日期与时区 | 2026-09-07，Asia/Shanghai（UTC+08:00） |
| 实验目的 | 复核成员四第一周环境、SimAI analytical 主基线、Vidur PD 测试以及 workload/trace/MoE 分析成果是否可复现 |
| 任务类别 | 环境检查 / 构建 / 主基线 / Vidur PD / trace 解析 / 其他（MoE 偏斜场景生成） |
| 通过标准 | 固定代码、子模块和输入哈希；构建与运行退出码为 0；指定测试全部通过；三项分析脚本重跑后生成文件无 Git 差异；结果、限制和未完成边界均有记录 |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | Ubuntu 24.04.4 LTS，WSL2，x86-64 |
| 内核 | `6.18.33.2-microsoft-standard-WSL2` |
| CPU/逻辑核数 | AMD Ryzen 7 9800X3D 8-Core Processor；16 逻辑核 |
| 内存 | 30 GiB；复核采集时可用 29 GiB |
| 可用磁盘 | ext4 `/dev/sdd`；复核采集时可用 954 GiB |
| GCC/G++ | 13.3.0 / 13.3.0 |
| CMake | 3.28.3 |
| Python/pip/pytest | Python 3.12.3 / pip 24.0 / pytest 9.1.1 |
| 其他关键依赖 | GNU Make 4.3；networkx 3.6.1；Vidur 测试使用隔离环境 `.venv-week1`；未安装 ninja |

环境采集命令：

```bash
uname -a
cat /etc/os-release
lscpu
free -h
df -h .
gcc --version
g++ --version
cmake --version
python3 --version
vidur-alibabacloud/.venv-week1/bin/python -m pip --version
vidur-alibabacloud/.venv-week1/bin/python -m pytest --version
```

## 3. 版本与工作区

| 字段 | 内容 |
|---|---|
| 顶层 Git SHA | `cf9ed25e41887a633c220ba1661a995ccab6d131` |
| `SimCCL` SHA | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` |
| `aicb` SHA | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` |
| `ns-3-alibabacloud` SHA | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` |
| 当前分支 | 正式验收克隆为 `master`；成果提交分支为 `smwy/week1` |
| 工作区是否干净 | 构建与 analytical 主运行时干净；安装测试依赖后仅有未跟踪目录 `vidur-alibabacloud/.venv-week1/`，其中为隔离环境，不修改源码与结果逻辑 |

```bash
git branch --show-current
git rev-parse HEAD
git submodule status --recursive
git status --short
```

## 4. 输入与配置

| 文件或参数 | 值 | SHA-256/来源 |
|---|---|---|
| 输入工作负载 | `example/workload_analytical.txt` | `8c2e255aa7397d8c5c7e01daa04d4b3c97a6b015a27bd425770ef8e7e5cbe0a1` |
| 网络/拓扑配置 | `example/busbw.yaml` | `ae063b004c098c15f3e5e3cf78c037f13187a06f5394499a876b8c86094a1a87` |
| 最小通信输入 | `example/microAllReduce.txt` | `5aea5b1afc033d4423897323348c0ed8eac6596ef7b5ce66a6017c259c0caae2` |
| Vidur PD 测试 | `vidur-alibabacloud/tests/test_pd_separation.py` | `c1d627de37e60c309c7d9101f4de082083b1ac5df0615ec029bfb1d9b9e203a5` |
| analytical 参数 | `-g 9216 -nv 360 -nic 48.5 -n_p_s 8 -g_p_s 8 -r example-` | 第一周计划规定命令 |
| MoE 场景 | uniform / hotspot / long_tail；固定总 assignment | `scripts/generate_moe_skew_scenarios.py` 与生成的 JSON/CSV |
| 随机种子 | MoE 场景使用脚本固定 seed；analytical 与 PD 测试无随机参数 | 脚本与完整命令 |

完整输入哈希命令与输出：

```text
$ sha256sum example/workload_analytical.txt example/busbw.yaml \
    example/microAllReduce.txt vidur-alibabacloud/tests/test_pd_separation.py
8c2e255aa7397d8c5c7e01daa04d4b3c97a6b015a27bd425770ef8e7e5cbe0a1  example/workload_analytical.txt
ae063b004c098c15f3e5e3cf78c037f13187a06f5394499a876b8c86094a1a87  example/busbw.yaml
5aea5b1afc033d4423897323348c0ed8eac6596ef7b5ce66a6017c259c0caae2  example/microAllReduce.txt
c1d627de37e60c309c7d9101f4de082083b1ac5df0615ec029bfb1d9b9e203a5  vidur-alibabacloud/tests/test_pd_separation.py
```

## 5. 执行记录

| 字段 | 内容 |
|---|---|
| 完整命令 | 见下方原文 |
| 工作目录 | Linux 基线：`/root/SimAI-week1`；分析脚本：当前 `smwy/week1` 仓库根目录 |
| 开始时间 | `N/A`（本模板在执行完成后补充，原始过程未单独保存开始时刻） |
| 结束时间 | analytical 输出文件：2026-09-07 21:43:31 +08:00；其余任务只保留日期，未保留精确时刻 |
| Wall time | analytical 1.24 s；Vidur pytest 0.13 s；三个分析脚本未独立计时 |
| 退出码 | analytical 构建 0；主运行 0；Vidur PD pytest 0；三个分析脚本均为 0 |
| stdout 日志 | 未单独保存完整日志；关键输出摘录见第 6 节，结构化结果已提交至 `docs/data/` |
| stderr 日志 | 未单独保存；构建存在上游代码警告但无编译错误，测试与分析脚本无失败输出 |
| 结果目录/文件 | Linux：`results/example-EndToEnd.csv`；仓库：`docs/data/` 下 workload、DeepSeek trace 和 MoE 场景 JSON/CSV |

```bash
cd /root/SimAI-week1
./scripts/build.sh -c analytical
/usr/bin/time -f 'ELAPSED=%e\nMAX_RSS_KB=%M\nEXIT=%x' \
  ./bin/SimAI_analytical \
  -w ./example/workload_analytical.txt \
  -g 9216 -nv 360 -nic 48.5 -n_p_s 8 -g_p_s 8 \
  -r example-

cd /root/SimAI-week1/vidur-alibabacloud
python3 -m venv .venv-week1
.venv-week1/bin/python -m pip install pytest networkx
.venv-week1/bin/python -m pytest tests/test_pd_separation.py -q

# 在成果仓库根目录重跑成员四分析脚本
python scripts/analyze_workload.py
python scripts/analyze_deepseek_trace.py
python scripts/generate_moe_skew_scenarios.py
git diff -- docs/data
```

## 6. 结果

| 指标或检查项 | 实际结果 | 单位/口径 | 是否达到通过标准 |
|---|---|---|---|
| analytical 构建 | 构建至 100%，退出码 0 | 构建状态 | 是 |
| analytical 主运行 | `SimAI-Analytical finished.`，退出码 0 | 进程状态 | 是 |
| analytical 结果规模 | 1,792 | `example-EndToEnd.csv` 文件行数 | 是 |
| analytical 结果 SHA-256 | `b3d73975f0081c119094852f15b7926b288afb33b337aa19fd46ed6a20acdd69` | 原始字节哈希 | 是 |
| analytical 峰值 RSS | 7,620 | KiB，`/usr/bin/time` | 是 |
| Summary total time | 7,545,619 | 输出文件原始时间单位 | 是 |
| Total computation | 4,542,795（60.20%） | 输出汇总 | 是 |
| Total exposed communication | 2,656,839（35.21%） | 输出汇总 | 是 |
| Bubble time | 345,984（4.59%） | 输出汇总 | 是 |
| Vidur PD 测试 | 10 passed，0 failed | pytest case | 是 |
| 主 workload 解析 | 1,789 条记录、12 字段；AllToAll 18 GiB、EP 72 GiB | 脚本生成摘要 | 是 |
| DeepSeek trace 解析 | EP32/EP128、Prefill/Decode 关键事件及 overlap 摘要已生成 | 行为级 trace 分析 | 是 |
| MoE 偏斜场景 | uniform/hotspot/long_tail 三组，固定总量与 seed | 可控假设数据 | 是 |
| 分析脚本确定性 | 重跑后 `docs/data/` 无 Git 内容差异 | 生成文件一致性 | 是 |

关键输出摘录：

```text
SimAI-Analytical finished.
ELAPSED=1.24
MAX_RSS_KB=7620
EXIT=0

..........                                                               [100%]
10 passed in 0.13s
```

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | 初始 Vidur 依赖检查；最终构建、运行和测试均成功 |
| 错误原文 | 系统 Python 初始未安装 pytest；analytical 输出的无通信/零字节行存在 `-nan` 带宽 |
| 最小复现步骤 | 在 `vidur-alibabacloud` 目录直接执行 `python3 -m pytest tests/test_pd_separation.py -q` 可复现缺少 pytest；运行第 5 节 analytical 命令可观察零字节行的 `-nan` |
| 已排查项 | 创建隔离 venv 并安装 pytest/networkx；复核 Git/子模块 SHA、输入哈希、退出码、结果行数与输出哈希；确认 `-nan` 只出现在不适用通信行 |
| 尚未排查项 | 上游 analytical 对零字节行的输出格式；完整 Vidur 测试套件；真实 GPU/RDMA 多节点性能 |
| 关联 Issue | `N/A`（第一周记录问题边界，未创建新 Issue） |
| 是否修改核心逻辑 | 否 |

## 8. 结论与边界

- 结论：成员四第一周要求的环境基线、analytical 主运行、Vidur PD 指定测试、workload/trace 分析和 MoE 偏斜方案均已完成并可按记录复核。
- 本次结果能够验证：固定版本和输入下的 analytical 可运行性与汇总结果；Vidur PD 配置逻辑；分析脚本生成结果的一致性；DeepSeek 事件顺序及可见 overlap；三种 MoE 偏斜假设的守恒性。
- 本次结果不能验证：真实 LLM serving 的 TTFT/TPOT、真实网络绝对时延、ns-3 与 analytical 的精度闭环、动态 EP 矩阵、真实热点/长尾路由对 P99 的绝对影响。
- 与其他成员结果的可比性：只有在相同顶层与子模块 SHA、相同输入哈希、相同命令和指标定义下可直接比较；DeepSeek 公开 trace 当前仅用于行为级校准。
- 后续动作与负责人：成员四在后续迭代中保存每次运行的完整 stdout/stderr 与精确起止时间，将 `-nan` 归一化为缺失值，并在取得真实或 ns-3 对照后填写绝对/相对误差。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 成员四，2026-09-07 |
| 成员一审核 | 待审核 |
| 审核意见 | 待填写 |
