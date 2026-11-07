# 阶段3：资源约束

`vidur.dag.resources.CapacityResourceManager` 是阶段2 `ResourceManager` 与
`KVCapacity` 协议的生产实现。它以 `ResourceCapacity(amount, unit)` 注册每项资源，
并对整组 `ResourceDemand` 提供原子申请：任一资源不足时返回 `None`，不产生部分占用。

- compute 与通信使用 `permits`；通信是否同时占用 compute 由任务的 demands 显式声明。
- KV 使用 `bytes`，并遵循 `reserve -> commit -> release`；已 pin 的 allocation 不可释放。
- `release` 返回稳定顺序的等待者，执行器仍按既有 READY 提交顺序重试，保证确定性。
- `resource_timeline(executor)` 从同一 DAG 时钟中的任务起止时间导出资源占用区间，不建立第二个事件循环。

失败清理：执行器通过可选的 `cancel_waiters(owners)` 扩展取消失败图内全部任务的等待登记，
不会取消其他图的等待者或释放调用者独立持有的 KV reservation。原有仅实现
`try_acquire/release` 的管理器仍可注入。成功释放租约时记录 `resource_released_at`；
失败任务输出从启动到实际释放的资源区间，释放未确认时保留租约及 cleanup_errors，
不会虚构结束时刻。正常 completion 的 `end_at` 语义保持不变。

`resource_capacity_validated` 仅对成功运行且通过资源区间容量、最终计数边界和任务租约
释放检查时为 true；失败运行保留资源使用量与检查错误，但该标记为 false。

验收覆盖共享 compute 的 22μs、独立 compute/NIC 的 18μs、通信同时占 GPU 的 22μs，
以及多资源申请原子性、等待唤醒、KV 容量和 pin 生命周期：

运行正式验收并保存完整证据（JSON、任务/资源时间线、pytest 日志与 manifest）：

```powershell
python scripts/dag_phase3/main.py --output results/dag/phase3/<run_id>
```

验收还保存故障注入场景 `failure_cleanup/`（0 启动，5μs 失败并释放）、完整输入图与
资源配置，以及 KV 收尾到零的记录。故障注入的工作负载 summary 为 failed 是预期行为，
顶层验收判断的是失败是否被正确处理。manifest 包含整个 DAG 执行器、schema、测试与
验收入口的 SHA-256、依赖版本、Git 状态/差异、退出码和正式产物哈希（不包含 manifest
自身或 pytest 临时文件）。异常执行返回 1，并尽可能保留 operation-error.json、失败
验收报告和 manifest；已经存在的输出目录会被拒绝覆盖。

仅快速执行资源层单元测试时：

```powershell
python -m pytest tests/dag/test_capacity_resources.py -q
```
