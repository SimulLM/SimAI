# 第一阶段交付与交接

目标：冻结 Batch iteration/Stage 任务图与执行边界，给阶段2—5提供可消费的类型、输入和验收样例；分别报告契约验收与精度基线。负责人待认领，DDL 为2026-11-01 22:00（Asia/Shanghai）。

## 交付索引

- [源码与归档核验](source-audit.md)：证据、backend 费用归属、受控 AICB 单位缺陷。
- [执行契约](execution-contract.md)：图、状态、接口、时钟、回调、资源和 cost 所有权。
- [数据与指标](data-and-metrics.md)：配对、导入、划分、退出码和补证要求。
- [schema](../../../schemas/dag/v1/graph.schema.json) 与 [Python 类型/Protocol](../../../schemas/dag/v1/contracts.py)：无执行实现，无旧 Node 依赖。
- [手算图与期望](../../../tests/fixtures/dag/v1/)：串行、fork-join、三类资源场景，以及9个非法输入。
- [配置与数据表](../../../configs/dag/phase1/)：支持矩阵、82项清单、7项阻塞配对、组划分及导入模板。
- [工具](../../../scripts/dag_phase1/) 与 [验收测试](../../../tests/test_dag_phase1_contracts.py)：图/数据校验、审计、导入、误差和探针。

## 复现顺序

工作目录为项目根目录，Python 3.10+。安装依赖：

```text
python -m pip install -r scripts/dag_phase1/requirements.txt
```

原验收环境使用 Python3.14、pytest9.1.1、jsonschema4.26.0，精确版本见归档 manifest。本地 `.cache/dag-phase1-deps` 依赖副本已随临时缓存清理；重新运行前按上面的 requirements.txt 安装依赖。common.py 仍兼容项目内可选依赖目录，正常虚拟环境无需该目录。

每次使用新的 run_id，避免覆盖验收记录；下面三个命令可共用同一 run_id：

```text
python scripts/dag_phase1/validate.py --output results/dag/phase1/<run_id>
python scripts/dag_phase1/evaluate_baseline.py --pairs configs/dag/phase1/data-pairs.csv --output results/dag/phase1/<run_id>
python -m pytest tests/test_dag_phase1_contracts.py -q
```

Windows 沙箱若系统临时目录不可写，pytest 增加 `--basetemp .cache/<new-test-run-id>`。带完整日志与 JUnit 的等价命令：

```text
python scripts/dag_phase1/run_tests.py --output results/dag/phase1/<run_id>
```

evaluate 退出码2在当前数据下是预期的“精度基线未通过”，不能由命令调用者改写为通过。审计清单需要显式刷新时运行：

```text
python scripts/dag_phase1/audit_archive.py --inventory configs/dag/phase1/reference-inventory.csv
```

## 输出及验收状态

`results/dag/phase1/<run_id>/` 保存各操作独立 manifest/log，包含 Git SHA、工作区 diff/status、Python/依赖版本、输入/代码 SHA-256、种子说明、命令 argv、完整配置和退出码。交接时归档正式报告、日志与 manifest，不能只交 summary；`pytest-tmp/` 是临时数据，无需归档。结果和 ZIP 均继承仓库忽略规则，需要单独传递，不等于仓库已提交的文件。

关键文件为 validation-report.json、source-audit.json、archive-audit.json、aicb-unit-probe.json、old-errors.csv、baseline-summary.json、blockers.json、pytest.log、pytest.xml。所有 JSON 禁止 NaN/Infinity；CSV 空白为缺失、reason 为原因；时间为秒、容量为 bytes、许可为整数。

唯一例外是 invalid/nonfinite.json：它故意含非法 NaN，用于验证读取器拒绝非有限输入，不作为有效输入或结果交付。

本轮正式验收已归档为 [20261031-phase1-final.zip](../../../results/dag/phase1/20261031-phase1-final.zip)，原展开目录已删除。ZIP 内保留 `20261031-phase1-final/` 顶层目录及14份正式报告、日志和 manifest，未包含 `pytest-tmp/`。归档逐文件比对原始字节并通过 ZIP 完整性检查。

归档 SHA-256：`36f7ac3dbfb32ea62f3d56e01dd6600f508f0ba2ba155b84a45ea5f5bafe4986`。解压到独立位置查看历史报告；重新验收应使用新的 run_id，不覆盖归档。

历史验收结果：18项静态检查与31项测试通过；有效精度样本0，7个候选场景阻塞，E2E 主指标 pending，阶段1整体尚未全部通过。该状态允许下游使用冻结接口开发，不允许宣称已完成精度提升。

归档 manifest 保存原验收时的文件身份；本次清理后仅更新交接文档，文档哈希自然不同，不回写历史 manifest。已清理 check/testcheck/test-import 中间结果、测试临时目录、Python/pytest 缓存和项目内依赖缓存；源码、测试、样例、schema 和配置表保留。后续运行仍会重新生成临时文件，可在保存正式结果后清理。

归档运行时的代码身份：基线 HEAD `354a9289e65a7d4ef58b6d232c628c8ebd4789a2` 加当时未提交工作区，完整输入哈希见运行 manifest。第一阶段源码、配置、测试和文档随后分批提交，提交记录以 Git 历史为准，不改写归档中的历史版本信息。未覆盖原始 baseline-data，未修改旧推理执行逻辑。

## 下游交接

交接时发送本目录、Git 提交版本及正式验收 ZIP；ZIP 未纳入 Git，接收者仅拉取仓库不会自动获得历史结果。没有 ZIP 时仍可安装依赖并用新的 run_id 复验，不能把缺少历史归档当作执行器缺陷。

阶段2实际执行三份图，对照期望起止，验证确定性、零时长收敛和一次完成。阶段3实现原子资源及 KV 协议，对照22/18/22μs资源场景。阶段4在原 Stage 事件位置接 coarse 图、保留原组批和 Token 语义；阶段5展开费用时核对来源表，避免旧 total_time 与子任务重复收费。

遗留问题：参考身份与单位补证、原始 trace 恢复、严格匹配的旧预测及 E2E 数据划分；AICB 秒/ms、TP、带宽及 PP>1 缺陷。逐场景原因位于 blockers.json。本阶段未新增执行器、资源实现、PD/MoE 运行功能或硬件精度声明。
