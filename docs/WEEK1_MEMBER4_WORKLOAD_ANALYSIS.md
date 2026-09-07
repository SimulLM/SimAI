# 成员四：第一周工作二——AICB/SimAI 负载字段与 AllToAll 统计

## 结论

`example/workload_analytical.txt` 的 1,789 条记录通过结构一致性检查。按负载记录中的
`comm_size` 字段求和：

- 普通 `ALLTOALL`：768 次通信操作，合计 18 GiB；
- 专家并行 `ALLTOALL_EP`：768 次通信操作，合计 72 GiB；
- 两类合计 90 GiB，`ALLTOALL_EP` 的声明字节数是普通 `ALLTOALL` 的 4 倍。

这里的“字节数”是负载文件中每次集合通信的**声明消息大小之和**，不是实测链路流量，
也不能直接解释为单卡、全网或交换机端口的实际传输字节数。

## AICB 到 SimAI 的负载链路

1. `aicb/scripts/inference_workload_with_aiob.sh` 收集模型、推理阶段、序列长度、批量大小和
   TP/EP/PP 等运行参数。
2. `SimAI_inference_workload_generator.py` 读取模型 JSON，遍历模拟模型的层，并将每个阶段
   写成一个 `Work_Item`。
3. 生成器把元数据头、记录数和每个 `Work_Item` 的 12 个字段写入制表符分隔的 `.txt` 文件。
4. SimAI 的 `Workload.cc` 读取这些字段，把通信类型解析为集合通信及其并行组，再按
   forward、input-gradient、weight-gradient 的次序驱动仿真。

推理生成器当前支持 DeepSeek、Qwen3-MoE 和 Qwen3-Next。仓库说明指出，这些推理负载目前
只兼容使用 `autobusbw` 的 SimAI-Analytical；DeepEP 通信仿真仍在开发中。

## 文件格式

### 元数据头

本次样例头部为：

```text
HYBRID_TRANSFORMER_FWD_IN_BCKWD model_parallel_NPU_group: 2 ep: 16 pp: 12 vpp: 8 ga: 24 all_gpus: 9216 checkpoints: 0 checkpoint_initiates: 0 pp_comm 50331648
```

其含义为：TP=2、EP=16、PP=12、虚拟流水并行 VPP=8、梯度累积 GA=24、总 GPU 数
9,216，流水通信消息大小为 50,331,648 字节。第二行的 `1789` 是后续记录数。

### 每条记录的 12 个字段

| 序号 | 字段 | 含义 |
|---:|---|---|
| 1 | `name` | 层或操作名称 |
| 2 | `dependency` | 依赖占位/索引；样例中常用 `-1` 表示无显式依赖 |
| 3 | `forward_compute_time` | 前向计算时间 |
| 4 | `forward_comm_type` | 前向通信类型 |
| 5 | `forward_comm_size` | 前向声明消息大小，字节 |
| 6 | `input_gradient_compute_time` | 输入梯度计算时间 |
| 7 | `input_gradient_comm_type` | 输入梯度通信类型 |
| 8 | `input_gradient_comm_size` | 输入梯度声明消息大小，字节 |
| 9 | `weight_gradient_compute_time` | 权重梯度计算时间 |
| 10 | `weight_gradient_comm_type` | 权重梯度通信类型 |
| 11 | `weight_gradient_comm_size` | 权重梯度声明消息大小，字节 |
| 12 | `weight_update_time` | 权重更新/处理时间 |

`NONE` 表示该阶段没有通信。`_EP` 后缀指定专家并行组，`_DP_EP` 指定数据并行与专家并行
组合组；不带后缀的 forward/input-gradient 通信通常使用 TP 组，而 weight-gradient 通信
通常使用 DP 组。

## AICB 推理生成器中的通信量计算

生成器先按推理阶段选择 token 维度：decode 使用 `micro_batch`，prefill 使用
`seq_length`。随后计算：

```text
tp_comm_size   = 2 * token_dimension * hidden_size
ep_combine     = tp_comm_size * topk / tp
ep_dispatch    = ep_combine
```

对 DeepSeek/Qwen3，dispatch 还会乘以代码中的 FP8 系数。MoE route 生成
`ALLTOALL_EP` dispatch，MoE expert 生成 `ALLTOALL_EP` combine。若未启用 AIOB 且没有既有
profile 文件，计算时间会回退为固定值 `1`，因此这种文件适合验证通信链路，不适合做高可信的
计算时间预测。

## AllToAll 统计结果

| 类型 | 阶段 | 次数 | 单次声明大小 | 阶段合计 |
|---|---|---:|---:|---:|
| `ALLTOALL` | forward | 384 | 24 MiB | 9 GiB |
| `ALLTOALL` | input-gradient | 384 | 24 MiB | 9 GiB |
| `ALLTOALL_EP` | forward | 384 | 96 MiB | 36 GiB |
| `ALLTOALL_EP` | input-gradient | 384 | 96 MiB | 36 GiB |

四组记录都来自 `mlp_moelayer`。计算过程为：

```text
ALLTOALL    = 384 * 24 MiB * 2 phases = 18 GiB
ALLTOALL_EP = 384 * 96 MiB * 2 phases = 72 GiB
ratio       = 72 GiB / 18 GiB         = 4
combined    = 18 GiB + 72 GiB         = 90 GiB
```

次数相同而累计量相差 4 倍，说明差异完全来自负载中单次消息大小，而不是操作频率。

## 数据质量检查

以下硬性检查全部通过：

- 声明记录数与实际记录数均为 1,789；
- 每条记录均有 12 个字段；
- 所有数值字段均可解析，且依赖字段之外没有负值；
- 所有通信类型均能被当前校验规则识别；
- 所有 `NONE` 通信的大小均为 0。

另有 216 个 input-gradient `REDUCESCATTER` 操作的大小为 0。当前将其视为可疑但非格式错误：
解析器允许该组合，且不能仅凭文件判断它是刻意的零载荷同步还是生成缺失。后续若用此样例进行
性能归因，应先追踪这些记录的生成逻辑。

## WSL 实跑记录与限制

在 Ubuntu-24.04 WSL 中验证入口时发现两点：

1. Windows 工作区检出的 `inference_workload_with_aiob.sh` 使用 CRLF 行尾，Ubuntu `sh`
   会报 `\r: not found` 并使参数值带入回车字符；应在 WSL 原生检出仓库，或先把脚本转为 LF。
2. 绕过 shell 脚本直接运行 Python 生成器后，环境缺少 `pandas`；进一步检查也缺少
   `numpy` 和 `torch`。当前 `aicb/requirements.txt` 没有列出 `pandas`、`numpy`、`torch`，
   所以不能把该 requirements 文件视为完整的无 AIOB 生成环境说明。

本项没有为追求一次生成而安装大体积 GPU/PyTorch 依赖，也没有改动上游 AICB 代码；可复现的
静态负载分析不依赖这些包，已经完成。

## 复现方法

在仓库根目录执行：

```bash
python scripts/analyze_workload.py
```

程序会读取 `example/workload_analytical.txt`，执行结构与取值校验，并更新：

- `docs/data/week1_workload_analysis.json`：完整机器可读结果；
- 进程退出码：全部硬性检查通过为 0，否则为 1。

也可分析其他文件或只打印 JSON：

```bash
python scripts/analyze_workload.py path/to/workload.txt --output -
```

## 源码依据

- AICB 推理使用说明：`aicb/README.md` 第 316–348 行；
- shell 参数与 Python 调用：`aicb/scripts/inference_workload_with_aiob.sh` 第 1–189 行；
- 12 字段定义：`aicb/workload_generator/SimAI_inference_workload_generator.py` 第 25–38 行；
- 通信量公式：同文件第 115–129 行；
- 输出格式：同文件第 238–260 行；
- SimAI 字段解析与并行组映射：`astra-sim-alibabacloud/astra-sim/workload/Workload.cc`
  第 1,274–1,493 行。
