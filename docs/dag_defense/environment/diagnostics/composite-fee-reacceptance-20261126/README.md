# 唯一组合费用重验收与冻结

2026-11-26，在原有 2048/128、并发4、32请求实测原件上做费用适配重放，没有重跑这32条GPU实测。当前重验收 `passed`，随后冻结并启动30轮正式验证。精度改善不是验收条件。

## 六个历史缺费键与实际测量形状

去除 baseline/DAG 前缀后为 **6个**，之前口头“7个”有误：Prefill attention等效chunk2896；Decode batch3 context2112、2176；Decode batch1/2/4 context2176。

2896仅是旧attention特征，**没有作为整模型输入长度测量**。新的模型费用直接测输入1024/2048、实际batch1/2/3/4、Prefill及每个真实Decode上下文，10次预热、30次测量，每点1024个费用点之一。原始40,960个步骤的schedule/worker/output共122,880个顺序区间校验通过。测量使用单H800、离线vLLM0.8.5 eager FP16 TP1，batch4 Prefill所需token预算8192；真实服务预算仍4096，仿真按其形成的实际批次调用，没有修改调度。

## 三阶段唯一收费方案

| 阶段 | 调用与范围 | 删除的重复项 |
|---|---|---|
| 生产端Prefill | 每个实际批次一次worker组合，prepare输入至同步execute结束，包含embedding、全层含RoPE/KV写入、输出head、采样与内部host/GPU等待；独立schedule/output区间一次 | 旧layer、norm、RoPE、head、sampler、prepare分项全部归零 |
| KV与消费端token1 | 每请求一次组合，消费端prepare前同步后开始，经receive、KV安装、bypass head/采样，执行结束后设备同步；batch1串行测量1024/2048各10+30 | 替换旧带宽转移费用；删除独立install、consumer token1、head、sampler、prepare收费；内部子区间绝不相加 |
| 消费端token2–128 | 正常127轮Decode，按实际批次和真实上下文调用worker组合，schedule/output各一次 | 不再次收费token1；旧细分费用归零 |

producer生成但未发给客户端的token不从其实际工作中删除。消费端token1只在KV组合中收费；两端head/采样是各自实际发生的不同工作，不能互相抵消。未建模的consumer bypass engine schedule/output、router/IPC/stream尾部保留为误差残差，不从本轮E2E拟合补偿。

worker按phase、输入长度、实际batch查询，Decode上下文在线性插值范围内，拒绝外推。混合上下文使用真实平均context查询uniform画像是**固定模型近似**，不声称不同向量等价。完整费用调用在原件`fee-calls.jsonl`，每批原始context和插值bracket可查。

KV标量参数只是将每请求组合秒数代入既有传输公式的费用系数，**不是测得物理带宽**。旧CLI只能接收整数，适配器在Replica初始化后绑定准确浮点系数，没有修改任何调度、就绪、事件函数。首个CLI错误尝试保留为`preaccept-composite-replay-20261126-01`，成功为`...-02`。

## 资源假设：待验证近似

worker同步host/device整段占用一个GPU permit，其中GPU可能空闲；KV组合每请求串行，占用既有源/目标GPU及端点；这是**待验证近似**，不是已证实的物理占用。schedule/output沿用每副本CPU资源。组合内部CPU/GPU等待只计一次；组合之间的自然调度和资源竞争沿用候选。没有新增组批、就绪、屏障变体，也未按E2E误差选择占用开关。

## 重验收实际结果

- 32条实际到达、ID与2048/128 token完整；DAG一Prefill+127Decode轮；提前执行0。
- 每批仅一个正值worker费用；其余layer子项归零。32笔receiver组合，每请求一次，没有额外首token/head/sampler任务。
- DAG重复/不完整任务0；资源占用区间无超额重叠，`start-ready=resource_wait`逐任务成立。
- 实测8波无跨波重叠；两版每波到达时前波未完请求均0。此观测不设“预测无积压”门槛。
- DAG worker服务工作量16.982220秒、等待0.293115秒；receiver服务1.186740秒、等待0.502382秒。服务工作量不是E2E墙钟时间；等待没有再收费。完整分资源和分波数据见`backlog-and-resources.json`。
- 112个配对批次：费用适配参考9.655%、DAG9.722%，最大费用差1.39e-17秒。配对比例不设门槛。
- 费用适配参考MAE0.351946秒、相对误差15.5058%；DAG MAE0.161924秒、相对误差7.1360%。这只是预验收，不能替代独立正式验证，也不能分离组合费用与DAG机制贡献。

原版`cef83f9...`独立检出未改；原版原费用预测另列在`three-way-scores.csv`的`pristine_original_s`。内部历史解析器CSV里的`baseline`明确指`fee-adapted-reference`，不是pristine。DAG HEAD仍`b3ce1b...`加原版predictor覆盖及共同费用适配器；所有overlay与adapter哈希绑定。

## 冻结与正式入口

服务器冻结文件：`/root/autodl-tmp/dag-handoff/parameter-freeze.json`；SHA256 `0641087e94dec29ba93172d74454e1f5a90c71fc2ed6f5fce278a7741c7b2313`。绑定387个源码、输入、服务、费用及测量文件；权重另验SHA256并逐轮核对文件身份。冻结前校验1024/2048 × batch1–4 × 全部127个后续Decode上下文覆盖。

```bash
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/run_frozen_matrix.py --output /root/autodl-tmp/dag-handoff/runs/<new-formal-id>
```

实际运行：`formal-validation-composite-20261126-01`。每轮预热、空闲观察、32条采集、router/token/worker对账、再核验空闲；失败中止矩阵、停止整个服务进程组、保留失败和未提交请求，不自动开放。正式源码与费用冻结后不再随运行改动。GPU收齐后停止，CPU按每轮实际到达回放费用适配参考、DAG和未修改原版并评分。完整结果状态以服务器`matrix-status.json`为准；本报告生成时已开始首轮，不宣称30轮完成。

费用原件：`/root/autodl-tmp/dag-handoff/runs/composite-fees-20261126-01`；KV补测：`receiver-composite-fees-20261126-01`；成功重放：`preaccept-composite-replay-20261126-02`。

费用域、物理组件独占清单和区间重叠负例检查已通过。Windows与服务环境的整套pytest调用分别因缺aiohttp、缺pytest未执行，已保留该失败；没有为此安装依赖。实际新费用negative tests在本机和服务器直接执行通过，真实重放的所有验收断言已执行。

随后在Windows排除需要aiohttp的collector测试，单独执行费用负例与validation矩阵测试，结果 **4 passed**。已有冻结运行未因此改变。
