# B：运行状态与依赖执行核心

已完成。`runtime.py`保存图/任务运行状态；`executor.py`实现submit、dispatch和on_task_complete。公共类型继续使用阶段1contracts。

## 执行流程

submit先校验并复制输入，建立前驱计数、后继表和稳定提交序号，再登记图。零前驱节点转为READY并调用dispatch。返回初始EventIntent，不创建事件循环。

dispatch按稳定提交序号检查READY任务，成功启动后记录start_at和scheduled_finish_at并返回完成事件。重复dispatch不会再次启动RUNNING任务。任务耗时直接使用提交快照，执行中不估时。

on_task_complete严格检查RUNNING状态与计划完成时间，先释放租约，再标记完成和递减后继计数。最后一个前驱完成才使后继READY。terminal完成时调用一次回调，返回其事件与后续调度事件。

## 状态与隔离

TaskRuntime保存前驱数、后继、状态、就绪/开始/结束时间、租约、等待和完成次数。GraphRuntime保存图状态、回调次数、完成计数及错误。`executor.graphs`返回脱离内部状态的检查快照。

运行身份为(graph_id, task_id)，graph ID在执行器生命周期内不可重用。非法提交不登记图或推进时钟；错误完成事件不重复解锁或推进时钟。完成时刻使用宿主原样传回的EventIntent.time_s，比较为精确float；测试期望用小量浮点容差。

资源默认模式仅接受无需求任务。有demands时必须注入管理器和单位注册表，或显式选dependency_only测试模式。后者不约束容量，结果必须标注。资源调用和失败边界在D部分进一步说明。

## 验证

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe -m pytest tests/dag/test_executor.py -q --basetemp .cache/phase2-tests-b
```

6项通过。实际执行serial和fork_join，对照expected文件的每个节点起止时间，分别得到10μs和7μs；终端各回调一次。其他测试覆盖前驱门控、重复完成、重复dispatch、非法完成时间、时间回退、非法提交原子性和运行状态隔离。测试中的小堆只负责消费事件，不向执行器提供expected时序。
