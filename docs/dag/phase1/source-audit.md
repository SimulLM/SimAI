# 第一阶段源码与归档核验

核验基线：HEAD `354a9289e65a7d4ef58b6d232c628c8ebd4789a2` 加当前工作区；精确源码哈希和工作区差异见每次运行 manifest。2026-10-31，Asia/Shanghai。保留用户已有 README 修改及架构文档删除，不恢复该文件。

## 断言核验

以下为静态源码证据，除单独注明的受控探针外，不等同于真实模型运行验收。

| 文档断言 | 当前源码证据（项目根目录相对位置） | 核验方式与结论 |
|---|---|---|
| 请求图已有节点与边 | `vidur-alibabacloud/vidur/entities/request.py:72,378–409` | nx.DiGraph、create_task/create_flow/successors 存在，已证实 |
| 只创建粗粒度 P→D | `vidur-alibabacloud/vidur/scheduler/global_scheduler/splitwise_global_scheduler.py:342–346` | 实际调度路径创建 prompt/token 并连边，已证实 |
| KV 插入调用未执行 | 同文件 `:234–259,382–431` | AST 查得可执行 add_kv_cache_transfer 调用为0，字符串调用区间为382–431，已证实 |
| 请求队列驱动组批 | `vidur-alibabacloud/vidur/events/global_schedule_event.py:30`；`scheduler/replica_scheduler/splitwise_replica_scheduler.py:315`（后者相对 vidur 目录） | 请求映射→队列→batch，不读取 DAG 前驱完成状态，已证实 |
| Stage 整体占用和预测 | `vidur-alibabacloud/vidur/scheduler/replica_stage_scheduler/replica_stage_schduler.py:39–73` | _is_busy、get_execution_time、total_time，已证实 |
| 固定事件推进流程 | `vidur-alibabacloud/vidur/events/replica_stage_schedule_event.py:57–69`；`events/batch_stage_end_event.py:35–110`（后者相对 vidur 目录） | 直接安排 StageEnd，再选下一 Stage/BatchEnd，无通用解锁循环，已证实 |
| PD 静态到达延迟 | `vidur-alibabacloud/vidur/events/batch_end_event.py:104–144` | size/bandwidth 与 decode_arrived_at，已证实；未证明容量 pin/reserve 正确 |
| MoE 聚合耗时 | `vidur-alibabacloud/vidur/entities/execution_time.py:568–601,1171–1182` | 固定 prefill 带宽分支、计算加通信并逐层求和，已证实 |
| 底层 flow 解锁存在 | `astra-sim-alibabacloud/astra-sim/system/collective/NcclFlowModel.cc:127–131,192,214` | 初始化前驱数、递减后继入度，已证实；不等同上层请求 DAG |
| 时钟为宿主事件堆 | `vidur-alibabacloud/vidur/simulator.py:78–110,147–154`；`events/base_event.py:55`（后者相对 vidur 目录） | heapq 与事件 priority 使用 time/id；新接口沿用单时钟 |

旧 Node 类中的 clock、metrics 引用和 interconnect 草案不能当作已接通执行器。其存在不会改变主链未消费请求 DAG 的结论；本阶段接口独立声明，避免调用这些未接通方法。

## Backend cost 归属

公共分派见 `vidur-alibabacloud/vidur/execution_time_predictor/base_execution_time_predictor.py:49–95`，汇总见 `vidur/entities/execution_time.py:488–521,1192–1200,1286–1342`（相对 vidur-alibabacloud）。

| backend/路径 | Compute | TP | PP | EP | CPU / PD | 状态 |
|---|---|---|---|---|---|---|
| vidur 常规 | Attention/MLP 分项层时延 | 每层 attention、MLP 各含一次 TP cost；TP1 为0 | 非末 Stage 通过公共预测接口加入 | 无独立动态 Expert DAG | total_time 加 CPU；PD 在 BatchEnd 另算 | 源码确认归属，画像单位/硬件精度未实跑 |
| simai_simulation | 同常规 compute 预测 | TPTimePredictor 调 ns-3 路径 | 公共 PP 估时，不代表 ns-3 已建模 PP | TP 适配器初始化 ep_size=1，无完整 EP | 同上 | 本地 bin 缺失，未补跑 |
| simai_analytical | 同常规 compute 预测 | analytical TP 适配器 | 同上 | 同上 | 同上 | 本地 bin 缺失，未补跑 |
| aicb 特殊模型/PP1 | 层画像 comp_time 从 ns 转秒 | 公共分派显式设置0，不能当作已包含 TP | Stage 汇总仍加 PP 字段 | comm_size/带宽近似，并固定 prefill 分支 | CPU 仍按 ms 转秒；PD 另算 | 单位探针复现缺陷；无动态争用 |
| aicb 其他模型/PP>1 | 非上述特殊分支需另验 | 不支持项不能推断为0真实成本 | 特殊模型 PP>1 的 start_layer/end_layer 未初始化 | 未核验完整组合 | 未核验 | 不纳入已验证首批配置 |

coarse 只能用原 total_time 一次；拆分后不能再次叠加该总值。原 PD 在批完成后另计，不能重复放入 coarse cost。Ray 通信是 CPU overhead 的一个分项，不能因为名字含 comm 就替代 TP/EP。

## AICB 数值探针与待修缺陷

`probe_aicb.py` 从原源码 AST 抽取6个方法，保留原方法体；构建没有 import、缓存、子进程和模型初始化的受控对象。输入 deepseek-671B/aicb/PP1、1层、attention/mlp/moe 各1,000,000ns、通信量0、PP cost0。

层合计返回0.003秒，而 model_time 返回0.000003秒，确认该受控路径存在再次乘1e-3的单位缩放。它不能证明所有 backend/模型都有千倍误差，也不能证明当前画像本身准确。`aicb-unit-probe.json` 保存输入、源码哈希和实际输出。

遗留问题：AICB 秒/ms 统一、TP 费用缺失、prefill 带宽硬编码、特殊模型 PP>1 未初始化。后续各设修正测试，旧/新 coarse 兼容性比较保留旧 cost，修订贡献单独报告。本轮不改执行源码。

## 归档核验与结论边界

`audit_archive.py` 逐字节校验 manifest 82项，核对 ZIP SHA 并查找原始 trace；本轮全部匹配，verified_cost=0，ZIP48项且原始 trace 缺失。这支持归档完整，不支持“参考数据已经齐全”。逐项结果见 archive-audit.json 和 reference-inventory.csv。

未运行：原推理链、PD 配置测试、真实 GPU 测量、ns-3/analytical 二进制仿真。阶段1测试只覆盖静态契约、预给定时序自洽和误差计算，不替代阶段2/3执行核验收。
