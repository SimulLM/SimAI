# E：原子图片段追加

已完成。执行器实现阶段1DagExecutor.append协议；独立runner提供append包装，将返回事件放回同一宿主队列。

## 追加规则

GraphAppend只描述新增tasks和edges，graph ID必须存在。terminal ID沿用原图。ACTIVE图且terminal仍PENDING时才接受追加；新增边的既有目标也必须PENDING。READY但被资源阻塞的任务已经冻结依赖，不能作为追加目标。

候选图经过完整schema/语义/资源声明校验，拒绝重复task/edge、未知引用、环、未收口节点、非法cost和未知资源。校验、后继表和剩余前驱计数的计算全部在提交更新之前进行；非法追加不推进时钟、不改变提交序号、运行状态或原事件队列。

新节点可以依赖COMPLETED前驱，其剩余前驱数不再计入该前驱。新根节点可以在追加时刻就绪。既有RUNNING任务的完成事件保持原计划；其完成时会消费更新后的后继表。

## 例子

原图A(2s)→B(1s)→terminal，A已经RUNNING。追加A→X(3s)→B后，A在2s完成、X在2—5s运行、B在5—6s运行，图在6s完成。原A→B边保留，B会等待A和X两个前驱。

未来MoE构图需要保留PENDING屏障，在屏障就绪前追加。阶段2仅验证通用执行语义，没有路由算法、Expert画像或通信展开。

## 验证

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe -m pytest tests/dag/test_append.py -q --basetemp .cache/phase2-tests-e
```

13项通过：运行中追加并延迟join、已完成前驱、新根节点与metadata快照、八类非法patch的完整回滚、READY目标与terminal保护、未知/已完成图拒绝。非法追加后继续消费原事件，验证原图仍能按原时序完成。
