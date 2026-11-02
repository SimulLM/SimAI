# A：共享校验与输入转换

已完成。共享校验位于 `schemas/dag/v1/validation.py`，JSON读取位于同目录 `io.py`，类型转换位于 `vidur-alibabacloud/vidur/dag/serialization.py`。

## 作用与调用

`load_graph(path)` 从JSON读取图；`graph_from_dict(data)` 接受字典；`snapshot_graph(fragment)` 校验并复制冻结类型。三者均返回阶段1的 `GraphFragment`。执行器提交时再次获取快照，外部修改原对象的metadata不会改变已提交图。

JSON数组转换为tuple，省略的metadata补为空字典。`graph_to_dict`输出可序列化字典，不包含运行状态。schema和公共类型仍使用v1版本。

校验覆盖唯一ID、引用、无环、唯一terminal、收口、费用互斥、时间单位、转换因子和有限数值。结构错误统一为ValueError。重复JSON键、NaN/Infinity和metadata中的非有限浮点数也拒绝。解析出的极大整数若不能转换为有限float同样拒绝。

阶段1的 `scripts/dag_phase1/graph_validation.py` 保留原导出接口，转调共享实现。预给定时序的静态校验仍然保留，不参与执行调度。

## 环境与验证

项目根目录运行：

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe -m pytest tests/test_dag_phase1_contracts.py tests/dag/test_validation.py -q --basetemp .cache/phase2-tests-a2
```

Python 3.15.2，51项通过：原阶段1测试31项，输入与转换新增20项。覆盖三份有效图往返、九份非法图、直接构造dataclass的非法值、metadata隔离、重复JSON键和溢出值。

## 归档换行修复

根目录 `.gitattributes` 对 `baseline-data/**` 指定 `-text`，Git不再自动转换该目录换行。复验时已经恢复的64份文本字节与HEAD及原始manifest哈希一致；规则保留这些字节，不修改历史哈希。Python生成的字节码加入忽略规则。

## 消费边界

当前按仓库源码布局运行；入口需要同时将项目根目录和 `vidur-alibabacloud` 加入模块路径。只加载轻量DAG模块，不导入模型、GPU或完整推理依赖。独立wheel打包属于后续工作。
