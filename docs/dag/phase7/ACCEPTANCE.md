# 第七阶段功能验收记录 · 2026-11-14

分支 `dev-v7` 的动态 MoE 功能首版已通过功能验收，精度验收仍缺匹配参考。
支持边界、输入契约和复现步骤见 [README](README.md)。

| 验证项 | 结果 |
|---|---|
| 完整回归 | 224 项通过，0 失败、0 跳过；包含前五阶段及 31 项新增 MoE 测试 |
| 受控探针与原 CLI 检查 | 17 项全部通过 |
| 原 CLI 请求流程 | 两请求全部完成，各处理 8 个 prefill、4 个 decode token |
| 动态展开 | 8 次 Stage/iteration，256 个逐层路由结果，2680 个任务 |
| 依赖与结算 | join 等待必需分支；StageEnd/terminal 各一次；费用按最终图结算 |
| 共享资源 | 同卡排队、异卡并行、共享 NIC 等待，容量验证通过且最终占用为零 |
| 合成均衡探针 | 每个 Expert 4 assignments，Stage 约 16.001 ms |
| 合成热点探针 | e0/e1 各 8 assignments，e2/e3 空载，Stage 约 32.001 ms |
| 精度与硬件校准 | `blocked_missing_matched_moe_reference`，未宣称精度改善 |

测试覆盖完整 source→destination 矩阵与 token 守恒、同轮 up/down 路由复用、
多轮与多层追加、画像严格匹配及缺失失败、证据哈希、失败后的资源清理、
AICB 原聚合费用替换和零 MoE 层保护。合成压力结果与真实负载精度验证分开报告。

Python 3.12 / Windows 下完整回归约 312 秒，验收脚本总墙钟约 376 秒。
脚本结果为功能 passed、精度 blocked，对应退出码 2。

## 验收包

[下载验收包](artifacts/20261114-phase7-delivery.zip)，约 787 KiB。
包中共 310 个文件，解压后包含：

- `20261114-phase7-acceptance-04/`：最终通过的一次运行；含 111 份带哈希产物及
  `run-manifest.json`，包括 pytest、原 CLI 命令/日志、动态图、矩阵、负载和实际时间线。
- `tested-source/`：198 份测试时源码/配置快照，对应 manifest 的 `source_sha256`。
  这是保留测试工作区原始字节的证据，包含 Windows 换行；Git 跨平台检出可能归一化换行。

测试在提交前工作区执行，manifest 的启动 HEAD 为阶段五交接提交 `e4b89ad`。
新增实现由源码快照、源文件哈希和启动时工作区差异共同固定，不能只用启动 HEAD 判断版本。
打包前已逐项复核源码与产物哈希，打包后再次核验 ZIP 内容及 CRC。

完整 SHA-256：

```text
86871304c7ef4b6d0c383ea4d1a198cc268bd218d3ebdca358ab5c39fe1275d7
```

精度验证下一步需要模型/设备/TP/PP/EP/dtype 一致的 Expert 负载画像、完整逐轮路由和
独立时延参考，并分离校准和验证数据。当前交付不包含阶段六 PD 或阶段八联合/规模验收。
