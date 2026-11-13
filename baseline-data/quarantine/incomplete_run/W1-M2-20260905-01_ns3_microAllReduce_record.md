# 实验记录：W1-M2-20260905-01

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M2-20260905-01` |
| 负责人 | 成员二 |
| 日期与时区 | 2026-09-05，时区未记录 |
| 实验目的 | 复跑 ns-3 `microAllReduce` 并保留启动日志 |
| 任务类别 | 通信冒烟 |
| 通过标准 | 仿真正常完成并生成有效 `ncclFlowModel_*.csv` |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | Windows 主机 + WSL Ubuntu；具体版本待补证 |
| 内核 | N/A（原记录未保存） |
| CPU/逻辑核数 | N/A |
| 内存 | N/A |
| 可用磁盘 | N/A |
| GCC/G++ | N/A |
| CMake | N/A |
| Python/pip/pytest | Python3 可调用；版本待补证 |
| 其他关键依赖 | `SimAI_simulator`、H20 8 GPU 拓扑、`SimAI.conf` |

## 3. 版本与工作区

| 字段 | 内容 |
|---|---|
| 顶层 Git SHA | N/A（原记录未保存） |
| `SimCCL` SHA | N/A |
| `aicb` SHA | N/A |
| `ns-3-alibabacloud` SHA | N/A |
| 当前分支 | N/A |
| 工作区是否干净 | N/A |

## 4. 输入与配置

| 文件或参数 | 值 | SHA-256/来源 |
|---|---|---|
| 输入工作负载 | `example/microAllReduce.txt` | 仓库文件，哈希未记录 |
| 网络/拓扑配置 | `Rail_Opti_SingleToR_8g_8gps_200Gbps_H20` | 本次生成，哈希未记录 |
| 其他配置 | `astra-sim-alibabacloud/inputs/config/SimAI.conf`；`-t 8` | 命令原文 |
| 随机种子 | N/A；原记录未说明随机性 | N/A |

## 5. 执行记录

| 字段 | 内容 |
|---|---|
| 完整命令 | 见下方原文 |
| 工作目录 | `/mnt/c/code/SimInfer-NJUISE` |
| 开始时间 | N/A |
| 结束时间 | N/A |
| Wall time | N/A |
| 退出码 | N/A（原记录未保存） |
| stdout 日志 | `results/W1-M2-20260905-01_ns3_microAllReduce.log` |
| stderr 日志 | 合并到 stdout 日志 |
| 结果目录/文件 | 本次未形成期望的 `ncclFlowModel_*.csv` |

```bash
cd /mnt/c/code/SimInfer-NJUISE
python3 ./astra-sim-alibabacloud/inputs/topo/gen_Topo_Template.py \
  --ro -g 8 -gt H20 -bw 200Gbps -nvbw 2400Gbps

./bin/SimAI_simulator -t 8 \
  -w ./example/microAllReduce.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c ./astra-sim-alibabacloud/inputs/config/SimAI.conf \
  2>&1 | tee ./results/W1-M2-20260905-01_ns3_microAllReduce.log
```

## 6. 结果

| 指标或检查项 | 实际结果 | 单位/口径 | 是否达到通过标准 |
|---|---|---|---|
| ns-3 是否启动 | 是 | 日志出现拓扑生成和启动信息 | 是 |
| `ncclFlowModel_*.csv` | 未生成 | 文件存在性 | 否 |
| 完整仿真结果 | 未确认 | 原始日志 | 否 |

关键输出：

```text
Creating Topology of totally 1 segment(s), totally 1 pod(s).
Rail_Opti_SingleToR_8g_8gps_200Gbps_H20
[MockNcclLog] WARNING: cannot open log file '/etc/astra-sim/SimAI.log'; logging is disabled.
```

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | 运行时/结果输出阶段 |
| 错误原文 | 未发现明确 fatal；出现日志文件权限警告 |
| 最小复现步骤 | 使用上述命令运行同一 workload 和拓扑 |
| 已排查项 | 已确认命令启动并生成拓扑 |
| 尚未排查项 | `SimAI.conf`、环境变量、运行退出原因、底层 ns-3 依赖 |
| 关联 Issue | N/A |
| 是否修改核心逻辑 | 否 |

## 8. 结论与边界

- 结论：ns-3 进程启动并留下日志，但本次没有完成有效 CSV 输出。
- 本次结果能够验证：WSL、拓扑生成和仿真入口可以启动。
- 本次结果不能验证：通信 collective 完成、流完成率和网络统计有效性。
- 与其他成员结果的可比性：不可作为成功冒烟结果；后续 `-02` 记录才是成功主记录。
- 后续动作与负责人：成员二补查运行参数；使用 `W1-M2-20260905-02` 作为成功复现实验。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 待填写 |
| 成员一审核 | 待审核 |
| 审核意见 | 本记录保留为失败/未完成的真实历史记录，不覆盖。 |
