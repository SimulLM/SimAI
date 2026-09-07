# W1-M4-20260907-01：解析主基线实验记录

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M4-20260907-01` |
| 负责人 | 成员四 |
| 日期与时区 | 2026-09-07，Asia/Shanghai（UTC+08:00） |
| 实验目的 | 验证固定版本的 SimAI analytical 后端能完成计划规定的主通信基线，并生成可校验结果 |
| 任务类别 | 构建 + 主基线 |
| 通过标准 | 构建和运行退出码均为 0；输出存在、可解析且 SHA-256 可记录；保存运行成本与结果边界 |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | Ubuntu 24.04.4 LTS，WSL2，x86-64 |
| 内核 | `6.18.33.2-microsoft-standard-WSL2` |
| CPU/逻辑核数 | AMD Ryzen 7 9800X3D；16 逻辑核 |
| 内存 | 30 GiB；采集时可用 29 GiB |
| 可用磁盘 | ext4 `/dev/sdd`；采集时可用 954 GiB |
| GCC/G++ | 13.3.0 / 13.3.0 |
| CMake | 3.28.3 |
| Python/pip/pytest | Python 3.12.3；本实验不依赖 pip/pytest |
| 其他关键依赖 | GNU Make 4.3；未安装 ninja |

## 3. 版本与工作区

| 字段 | 内容 |
|---|---|
| 顶层 Git SHA | `cf9ed25e41887a633c220ba1661a995ccab6d131` |
| `SimCCL` SHA | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` |
| `aicb` SHA | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` |
| `ns-3-alibabacloud` SHA | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` |
| 当前分支 | `master` |
| 工作区是否干净 | 构建和主运行时干净；后续为 PD 测试新增未跟踪目录 `vidur-alibabacloud/.venv-week1/`，不修改源码和本记录结果 |

## 4. 输入与配置

| 文件或参数 | 值 | SHA-256/来源 |
|---|---|---|
| 输入工作负载 | `example/workload_analytical.txt` | `8c2e255aa7397d8c5c7e01daa04d4b3c97a6b015a27bd425770ef8e7e5cbe0a1` |
| 网络/拓扑配置 | `example/busbw.yaml` | `ae063b004c098c15f3e5e3cf78c037f13187a06f5394499a876b8c86094a1a87` |
| 运行参数 | `-g 9216 -nv 360 -nic 48.5 -n_p_s 8 -g_p_s 8 -r example-` | 第一周计划规定命令 |
| 随机种子 | `N/A` | analytical 主命令无随机参数，输入为固定文本 |

完整输入哈希命令：

```bash
sha256sum example/workload_analytical.txt example/busbw.yaml
```

## 5. 执行记录

| 字段 | 内容 |
|---|---|
| 完整命令 | 见下方原文 |
| 工作目录 | `/root/SimAI-week1` |
| 开始时间 | `N/A`（引入本模板前未单独记录） |
| 结束时间 | 2026-09-07 21:43:31 +08:00（结果文件时间） |
| Wall time | 1.24 s |
| 退出码 | 构建 0；主运行 0 |
| stdout 日志 | 未单独归档；关键结束信息见下方摘录 |
| stderr 日志 | 未单独归档；构建仅有上游编译警告，无编译错误 |
| 结果目录/文件 | `/root/SimAI-week1/results/example-EndToEnd.csv` |

```bash
./scripts/build.sh -c analytical
/usr/bin/time -f 'ELAPSED=%e\nMAX_RSS_KB=%M\nEXIT=%x' \
  ./bin/SimAI_analytical \
  -w ./example/workload_analytical.txt \
  -g 9216 -nv 360 -nic 48.5 -n_p_s 8 -g_p_s 8 \
  -r example-
```

## 6. 结果

| 指标或检查项 | 实际结果 | 单位/口径 | 是否达到通过标准 |
|---|---|---|---|
| 构建完成度 | 100%，退出码 0 | analytical 后端 | 是 |
| 主运行状态 | `SimAI-Analytical finished.`，退出码 0 | 进程状态 | 是 |
| 输出规模 | 1,792 | CSV 行（含表头/汇总，以文件行数计） | 是 |
| 输出 SHA-256 | `b3d73975f0081c119094852f15b7926b288afb33b337aa19fd46ed6a20acdd69` | 原始字节哈希 | 是 |
| 峰值 RSS | 7,620 | KiB，`/usr/bin/time` |
| Summary total time | 7,545,619 | 输出文件原始时间单位 | 是 |
| Total computation | 4,542,795（60.20%） | 输出汇总 | 是 |
| Total exposed communication | 2,656,839（35.21%） | 输出汇总 | 是 |
| Bubble time | 345,984（4.59%） | 输出汇总 | 是 |

关键输出摘录：

```text
SimAI-Analytical finished.
ELAPSED=1.24
MAX_RSS_KB=7620
EXIT=0
```

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | `N/A`（最终构建与运行均成功） |
| 错误原文 | `N/A` |
| 最小复现步骤 | 运行第 5 节两条命令 |
| 已排查项 | 退出码、结束标记、输出存在性、行数、SHA-256、运行成本 |
| 尚未排查项 | 无通信/零字节行的 `-nan` 带宽尚未在上游输出中消除；后续解析需转为缺失值 |
| 关联 Issue | `N/A`（第一周只记录边界，未新建议题） |
| 是否修改核心逻辑 | 否 |

## 8. 结论与边界

- 结论：固定版本的 analytical 后端可以复现构建并完成主通信基线。
- 本次结果能够验证：程序可运行、固定输入能产生稳定结果，以及计算/暴露通信/气泡时间的汇总。
- 本次结果不能验证：真实 LLM serving 的 TTFT/TPOT、ns-3 网络精度、真实多节点 MoE 偏斜影响。
- 与其他成员结果的可比性：只有在相同 Git/子模块 SHA、输入哈希和完整参数下才可直接比较。
- 后续动作与负责人：成员四在第二周校准解析器时将 `-nan` 归一化为缺失值，并为后续运行保存完整日志。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 成员四，2026-09-07 |
| 成员一审核 | 待审核 |
| 审核意见 | 待填写 |
