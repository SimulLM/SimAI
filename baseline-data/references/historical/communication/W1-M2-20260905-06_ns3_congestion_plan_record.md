# 实验记录：W1-M2-20260905-06

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M2-20260905-06` |
| 负责人 | 成员二 |
| 日期与时区 | 2026-09-05，时区未记录 |
| 实验目的 | 设计后续使用 ns-3 验证 EP AllToAll 分组级拥塞的初步方案 |
| 任务类别 | 其他：实验方案设计 |
| 通过标准 | 明确场景、控制变量、运行方法、采集指标和拥塞判定标准 |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | N/A；本记录是方案设计，不是运行实验 |
| 内核 | N/A |
| CPU/逻辑核数 | N/A |
| 内存 | N/A |
| 可用磁盘 | N/A |
| GCC/G++ | N/A |
| CMake | N/A |
| Python/pip/pytest | N/A |
| 其他关键依赖 | ns-3 analysis 工具：FCT、队列、带宽、QP/CNP、trace_reader |

## 3. 版本与工作区

| 字段 | 内容 |
|---|---|
| 顶层 Git SHA | N/A |
| `SimCCL` SHA | N/A |
| `aicb` SHA | N/A |
| `ns-3-alibabacloud` SHA | N/A |
| 当前分支 | N/A |
| 工作区是否干净 | N/A |

## 4. 输入与配置

| 文件或参数 | 值 | SHA-256/来源 |
|---|---|---|
| 基础通信输入 | `example/workload_alltoall_ep_minimal.txt` | 已有最小 EP workload |
| 起始拓扑 | `Rail_Opti_SingleToR_8g_8gps_200Gbps_H20` | 8 GPU 基线拓扑 |
| 场景矩阵 | 均衡 `25/25/25/25`；热点 `70/10/10/10`；长尾 `50/25/15/10` | 方案设计值 |
| 随机种子 | 待实验确定；若无随机性需记录依据 | N/A |

## 5. 执行记录

本记录不对应已执行的 ns-3 命令。后续命令模板：

```bash
mkdir -p results/congestion/<scenario>
AS_SEND_LAT=3 AS_NVLS_ENABLE=1 ./bin/SimAI_simulator -t 8 \
  -w ./example/workload_alltoall_ep_<scenario>.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c ./astra-sim-alibabacloud/inputs/config/SimAI.conf \
  2>&1 | tee results/congestion/<scenario>/run.log
cp -f ncclFlowModel_* results/congestion/<scenario>/
```

| 字段 | 内容 |
|---|---|
| 工作目录 | `/mnt/c/code/SimInfer-NJUISE`（计划值） |
| 开始/结束时间 | N/A |
| Wall time | N/A |
| 退出码 | N/A；尚未执行 |
| stdout/stderr | N/A；尚未执行 |
| 结果目录/文件 | `results/congestion/<scenario>/`（计划值） |

## 6. 结果

| 指标或检查项 | 实际结果 | 单位/口径 | 是否达到通过标准 |
|---|---|---|---|
| 均衡场景 | 尚未执行 | N/A | N/A |
| 热点场景 | 尚未执行 | N/A | N/A |
| 长尾场景 | 尚未执行 | N/A | N/A |
| 拥塞指标 | 已定义，未采集 | FCT、队列、带宽、ECN/CNP、trace | 方案通过 |

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | N/A；尚未执行 |
| 错误原文 | N/A |
| 最小复现步骤 | N/A |
| 已排查项 | 已确认仓库存在 FCT、队列、带宽、QP/CNP 和 trace 分析入口 |
| 尚未排查项 | 流量矩阵能否被当前 workload 格式表达；实际拥塞输出 |
| 关联 Issue | N/A |
| 是否修改核心逻辑 | 否 |

## 8. 结论与边界

- 结论：分组级拥塞验证方案已完成设计。
- 本次结果能够验证：后续实验的均衡/热点/长尾分组、控制变量、指标和判定标准。
- 本次结果不能验证：实际队列增长、FCT 长尾、ECN/CNP 或分组级拥塞已经发生。
- 与其他成员结果的可比性：后续应固定 8/16 GPU 拓扑、总通信量和配置。
- 后续动作与负责人：成员二执行三组 ns-3 实验并归档原始 trace/monitor 输出。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 待填写 |
| 成员一审核 | 待审核 |
| 审核意见 | 本记录是方案记录，不能作为已完成拥塞实验结果。 |
