# 实验记录：W1-M2-20260905-02

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M2-20260905-02` |
| 负责人 | 成员二 |
| 日期与时区 | 2026-09-05，时区未记录 |
| 实验目的 | 验证 ns-3 路径能运行 `microAllReduce` 并生成有效通信统计 |
| 任务类别 | 通信冒烟 |
| 通过标准 | workload 正常完成、stream 完成率 100%、CSV 非空 |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | Windows 主机 + WSL Ubuntu；具体版本待补证 |
| 内核 | N/A |
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
| 网络/拓扑配置 | `Rail_Opti_SingleToR_8g_8gps_200Gbps_H20` | 使用 8 GPU H20 拓扑 |
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
| 退出码 | 0/成功状态由日志确认，原始 shell 退出码未单独保存 |
| stdout 日志 | `results/W1-M2-20260905-02_ns3_microAllReduce.log` |
| stderr 日志 | 合并到 stdout 日志 |
| 结果目录/文件 | 根目录 `ncclFlowModel_*.csv`，并已归档到 `results/` |

```bash
cd /mnt/c/code/SimInfer-NJUISE
python3 ./astra-sim-alibabacloud/inputs/topo/gen_Topo_Template.py \
  --ro -g 8 -gt H20 -bw 200Gbps -nvbw 2400Gbps

./bin/SimAI_simulator -t 8 \
  -w ./example/microAllReduce.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c ./astra-sim-alibabacloud/inputs/config/SimAI.conf
```

## 6. 结果

| 指标或检查项 | 实际结果 | 单位/口径 | 是否达到通过标准 |
|---|---:|---|---|
| Total streams injected | 2 | streams | 是 |
| Total streams finished | 2 | streams | 是 |
| Percentage of finished streams | 100% | 完成率 | 是 |
| total exposed comm | 388292.026 | EndToEnd CSV 统计单位 | 是 |
| total comp | 1112.004 | EndToEnd CSV 统计单位 | 是 |
| total time | 389404.030 | EndToEnd CSV 统计单位 | 是 |
| detailed flows | 已生成 | CSV | 是 |
| dimension utilization | 已生成 | CSV | 是 |

关键输出文件：

- `ncclFlowModel_EndToEnd.csv`
- `ncclFlowModel_detailed_9.csv`
- `ncclFlowModel_detailed_flows.csv`
- `ncclFlowModel_test1_dimension_utilization_0.csv`

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | N/A |
| 错误原文 | N/A |
| 最小复现步骤 | 执行第 5 节命令 |
| 已排查项 | workload、拓扑、配置和 ns-3 输出均已验证 |
| 尚未排查项 | 更大规模拓扑、拥塞场景和请求级回写 |
| 关联 Issue | N/A |
| 是否修改核心逻辑 | 否 |

## 8. 结论与边界

- 结论：`microAllReduce` ns-3 冒烟测试成功。
- 本次结果能够验证：基础 collective、流完成、EndToEnd、详细 flow 和维度利用率输出。
- 本次结果不能验证：AllToAll/EP、热点拥塞和 Vidur 请求级回写。
- 与其他成员结果的可比性：使用统一 8 GPU H20 拓扑和固定输入，可作为通信冒烟基线。
- 后续动作与负责人：成员二继续完成 AllToAll/EP 和拥塞方案验证。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 待填写 |
| 成员一审核 | 待审核 |
| 审核意见 | 建议作为 microAllReduce 成功主记录；原始 Markdown 保留不变。 |
