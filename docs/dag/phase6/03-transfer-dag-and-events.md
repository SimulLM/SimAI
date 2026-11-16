# C：传输DAG与宿主事件

已实现按源PP Stage划分的传输fragment，每图包含各TP rank的通信任务及唯一零时长terminal。同构分片按相同Stage/rank对应传输；全部Stage图terminal完成后才安排一次接收提交事件。任务图仍遵循v1的单Stage上下文，运行身份包含request、Stage和migration0。首版拒绝重启Prefill与迁移重试。

传输cost为latency_s + wire_bytes / bandwidth_bytes_per_s。metadata保留源/目标GPU、端点、存储bytes、wire bytes、带宽、时延和证据。默认是否占GPU由PD配置显式给出；网络端点沿用StagePlacement映射，重复资源ID去重。

Stage图、PD图复用同一执行器、资源管理器和Simulator堆。DagHostEvent对Stage保持原StageEnd排序身份，对非Stage图使用独立anchor。PD图不生成StageEnd。terminal回调只向outbox加入接收事件，不重入执行器；目标提交、KVReady和Decode唤醒在后续同时间宿主事件完成。

最终图输出对PD使用图ID哈希文件名，避免与Stage迭代编号重名覆盖。费用账本包含PD任务，Stage费用结算只消费本Stage图，避免把传输费用重复加进模型执行时间。

受控测试中，每分片8 bytes、4 bytes/s，传输需2s；TP2/PP2四分片共享同一端点时，1s提交、9s就绪；独立端点时3s就绪。还覆盖terminal一次和全部Stage汇合。
