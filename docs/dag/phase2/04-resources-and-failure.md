# D：资源调用边界与运行失败

已完成。执行器支持注入阶段1ResourceManager协议；`testing.py`提供显式依赖验证替身。阶段2没有生产容量管理器或KV实现。

## 三种运行模式

默认resource_free只接受空demands。注入管理器时选择injected模式，非空需求还必须提供resource_units注册表，资源ID/单位在图启动前检查。dependency_only=True显式启用无容量约束的替身，输出标记该模式；不能与注入管理器混用。

dispatch完整传递demands，失败返回None时不启动任务，保留原提交序号并记录resource_wait。其他可用任务继续执行。release先于后继解锁；完成后统一按提交序号扫描READY，覆盖管理器返回的wakeups和新就绪任务。首版采取全量READY扫描，wakeups不改变调度优先级。

外部资源通知可以在宿主队列安排dispatch事件。try_acquire必须满足原子语义：抛出异常或返回None时，管理器不得残留无法追踪的部分占用。阶段3负责实现并验证该保证。

## 失败与清理

宿主可以调用扩展方法 `fail_task(graph_id, task_id, now, reason)` 注入RUNNING任务失败。获取/释放资源异常、完成时间溢出或回调异常也会标记图FAILED并返回graph_failed。

失败图停止启动新任务，清理仍持有的租约。每份租约最多尝试release一次；release失败时保留未确认租约与cleanup_errors，不能报告资源已经释放。已经排队的失败图完成事件被忽略，不再解锁或释放。成功terminal回调不会在失败路径补调。

重复完成属于协议错误，抛RuntimeError且不改变剩余前驱数。回调在调用前记录次数，异常后不会再次执行；禁止回调重入执行器。检查快照保留回调对象身份，不复制其绑定的Simulator、锁或文件等宿主对象。

## 验证

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe -m pytest tests/dag/test_resources_and_failure.py -q --basetemp .cache/phase2-tests-d2
```

12项通过，覆盖资源单位拒绝、跨图唤醒、等待与新工作顺序、外部dispatch、队列停滞、任务失败一次清理、遗留完成事件、申请异常、释放异常、不重复释放、三类回调失败和绑定宿主的检查快照。等待替身只控制成功/失败，不用于22/18/22μs容量验收。

接口复查增加非空多资源需求整体传递、placement不隐式申请资源两项，最终该文件14项通过。
