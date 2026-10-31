# W1-M2-20260903-04：workload_analytical analytical 跑通验证

## 1. 实验目的

验证 analytical 路径能够成功读取 workload，并执行通信/空闲/总时长统计，确认当前通信基线已经跑通。

## 2. 实验时间

- 日期：2026-09-03
- 记录时间：2026-09-03 21:02 左右

## 3. 实验环境

- 操作系统：WSL Ubuntu
- 项目目录：/mnt/c/code/SimInfer-NJUISE
- 关键路径：
  - ./bin/SimAI_analytical
  - ./example/workload_analytical.txt

## 4. 实验命令

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

## 5. 关键日志证据

```text
Success in opening workload file
model_parallel_NPU_group is 2
...
all passes finished at time: 4542800844, id of first layer: grad_gather
Time to exit: Thu Sep  3 21:02:19 2026
all-reduce Collective implementation: NcclFlowModel
reduce-scatter Collective implementation: NcclFlowModel
all-gather Collective implementation: NcclFlowModel
all-to-all Collective implementation: NcclFlowModel
Collective optimization: baseline
Total sim duration: 0:0 hours
...
SimAI-Analytical finished.
```

## 6. 关键观察

- workload 文件确实被成功打开，说明输入文件格式可用；
- 程序输出了 `Workload stats`，说明通信相关统计是被计算和记录的；
- 运行了到 `all passes finished at time: 4542800844`，说明模拟过程确实执行完成；
- 最终输出 `SimAI-Analytical finished.`，说明 analytical 路径本次执行成功；
- 输出中包含 `ALLREDUCE`、`ALLGATHER`、`REDUCESCATTER`、`ALLTOALL`、`ALLTOALL_EP` 等通信类别，可用于后续支持分析。

## 7. 结论

本次 analytical 路径已成功运行，且 workload 能被识别并处理，说明当前通信基线已基本跑通。该阶段已完成最关键的前置验证：构建通过、workload 可执行、通信统计有效输出。

## 8. 下一步计划

1. 检查结果文件是否生成；
2. 继续分析 workload 中 `ALLTOALL_EP` 等 MoE 相关通信的真实支持状态；
3. 进行 ns-3 模型编译与对比验证；
4. 将实验结果整理到后续汇报材料中。

---

> 备注：本实验的原始输出已保存在同路径下的日志文件，后续可直接用于复盘和报告撰写。
