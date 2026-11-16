# B：KV容量事务与所有权

已实现 `KVTransactions` 和 `PDCoordinator` 的存储生命周期。统一使用阶段3的CapacityResourceManager，GPU/NIC仍使用permits，KV资源使用bytes。

Prefill准入前reserve源分片并commit为分配；Prefill完成后pin。目标所有分片预留成功才启动传输。多分片任一预留失败，回滚本次其余预留，不保留部分占用；协调层按稳定顺序等待释放通知。接收完成commit目标，不再次扣容量；随后unpin并释放源。Decode结束释放目标。

首版沿用最大序列块预分配。资源管理器负责容量准入，调度器块表和副本统计从同一操作同步。目标预留时已经占有块，Decode组批不再分配。有效KV字节与预分配容量分别记录。

每分片有效容量取显式配置与原块池容量的较小值。超过总容量的请求报错；暂时不足则等待。释放后在同一宿主时刻安排重试和副本调度，没有定时轮询。目标满时保留源KV，形成上游背压。

`tests/dag/test_pd_transactions.py`三项通过，覆盖reserve/commit/pin/release、部分预留回滚和commit不重复计费。协调层测试还覆盖源容量不足、目标背压和释放后继续推进。
