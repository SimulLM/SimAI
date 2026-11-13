# 实验记录：W1-M2-20260903-04

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M2-20260903-04` |
| 负责人 | 成员二 |
| 日期与时区 | 2026-09-03，时区未记录 |
| 实验目的 | 验证 analytical 路径能够读取并执行主通信 workload |
| 任务类别 | 主基线 |
| 通过标准 | workload 成功完成，集合通信统计输出，出现 `SimAI-Analytical finished.` |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | WSL Ubuntu；具体版本待补证 |
| 内核 | N/A |
| CPU/逻辑核数 | N/A |
| 内存 | N/A |
| 可用磁盘 | N/A |
| GCC/G++ | N/A |
| CMake | N/A |
| Python/pip/pytest | N/A |
| 其他关键依赖 | `bin/SimAI_analytical` |

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
| 输入工作负载 | `example/workload_analytical.txt` | 仓库文件，哈希未记录 |
| 网络/拓扑配置 | analytical 自动带宽参数 | 不适用 ns-3 拓扑 |
| 其他配置 | `-g 9216 -nv 360 -nic 48.5 -n_p_s 8 -g_p_s 8 -r example-` | 命令原文 |
| 随机种子 | N/A；原记录未说明随机性 | N/A |

## 5. 执行记录

| 字段 | 内容 |
|---|---|
| 完整命令 | 见下方原文 |
| 工作目录 | `/mnt/c/code/SimInfer-NJUISE` |
| 开始时间 | 2026-09-03 约 21:02；结束时间约 21:02 |
| Wall time | N/A |
| 退出码 | 成功状态由日志确认，原始 shell 退出码未保存 |
| stdout 日志 | `results/W1-M2-20260903-04_workload_analytical.log` |
| stderr 日志 | N/A |
| 结果目录/文件 | `example-` 前缀对应的 analytical 输出 |

```bash
cd /mnt/c/code/SimInfer-NJUISE
./bin/SimAI_analytical \
  -w ./example/workload_analytical.txt \
  -g 9216 \
  -nv 360 \
  -nic 48.5 \
  -n_p_s 8 \
  -g_p_s 8 \
  -r example-
```

## 6. 结果

| 指标或检查项 | 实际结果 | 单位/口径 | 是否达到通过标准 |
|---|---:|---|---|
| workload 打开 | 成功 | 日志 | 是 |
| 模拟完成 | `4542800844` | 日志 tick | 是 |
| 集合通信类型 | AllReduce/AllGather/ReduceScatter/AllToAll | 日志实现类型 | 是 |
| `ALLTOALL_EP` 出现 | 是 | workload 语义 | 是 |
| `SimAI-Analytical finished.` | 出现 | 日志 | 是 |

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | N/A |
| 错误原文 | N/A |
| 最小复现步骤 | 执行第 5 节命令 |
| 已排查项 | workload 打开、通信类型识别、全流程结束 |
| 尚未排查项 | analytical/ns-3 精度差异、复杂 MoE 拥塞 |
| 关联 Issue | N/A |
| 是否修改核心逻辑 | 否 |

## 8. 结论与边界

- 结论：主 analytical 通信基线运行成功。
- 本次结果能够验证：主 workload 可执行，集合通信实现路径可启动并完成。
- 本次结果不能验证：ns-3 分组级行为、复杂专家负载偏斜和请求级回写。
- 与其他成员结果的可比性：使用第一周统一主 workload，可作为成员二通信基线。
- 后续动作与负责人：成员二继续做 AllToAll/EP 最小对照和 ns-3 分析。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 待填写 |
| 成员一审核 | 待审核 |
| 审核意见 | 原始记录保留；本文件仅规范字段格式。 |
