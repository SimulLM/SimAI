# D：原请求调度接入

已接入原 `python -m vidur.main`，使用execution_mode=dag_expanded、Splitwise全局/副本调度和显式dag_pd_config。

新增配置校验拒绝非PD集群、非Splitwise调度、异构或与公共TP/PP不一致的分片配置、不一致P/D副本数量及PD+MoE组合。KV dtype必须与副本配置相同。CLI仍使用原请求生成器、预测器、Stage执行和Token推进。

Splitwise副本调度在PD模式委托协调层准入与组批。Prefill完成后保留源分配，创建容量等待记录。目标预留成功提交传输DAG。所有传输完成并commit后，设置实际decode_arrived_at，将请求加入Decode队列并唤醒原ReplicaScheduleEvent。

普通队列和恢复队列都经过KVReady检查；请求未就绪时可以跳过，让其他已就绪请求前进。首次Decode时间在原Stage实际启动回调记录，包含启动前的资源等待，不以组批时刻代替。

CSV回放在输入边界把Token转换为Python整数，避免pandas.iterrows把整数字段提升为浮点。Prefill已生成全部输出时允许decode_time=0，释放源容量后直接结束，不创建无消费者传输；原Token总数语义保持一致。

原CLI开发验收五组通过：单请求、双请求、目标容量背压、TP2/PP2、无需后续Decode。合成画像仅提供功能证据。正式验收在最终源码冻结后重新运行。
