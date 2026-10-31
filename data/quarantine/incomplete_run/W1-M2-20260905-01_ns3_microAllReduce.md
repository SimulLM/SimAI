# W1-M2-20260905-01：ns3 microAllReduce 复跑记录

## 1. 实验目的

再次验证 SimAI 的 ns3 仿真路径是否能正常启动，并保留完整日志，以便后续复盘和分析。

## 2. 实验时间

- 日期：2026-09-05
- 运行环境：WSL Ubuntu
- 项目目录：/mnt/c/code/SimInfer-NJUISE

## 3. 实验命令

```bash
cd /mnt/c/code/SimInfer-NJUISE
python3 ./astra-sim-alibabacloud/inputs/topo/gen_Topo_Template.py \
  --ro -g 8 -gt H20 -bw 200Gbps -nvbw 2400Gbps

./bin/SimAI_simulator -t 8 \
  -w ./example/microAllReduce.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c ./astra-sim-alibabacloud/inputs/config/SimAI.conf
```

本次执行额外增加了日志重定向：

```bash
2>&1 | tee ./results/W1-M2-20260905-01_ns3_microAllReduce.log
```

## 4. 实验输出（原始日志）

```text
wsl: 检测到 localhost 代理配置，但未镜像到 WSL。NAT 模式下的 WSL 不支持 localhost 代理。
PWD=/mnt/c/code/SimInfer-NJUISE
total 0
lrwxrwxrwx 1 fuzz fuzz 113 Sep  3 20:51 SimAI_analytical -> /mnt/c/code/SimInfer-NJUISE/astra-sim-alibabacloud/build/simai_analytical/build/simai_analytical/SimAI_analytical
lrwxrwxrwx 1 fuzz fuzz 143 Sep  4 15:47 SimAI_simulator -> /mnt/c/code/SimInfer-NJUISE/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-AstraSimNetwork-debug
asw_switch_num: 8
psw_switch_num: 64
Creating Topology of totally 1 segment(s), totally 1 pod(s).
Rail_Opti_SingleToR_8g_8gps_200Gbps_H20
[MockNcclLog] WARNING: cannot open log file '/etc/astra-sim/SimAI.log'; logging is disabled.
```

## 5. 关键观察

- 该命令在 WSL 环境下确实启动并执行了；
- 输出中已记录拓扑生成信息：`Creating Topology...` 与 `Rail_Opti_SingleToR_8g_8gps_200Gbps_H20`；
- 仅看到一条日志警告：`cannot open log file '/etc/astra-sim/SimAI.log'; logging is disabled.`；
- 当前这次执行没有继续产出期望的 `ncclFlowModel_*.csv` 文件，说明本次运行尚未进入完整的仿真结果输出阶段。

## 6. 结论

本次 ns3 复跑已成功记录日志，且命令运行已启动，但就当前这次输出来看，仿真流程未达到产生 CSV 结果文件的完整状态。也就是说，日志已留档，但“结果生成”还需要进一步排查配置、参数或环境问题。

## 7. 下一步建议

1. 检查 `SimAI_simulator` 是否真的在完整仿真阶段执行，或者是否在启动阶段退出；
2. 检查 `SimAI.conf` 与网络拓扑文件是否匹配；
3. 检查是否需要设置额外环境变量，如 `AS_SEND_LAT`；
4. 若仍无结果，再检查是否有底层 ns3 编译或运行依赖缺失。

---

> 说明：本次的原始日志文件保存为 `./results/W1-M2-20260905-01_ns3_microAllReduce.log`，可直接用于后续复盘和报告。
