# 2048/128、并发 4、32 请求端到端预验收

本轮为用户指定的单独预验收，不计入 30 轮 validation。32 条实测、两版预测和逐请求评分均已交付。结果为 **failed：费用覆盖和独占费用归属未通过**，并非误差或组批门槛。

原始服务、输入、客户端、router/worker 事件、源码差异、费用输入、启动/仿真日志、命令、退出码及失败重试关系保存在服务器：

`/root/autodl-tmp/dag-handoff/runs/preaccept-2048-128-c4-20261126-2236`

两版完整预测及评分：上述目录 `prediction-retry-01/`。本目录中的 CSV/JSON 是原件的回传副本。原件包包含首个预热后空闲检查失败的 `...-2231` 尝试，不删除失败记录。

## 固定比较与边界

原版为未经修改 `cef83f9ddd96540e3e9f48934f11335d52d54fce`；DAG 为 `b3ce1b661d39510192652457ce1266ebfa417b1b` 加唯一原版预测器覆盖。就绪修复与其他调度改造均不在比较中。profile 沿用当前候选，未根据本轮 E2E 拟合。

真实服务 vLLM 0.8.5、FP16、TP1、1P1D、每卡一个角色，沿用现有轻量 host 事件记录。4 条预热与正式 32 条分开记录；空闲观察覆盖 router inflight、运行/等待队列和 GPU KV 占用。当前版本没有导出的 swapped/CPU cache 指标记录 null，不伪造为零。预热结束、实测、失败清理均保留日志；本轮停止后两张 GPU 均为 0 MiB、0%。host 事件不能证明精确 GPU KVReady。

实际目标为 router stream complete-arrival；两版按这轮实际 router arrival 回放，预测为 modeled batch complete-arrival。末端 host/router 残差保留在误差中，不加补偿。真实 consumer 第一次 KV bypass 生成客户端 token 1，后续 127 次生成 token 2..128；producer token 不发送给客户端。仿真 Prefill 计 token 1，随后 127 轮 Decode。物理位置不同的首 token 费用仍未闭合，不能因 token 总数一致而宣称完整同费用。

## 实际结果

| 检查 | 结果 |
|---|---|
| 32 条 HTTP、token、ID、router 时钟对账 | passed，全部 2048/128 |
| 两版真实到达回放 | passed，32/32 |
| PD host send/recv、KV bypass、consumer 128 步 | passed；host 时间限制披露 |
| DAG 提前 Decode | 0 |
| DAG 重复、未完成、早于依赖任务 | 0 |
| 配对模型批次 | 621；原版 621/1058=58.70%，DAG 621/1052=59.03% |
| 配对批次最大费用差 | 2.78e-17 秒；不含 DAG 资源等待 |
| 原版提前编入未就绪请求 | 53 次，原版原样保留；首例 request 1、batch 9，start 0.214350232s < modeled ready 0.244342141s |
| 原版 MAE / 平均相对误差 | 0.199559664 秒 / 8.7881% |
| DAG MAE / 平均相对误差 | 0.737953174 秒 / 32.4916% |

DAG 本轮预测退化，结果保留。配对比例、误差与改善方向均不是验收门槛。

## 具体失败断言与唯一后续动作

`actual_reachable_fee_domain` 失败。当前主比较实际遇到的越界费用键是：

- Prefill 两请求合批的 equivalent chunk=2896；当前测量最大 2174。两版各 8 批。
- Decode batch=3，rounded context=2112/2176；当前 batch3 画像范围仅 1040..1152。原版分别 12/14 批，DAG 分别 4/8 批。
- Decode batch=1/2/4，rounded context=2176；相应画像最大 2174。本轮原版分别 4/8/495 批，DAG batch1/4 分别 4/504 批；DAG 没有到达此 batch2 键。

原预测器会在测量域外输出回归值。本报告保留这些预测，但不能将“能算出值”当成费用覆盖通过。`fee-domain.json` 记录实际主比较键、次数、画像哈希；没有使用其他诊断变体的旧缺费表。

`exclusive_physical_fee_ownership` 失败：consumer KV bypass 首 token、producer 输出 head、KV installation 与 inclusive receive/wait、同步 sampler 与 GPU 工作/等待的重叠尚无共同且独占的可执行映射。任务 ID 不重复及 621 对费用一致不能关闭这项。该失败来自保留的费用契约证据，不是发现了本轮一个可直接计数的重复任务。

唯一下一步：仅修复共享费用提供器/输入。先查已有独立微基准是否包含上述形状和边界，补齐可追溯的插值或测量域，并建立逐项独占收费映射；在新的预测尝试目录重放本轮同一实际 trace。没有必要重新采集这 32 条 GPU E2E，也不改变就绪/调度源码。未经修改原版保留；若需要费用适配的原版参考，必须另列 `fee-adapted reference`，不能改名为 pristine original。

## 已修复的本轮执行故障

首尝试 4 条预热成功后，空闲检查因缺少 vLLM 未导出的可选 gauge 中止；原件保留，第二次尝试记录 `retry_of`。只修正必需/可选指标检查。

第二次实测 32 条全部成功。原版首次回放因 Prefill 两请求合批查询 `attn_prefill[(0,8386816)]` 而 KeyError；两版共同将预测表生成范围从 2048 扩至 4096，费用文件不变，源码不变。原版 event JSON 导出器含 set 无法序列化，因此两版都只启用已有 Chrome trace 导出。CPU 回放重试成功，未重跑 GPU。第一次失败命令和 traceback 全部保留。

## 四项阻塞状态

唯一登记表为 `docs/dag_defense/freeze_gate/blockers.json`。本轮关闭“到达/评分边界”和“当前候选并发因果/token”两项；费用项 open；冻结执行项 open，需在费用通过后绑定哈希并接入正式轮次。`supervise_validation.py` 的正式 CLI 仍是 fail-closed，不能宣称已可启动 30 轮。正式仍 0/30、0/960。

原件包：`/root/autodl-tmp/dag-handoff/preacceptance-2048-128-c4-20261126-evidence.tar.gz`

SHA256：`91cf35b0eb069112864be6b6d235d39c2e3c628a74ea1e02c9c9eb73073159e6`。包内 `FINAL-SHA256SUMS` 覆盖实测、预测、费用输入及脚本快照；`result.json` 是首次失败状态，最新验收以 `final-acceptance.json` 为准，保留两者避免改写尝试历史。

证据已回传 Windows，并校验归档 SHA256 及内部 1510 个文件。完整原始证据发布于 [本次预验收 Release](https://github.com/SimulLM/SimAI/releases/tag/dev-preaccept-2048-c4-20261126)。使用已有 Git Credential Manager HTTPS 认证，未创建新 token，未撤销已有认证。
