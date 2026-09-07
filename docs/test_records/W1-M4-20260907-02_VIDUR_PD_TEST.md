# W1-M4-20260907-02：Vidur PD 测试记录

## 1. 基本信息

| 字段 | 内容 |
|---|---|
| 记录编号 | `W1-M4-20260907-02` |
| 负责人 | 成员四 |
| 日期与时区 | 2026-09-07，Asia/Shanghai（UTC+08:00） |
| 实验目的 | 验证 Vidur 子模块的 PD 分离配置与校验逻辑在固定版本下通过单元测试 |
| 任务类别 | Vidur PD |
| 通过标准 | 指定测试文件全部通过，退出码为 0，并记录隔离环境及依赖 |

## 2. 环境

| 字段 | 内容 |
|---|---|
| 操作系统与版本 | Ubuntu 24.04.4 LTS，WSL2，x86-64 |
| 内核 | `6.18.33.2-microsoft-standard-WSL2` |
| CPU/逻辑核数 | AMD Ryzen 7 9800X3D；16 逻辑核 |
| 内存 | 30 GiB；采集时可用 29 GiB |
| 可用磁盘 | ext4 `/dev/sdd`；采集时可用 954 GiB |
| GCC/G++ | 13.3.0 / 13.3.0（本测试不直接编译 C/C++） |
| CMake | 3.28.3（本测试不直接调用） |
| Python/pip/pytest | Python 3.12.3 / pip 24.0 / pytest 9.1.1 |
| 其他关键依赖 | networkx 3.6.1；隔离环境 `.venv-week1` |

## 3. 版本与工作区

| 字段 | 内容 |
|---|---|
| 顶层 Git SHA | `cf9ed25e41887a633c220ba1661a995ccab6d131` |
| `SimCCL` SHA | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` |
| `aicb` SHA | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` |
| `ns-3-alibabacloud` SHA | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` |
| 当前分支 | `master` |
| 工作区是否干净 | 否；仅有未跟踪的 `vidur-alibabacloud/.venv-week1/`，为本测试隔离依赖，不修改被测源码 |

## 4. 输入与配置

| 文件或参数 | 值 | SHA-256/来源 |
|---|---|---|
| 测试文件 | `vidur-alibabacloud/tests/test_pd_separation.py` | `c1d627de37e60c309c7d9101f4de082083b1ac5df0615ec029bfb1d9b9e203a5` |
| 网络/拓扑配置 | `N/A` | 单元测试不启动网络仿真 |
| 其他配置 | pytest quiet mode `-q` | 实际命令 |
| 随机种子 | `N/A` | 该测试不使用随机输入 |

完整输入哈希命令：

```bash
sha256sum tests/test_pd_separation.py
```

## 5. 执行记录

| 字段 | 内容 |
|---|---|
| 完整命令 | 见下方原文 |
| 工作目录 | `/root/SimAI-week1/vidur-alibabacloud` |
| 开始时间 | `N/A`（引入本模板前未单独记录） |
| 结束时间 | 2026-09-07 +08:00；精确时刻未在原测试日志中保留 |
| Wall time | pytest 报告 0.13 s |
| 退出码 | 0 |
| stdout 日志 | 未单独归档；关键输出见下方摘录 |
| stderr 日志 | 无失败输出；未单独归档 |
| 结果目录/文件 | `N/A`；单元测试仅返回测试报告 |

```bash
python3 -m venv .venv-week1
.venv-week1/bin/python -m pip install pytest networkx
.venv-week1/bin/python -m pytest tests/test_pd_separation.py -q
```

## 6. 结果

| 指标或检查项 | 实际结果 | 单位/口径 | 是否达到通过标准 |
|---|---|---|---|
| 测试通过数 | 10 | pytest case | 是 |
| 测试失败数 | 0 | pytest case | 是 |
| pytest 用时 | 0.13 | s | 是 |
| PD 关闭路径 | 通过 | 测试断言 | 是 |
| Prefill/Decode 独立 world size | 通过 | 测试断言 | 是 |
| 参数回退与非法比例拒绝 | 通过 | 测试断言 | 是 |
| 显式 Prefill 副本优先级 | 通过 | 测试断言 | 是 |

关键输出摘录：

```text
..........                                                               [100%]
10 passed in 0.13s
```

## 7. 失败与排查

| 字段 | 内容 |
|---|---|
| 失败阶段 | 初始依赖检查：系统环境缺少 pytest；最终测试阶段为 `N/A`（全部通过） |
| 错误原文 | 系统 Python 无 pytest；通过独立 venv 安装测试最小依赖解决 |
| 最小复现步骤 | 在第 5 节工作目录运行最后一条 pytest 命令 |
| 已排查项 | Python 版本、pytest/networkx 版本、测试文件哈希、退出码、通过数 |
| 尚未排查项 | 完整 Vidur 测试套件与真实 PD serving 性能未纳入本次任务 |
| 关联 Issue | `N/A` |
| 是否修改核心逻辑 | 否 |

## 8. 结论与边界

- 结论：固定 Vidur 版本的 PD 配置逻辑通过计划指定的 10 个测试。
- 本次结果能够验证：PD 开关、Prefill/Decode 资源参数、回退规则和非法配置校验的代码行为。
- 本次结果不能验证：真实请求的 TTFT/TPOT、KV 传输成本、跨节点性能或 SimAI 与 Vidur 的数值一致性。
- 与其他成员结果的可比性：在相同顶层/子模块 SHA、测试文件哈希和 Python 依赖版本下可直接复测。
- 后续动作与负责人：成员四后续将 PD 测试结果作为请求级校准的行为基线；真实性能数据需由后续实验补充。

## 9. 审核

| 字段 | 内容 |
|---|---|
| 提交人确认 | 成员四，2026-09-07 |
| 成员一审核 | 待审核 |
| 审核意见 | 待填写 |
