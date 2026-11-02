# F：统一命令、时间线与验收

已完成。入口为 `scripts/dag_phase2/main.py`，提供validate、run和acceptance三个子命令。所有命令从项目根目录运行，output必须是 `results/dag/phase2` 下尚不存在的目录；拒绝覆盖历史结果。

## 单图运行

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe scripts/dag_phase2/main.py validate --graph tests/fixtures/dag/v1/fork_join.graph.json --output results/dag/phase2/<new-validation-id>
& ./.cache/dag-phase1-py315/Scripts/python.exe scripts/dag_phase2/main.py run --graph tests/fixtures/dag/v1/fork_join.graph.json --resource-mode dependency-only --output results/dag/phase2/<new-run-id>
```

validate只检查图结构、数值和语义，不执行资源容量或调度。run默认resource-free模式，有需求的输入会失败并保存原因；dependency-only必须显式指定。`--start-time`可指定有限非负秒数。生产资源注入通过Python API使用。

运行输出timeline.csv、events.csv、summary.json和run-manifest.json。失败运行同样保存诊断和manifest。CLI退出码：成功0；图输入/运行/验收失败1；命令参数、非法输出位置或覆盖已有目录2。

## 输出含义

timeline逐任务记录提交序号、类型、状态、ready/start/end、计划完成时间、常量cost、原始cost单位和来源、资源需求与等待。缺失时间为空；资源仍在等待时统计到图失败时间或当前观测时间。

events记录实际消费的事件及宿主插入序号。summary保存图提交/完成时间、makespan、回调次数、未完成前驱、资源等待、失败原因、未确认释放的租约，以及任务/事件数和队列峰值。makespan只在图成功完成时输出。不同图的task ID可相同。

manifest保存命令、解释器、全部已安装依赖版本、Git HEAD/status/diff、输入/代码/测试/输出SHA-256和退出码。新文件即使未提交也进入代码哈希。执行结果不包含NaN/Infinity。运行耗时和manifest日期不参与确定性比较。

## 统一验收

```powershell
& ./.cache/dag-phase1-py315/Scripts/python.exe scripts/dag_phase2/main.py acceptance --output results/dag/phase2/<new-acceptance-id>
```

验收实际执行三份图，保存各自时间线，再读取expected比较逐节点起止和完成次数；同时运行阶段1与阶段2测试。serial=10μs、fork_join=7μs、resource_contention在显式dependency_only模式下=18μs。第三份图原始demands保持不变，18μs只验证去掉容量约束后的依赖关键路径；shared和comm_occupies_compute的22μs属于阶段3资源验收，不能标为已通过。

测试还覆盖固定种子随机图、1500节点零时长链、多图、资源替身、运行失败、原子追加、CLI失败证据、输出不覆盖和轻量导入。pytest.log与pytest.xml保存联合回归结果。验收命令不会把阶段1精度pending改为通过。

## 验证记录

CLI与输出专项12项通过。第一次联合回归107项通过。接口复查补充真实多资源需求整体传递、placement不隐式申请资源、事件批次原子入堆与失败runner拒绝新任务，最终联合回归为110项。

最终结果目录：`results/dag/phase2/20261102-core-final-01/`。对应阶段1静态复验位于 `results/dag/phase1/20261102-after-phase2-01/`，18项通过，基线评估退出2：0有效样本、7项阻塞。结果目录继承Git忽略规则，交接需单独提供正式报告或重新运行。
