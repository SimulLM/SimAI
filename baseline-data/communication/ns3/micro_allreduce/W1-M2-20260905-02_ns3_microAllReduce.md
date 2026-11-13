# W1-M2-20260905-02：ns3 microAllReduce 结果归档与分析

## 1. 实验目标

验证 ns3 路径在实际工作负载上是否能够正常运行，并确认输出结果文件是否正确生成、格式可读、内容合理。

## 2. 实验时间

- 日期：2026-09-05
- 环境：WSL Ubuntu
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

## 4. 实验日志摘要

关键输出如下：

```text
maxRtt=160 maxBdp=48000
Running Simulation.
Success in opening workload file
... 
all passes finished at time: 389404030, id of first layer: embedding_layer
path to create csvs is: ./ncclFlowModel_
success in openning file
Total streams injected: 2
Total streams finished: 2
Percentage of finished streams: 100 %
```

## 5. CSV 结果验证

本次实验生成了如下文件：

- `ncclFlowModel_EndToEnd.csv`
- `ncclFlowModel_detailed_9.csv`
- `ncclFlowModel_detailed_flows.csv`
- `ncclFlowModel_test1_dimension_utilization_0.csv`

其中，`EndToEnd.csv` 内容如下：

```csv
File name, Expose DP comm, Expose DP_EP comm, Expose TP comm, Expose_EP_comm, Expose_PP_comm, bubble time, total comp, total exposed comm, Total time
test1, 0 (0.00%), 0 (0.00%), 388292 (99.71%), 0 (0.00%), 0 (0.00%), 0 (0.00%), 1112 (0.29%), 388292 (99.71%), 389404
layer_name,test1,fwd compute,wg compute,ig compute,fwd exposed comm,wg exposed comm,ig exposed comm,fwd total comm,algbw,busbw,wg total comm,algbw,busbw,ig total comm,algbw,busbw,workload finished at
embedding_layer,test1,556.000000,0.001000,0.001000,222699.464000,0.000000,0.000000,222699.464000,0.070162,0.122783,0.000000,-nan,0.000000,0.000000,-nan,0.000000,389404.030000
embedding_layer,test1,556.000000,0.001000,0.001000,165592.556000,0.000000,0.000000,165592.556000,0.377432,0.660507,0.000000,-nan,0.000000,0.000000,-nan,0.000000,389404.030000
SUM,test1,1112.000000,0.002000,0.002000,388292.020000,0.000000,0.000000,388292.020000,NONE,NONE,0.000000,NONE,NONE,0.000000,NONE,NONE
total exposed comm,388292.026000,total comp,1112.004000,total time,389404.030000
```

可以看到：

- `Total time = 389404`，与日志中的 `all passes finished at time: 389404030` 对应；
- 通信开销完全集中在 `Expose TP comm`，占比约 `99.71%`；
- 这说明在该小规模 AllReduce/TP 工况下，TP 通信是主导因素；
- 文件内容结构完整，说明输出正常。

## 6. detailed flows 验证

`ncclFlowModel_detailed_flows.csv` 的前几行显示了典型 collective flow 信息：

```csv
collective,op,data_size,algorithm,protocol,channel_id,flow_id,src,dest,flow_size,chunk_id,chunk_count,conn_type,parent_flow_ids,prev_flow_ids
TP_0_0_0_3_16777216,3,16777216,1,1,0,0,0,1,262144,0,14,RING,,7
TP_0_0_0_3_16777216,3,16777216,1,1,0,8,0,1,262144,1,14,RING,7,7
...
```

这说明：

- 流量确实被拆解为 point-to-point 记录；
- `algorithm=1`、`protocol=1`、`conn_type=RING` 等字段说明当前实现使用的是 ring 连接模型；
- 该文件的结构完全符合 SimCCL/SimAI 的流模型输出格式。

## 7. utilization 验证

`ncclFlowModel_test1_dimension_utilization_0.csv` 的前几行如下：

```csv
 time (us) ,dim1 util,dim2 util,
10.000000,0.000000,0.000000,
20.000000,0.000000,0.000000,
30.000000,0.000000,0.000000,
...
```

说明该文件是时间轴上的利用率曲线，适合做后续通信利用率分析。

## 8. 归档结果

已将上述 CSV 文件复制到结果目录：

- [results/ncclFlowModel_EndToEnd.csv](../results/ncclFlowModel_EndToEnd.csv)
- [results/ncclFlowModel_detailed_9.csv](../results/ncclFlowModel_detailed_9.csv)
- [results/ncclFlowModel_detailed_flows.csv](../results/ncclFlowModel_detailed_flows.csv)
- [results/ncclFlowModel_test1_dimension_utilization_0.csv](../results/ncclFlowModel_test1_dimension_utilization_0.csv)

## 9. 结论

本次 ns3 仿真已经成功执行，并产生了有效的通信结果与流量拆解输出。输出文件内容结构合理，数值符合预期，说明当前通信基线已完成有效验证。

## 10. 下一步计划

1. 对 `EndToEnd.csv` 和 `detailed_flows.csv` 做更细的定量分析；
2. 对比不同 `AS_SEND_LAT` 或不同拓扑条件下的通信性能；
3. 补充到汇报材料中，作为 ns3 基线实验的证据。
