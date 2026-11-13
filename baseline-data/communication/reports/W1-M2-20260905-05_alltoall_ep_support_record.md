# 实验记录：W1-M2-20260905-05

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M2-20260905-05` |
| 负责人 | 成员二 |
| 日期与时区 | 2026-09-05，时区未记录 |
| 实验目的 | 对比最小 `ALLTOALL` / `ALLTOALL_EP` 在 analytical 和 ns-3 中的基础执行路径 |
| 任务类别 | 其他：AllToAll/EP 支持验证 |
| 通过标准 | 两类 workload 均被识别，ns-3 collective=1、stream 完成率=100%，EndToEnd CSV 非空 |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | Windows 主机 + WSL/Linux；具体版本待补证 |
| 内核 | N/A |
| CPU/逻辑核数 | N/A |
| 内存 | N/A |
| 可用磁盘 | N/A |
| GCC/G++ | N/A |
| CMake | N/A |
| Python/pip/pytest | Python3 可调用；版本待补证 |
| 其他关键依赖 | `SimAI_analytical`、`SimAI_simulator`、8 GPU H20 Rail 拓扑 |

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
| 普通 workload | `example/workload_alltoall_minimal.txt` | 仓库新增文件，哈希未记录 |
| EP workload | `example/workload_alltoall_ep_minimal.txt` | 仓库新增文件，哈希未记录 |
| 网络/拓扑配置 | `Rail_Opti_SingleToR_8g_8gps_200Gbps_H20` | 8 GPU H20 拓扑 |
| 其他配置 | `SimAI.conf`、`-t 8`、`AS_SEND_LAT=3 AS_NVLS_ENABLE=1` | 命令原文 |
| 随机种子 | N/A；原记录未说明随机性 | N/A |

## 5. 执行记录

### analytical

```bash
./bin/SimAI_analytical \
  -w ./example/workload_alltoall_minimal.txt \
  -g 8 -nv 8 -nic 100 -n_p_s 8 -g_p_s 1 -r alltoall-minimal-

./bin/SimAI_analytical \
  -w ./example/workload_alltoall_ep_minimal.txt \
  -g 8 -nv 8 -nic 100 -n_p_s 1 -g_p_s 8 -r alltoall-ep-minimal-
```

### ns-3

```bash
AS_SEND_LAT=3 AS_NVLS_ENABLE=1 ./bin/SimAI_simulator -t 8 \
  -w ./example/workload_alltoall_minimal.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c astra-sim-alibabacloud/inputs/config/SimAI.conf

AS_SEND_LAT=3 AS_NVLS_ENABLE=1 ./bin/SimAI_simulator -t 8 \
  -w ./example/workload_alltoall_ep_minimal.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c astra-sim-alibabacloud/inputs/config/SimAI.conf
```

| 字段 | 内容 |
|---|---|
| 工作目录 | `/mnt/c/code/SimInfer-NJUISE` |
| 开始/结束时间 | 原始记录未完整保存 |
| Wall time | N/A |
| 退出码 | 成功状态由日志和输出确认，原始 shell 退出码未单独保存 |
| stdout/stderr | 各场景 `run.log`，stderr 合并记录 |
| 结果目录 | `results/W1-M2-20260905-05_alltoall*` |

## 6. 结果

| 场景 | analytical Total time | ns-3 Total time | collective | stream 完成率 | 是否通过 |
|---|---:|---:|---:|---:|---|
| `ALLTOALL` | 25 | 52 | 1 | 100% | 是 |
| `ALLTOALL_EP` | 3030 | 45 | 1 | 100% | 是 |

相对差异：

- `ALLTOALL`：`abs(52-25)/25 = 108.00%`；
- `ALLTOALL_EP`：`abs(45-3030)/3030 = 98.51%`。

关键结果文件：

- `results/W1-M2-20260905-05_alltoall/ns3_rail8/ncclFlowModel_EndToEnd.csv`；
- `results/W1-M2-20260905-05_alltoall_ep/ns3_rail8_tp2_ep4/ncclFlowModel_EndToEnd.csv`。

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | 初次 ns-3 运行阶段 |
| 错误原文 | `std::bad_array_new_length`；8 GPU workload 使用 128 GPU 拓扑 |
| 最小复现步骤 | 使用 128 GPU Spectrum-X 拓扑运行 8 GPU workload |
| 已排查项 | 将 `-t 16` 改为 `-t 8` 仍失败，随后改用匹配的 8 GPU拓扑成功 |
| 尚未排查项 | EP 组映射的最终精度解释、Vidur AllToAll/EP 回写 |
| 关联 Issue | N/A |
| 是否修改核心逻辑 | 否 |

另一次 EP 配置问题：`TP=1, EP=8` 会产生 `all dims disabled` 和 `collective=0`；修正为 `TP=2, EP=4` 后成功。

## 8. 结论与边界

- 结论：两类最小 AllToAll workload 均通过 analytical 和 ns-3 基础验证。
- 本次结果能够验证：语义识别、AllToAll flow 生成、ns-3 collective 完成和 EndToEnd CSV 输出。
- 本次结果不能验证：复杂 MoE 负载偏斜、真实分组级拥塞和 Vidur 请求级 AllToAll/EP 回写。
- 与其他成员结果的可比性：两类实验使用相同 8 GPU 规模和匹配拓扑；不同后端统计口径仍需进一步核对。
- 后续动作与负责人：成员二执行拥塞场景并设计 Vidur 回写接口。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 待填写 |
| 成员一审核 | 待审核 |
| 审核意见 | 原始实验报告和 CSV 不变，本文件仅按统一模板重新编排。 |
