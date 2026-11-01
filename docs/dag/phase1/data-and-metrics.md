# 数据与精度协议

## 当前可用性与准入

`configs/dag/phase1/reference-inventory.csv` 逐项列出归档 manifest 的82份文件，包含路径、SHA-256、来源、属性、粒度、单位证据、身份缺项及用途。82份校验通过只能证明迁入完整，不能补齐缺失的实验身份。原始 ZIP 共48个文件条目，无 prefill.json/decode.json。

analytical/ns-3 为通信模拟候选；DeepSeek 派生统计用于行为参考，恢复原始 trace 并修正小数时间截断后才可作为局部数值参考；MoE loads 用于合成逻辑测试；PD 测试用于配置检查；quarantine 一律排除精度和 cost。单 GPU rank 的 kernel 区间不代表完整请求、完整网络传输或 TTFT/ITL。

现有 `data-pairs.csv` 有7个明确阻塞的场景，没有 eligible 配对。`dataset-split.csv` 将这些组排除；这不是已冻结的最终验证集。`support-matrix.csv` 分离契约支持、旧路径运行、配对与精度资格；未运行填 not_run，未知字段留空。多个模型名/backend 的分号列表是共享限制的候选族，不是已测配置。

## 配对与导入

配对表列为 pair_id、reference_record、old_record、status、reason、group_id。status=eligible 才尝试计算；blocked 行完整保留到误差表。两个 record 是项目内 JSON 文件，按以下字段准备：

- model、hardware、input_sha256、batch、tp、pp、ep、topology_sha256、dtype、metric、metric_definition：双方必须相同且已知。batch/tp/pp/ep 为正整数，两个输入 SHA 必须为64位小写十六进制。非网络场景也须给出明确描述文件的 topology SHA，不能用 unknown 当通配符。
- run_id、version、group_id、nature、verification：版本填写实际运行版本；nature 仅 measured/simulated/estimated 可入精度表，旧结果必须 simulated；verification 必须 verified。
- raw_value、raw_unit、conversion_to_s、unit_evidence：保留原始值和单位证据，只接受 s/ms/us/ns，禁止猜测 tick 或无说明的 CSV 单位。
- evidence：非空数组，每项含项目相对 path 和 sha256。哈希不符、quarantine 路径和仍未核验的归档原件均拒绝。需要独立的新补证材料和记录，不直接把 manifest 的 false 改成 true。

示例结构见 `configs/dag/phase1/record-template.json`，它故意含 null 身份，不能直接进入精度验收。`scripts/dag_phase1/import_results.py` 显式指定 CSV、零起始数据行、列名和 metadata JSON 导入一条结果，不自动推断单位或提升 verification：

```text
python scripts/dag_phase1/import_results.py --csv <root-relative.csv> --row 0 --column <metric-column> --metadata <metadata.json> --output results/dag/phase1/<new-run-id>/old-record.json
```

CSV 导入选择器保存在记录中。日志和命令、输入配置应作为 evidence 一同保留。历史运行缺元数据时，新建运行补跑；不将当前源码的默认配置倒推为历史配置。本地没有 SimAI 可执行文件，当前 Python 环境未准备 Vidur 依赖，本轮不运行无匹配参考的端到端仿真。

## 数据划分与指标

dataset-split 仅接受 calibration/validation/excluded，每个 group 只出现一次。同一 workload/config 或同一参考证据不能分属不同 group；程序拒绝这样的配对。整个 trace 及其派生统计按同组管理，不把 kernel 行随机切分进两套集合。最终验证集冻结后不得用于 cost 参数拟合。

优先主指标：`request_e2e` 的平均相对误差；metric_definition 为统一的“请求完成时间减请求到达时间”。仅在严格配对 E2E 样本覆盖 calibration 和 validation 后标记 frozen，否则保持 pending。局部 collective、kernel 指标分别命名、分组报告，不替代请求 E2E。

`absolute_error_s=abs(old_s-reference_s)`；非零参考时 `relative_error=absolute_error_s/abs(reference_s)`。零参考只输出绝对误差；任一集合没有非零 E2E 参考值时不能冻结平均相对误差主指标。汇总按 metric、split、reference_nature 分开，报告样本数和非零参考数，不混合 measured/simulated/estimated，不输出混合量纲或粒度的单个平均误差。没有样本时误差为 null。

阶段1只建立旧基线，未实现新 DAG 的误差降低比较。后续必须在同 cost 下比较时序贡献，再单列 cost 修订贡献；报告每样本改善/持平/退化、主要误差及墙钟开销。参考若为模拟或估计，结论只可说相对该参考误差，不声称硬件精度。

## 退出码及补齐条件

validate：0 表示静态契约检查通过，1 表示检查失败。evaluate_baseline：0 表示具备已冻结分组的 E2E 基线，2 表示精度基线未通过；数据格式/路径等异常为运行错误，不应吞掉。所有排除原因落盘。

补齐顺序：恢复输入、拓扑、配置及版本身份→证明指标与单位→恢复原始 trace 或获得匹配实测→固定旧预测运行→划分 calibration/validation→运行配对评估。通信 ns-3 候选可先独立配对局部指标，仍不自动解除 E2E 阻塞。
