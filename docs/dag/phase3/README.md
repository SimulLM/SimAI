# 阶段3：资源约束

`vidur.dag.resources.CapacityResourceManager` 是阶段2 `ResourceManager` 与
`KVCapacity` 协议的生产实现。它以 `ResourceCapacity(amount, unit)` 注册每项资源，
并对整组 `ResourceDemand` 提供原子申请：任一资源不足时返回 `None`，不产生部分占用。

- compute 与通信使用 `permits`；通信是否同时占用 compute 由任务的 demands 显式声明。
- KV 使用 `bytes`，并遵循 `reserve -> commit -> release`；已 pin 的 allocation 不可释放。
- `release` 返回稳定顺序的等待者，执行器仍按既有 READY 提交顺序重试，保证确定性。
- `resource_timeline(executor)` 从同一 DAG 时钟中的任务起止时间导出资源占用区间，不建立第二个事件循环。

验收覆盖共享 compute 的 22μs、独立 compute/NIC 的 18μs、通信同时占 GPU 的 22μs，
以及多资源申请原子性、等待唤醒、KV 容量和 pin 生命周期：

运行正式验收并保存完整证据（JSON、任务/资源时间线、pytest 日志与 manifest）：

```powershell
python scripts/dag_phase3/main.py --output results/dag/phase3/<run_id>
```

仅快速执行资源层单元测试时：

```powershell
python -m pytest tests/dag/test_capacity_resources.py -q
```
