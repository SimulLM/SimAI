# 阶段6：PD分离

开发分支dev-v6，基于dev-v7的8e64002。原入口已实现Prefill→KV传输DAG→目标提交→KVReady→Decode，复用同一执行器、容量管理器、Simulator时钟和事件堆。

| 工作包 | 说明 |
|---|---|
| A：配置与布局 | [01-config-and-kv-layout.md](01-config-and-kv-layout.md) |
| B：容量生命周期 | [02-kv-lifecycle.md](02-kv-lifecycle.md) |
| C：传输与事件 | [03-transfer-dag-and-events.md](03-transfer-dag-and-events.md) |
| D：调度接入 | [04-scheduler-integration.md](04-scheduler-integration.md) |
| E：故障和边界 | [05-failure-and-boundaries.md](05-failure-and-boundaries.md) |
| F：验收与交接 | [06-acceptance-and-handoff.md](06-acceptance-and-handoff.md) |

## 配置与支持范围

原CLI增加 `--dag_pd_config <JSON>`。必须使用dag_expanded和Splitwise全局/副本调度，配置真实P/D副本分组。示例见 [example.json](../../../configs/dag/phase6/example.json)。计算/通信画像和其余参数沿用原CLI。

首版支持同构P/D的TP/PP、整块最大序列预分配、完整Prefill、逐Token Decode和可配置共享端点。每分片容量使用配置与原块池约束的较小值。KV dtype须与replica_config_pd_p2p_comm_dtype一致，wire dtype与存储dtype相同。GQA/MQA在TP大于KV heads时显式按rank复制，支持均匀分片/复制，不支持非整除布局。

异构P/D、跨dtype转换、请求重启、迁移重试和PD+MoE组合启动时拒绝或在遇到不支持的工作时明确失败。原非PD与动态MoE路径保留。网络是许可争用加固定费用模型，不模拟流级带宽共享；独立端点并发时不宣称具备完整拓扑带宽约束。

## 生命周期与费用

源容量在Prefill准入时占用；Prefill完成pin源分配。目标容量不足时保留源KV并背压P端。所有目标分片预留成功后提交每个PP Stage的通信图。全部terminal完成安排一次接收提交，目标commit不重复扣容量；释放源后发布KVReady并允许Decode。Decode复用已有分配，请求完成释放目标。

传输有效Token为Prefill输入Token，排除尚未经过下一轮前向的首个输出Token。wire bytes不含空闲预分配块。每分片费用为latency_s + wire_bytes / bandwidth_bytes_per_s。传输费用记录在独立PD图中，不重复计入Stage模型计算费用。请求E2E由宿主实际时间推进自然包含等待与传输。

## 运行与验证

依赖见scripts/dag_phase4/requirements.txt。完整命令、退出码和产物规则见F文档。每次使用新的results/dag/phase6目录；结果与缓存默认不提交。

主要实现为vidur/dag/pd.py、kv_layout.py、pd_lifecycle.py、pd_host.py，测试位于tests/dag/test_pd_*.py。v1公共schema、协议和原执行器字段保持兼容。非Stage宿主图使用独立排序anchor，原Stage的排序身份保持原行为。

正式结果在最终验收后补充独立ACCEPTANCE记录。没有匹配PD测量/模拟参考，功能通过与精度阻塞分别交付，不能据此声称硬件预测精度提升。
