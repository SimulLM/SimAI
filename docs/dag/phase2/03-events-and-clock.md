# C：独立事件运行器与单时钟

已完成。`runner.py`提供DagRunner，负责CLI模式下唯一的事件堆。执行器只返回EventIntent。

## 使用

构造 `DagRunner(executor)`，调用submit提交图。`step()`只消费一个事件，适合插入图片段或外部资源通知；`run()`持续消费直到完成。返回值是宿主绝对时间，图makespan需减去submitted_at。

事件堆键为(time_s, insertion_sequence)，插入序号由runner生成。同一时刻按插入顺序处理完成事件；每个完成先释放该任务资源，再解锁和调度后继。零时长后继仍产生完成事件，避免递归推进。

submit允许非零时间，但不能跳过队列中更早的事件。enqueue先完整检查一组事件，拒绝过去时间和非法载荷，再整组入堆。terminal回调允许返回EventIntents，回调不能重入执行器推进时间。

runner遇到graph_failed或协议异常抛出SimulationFailure并保留事件记录。队列耗尽但仍有未完成图也报错；资源等待时不能直接报告成功。原Simulator接入时以其队列替换runner，执行器接口保持一致。

## 验证

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe -m pytest tests/dag/test_runner.py -q --basetemp .cache/phase2-tests-c
```

12项通过：terminal-only、非零提交时刻、1500节点零时长链、重复执行确定性、跨图同task ID、重复graph ID、回调返回事件、非法回调、非法宿主时间、完成时间溢出和过去事件拒绝。随机用例使用固定种子20261102，生成1/5/20/50节点各5张图，以独立拓扑动态规划计算起止和关键路径，逐节点对照实际执行结果。

接口复查增加正耗时浮点精度丢失的显式失败、批次入堆原子性和失败runner拒绝新任务，最终该文件14项通过。

## 限制

runner为独立逻辑验证适配器，未接入请求组批、token推进或原推理事件。资源容量仍需阶段3。事件顺序不按类型添加额外优先级，不把近似相等的浮点时刻合并。
