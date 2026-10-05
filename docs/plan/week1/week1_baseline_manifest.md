# 第一周统一基线清单

状态：基线固定；Linux LF 输入口径已复核，统一验收待补证

冻结日期：2026-09-02（Asia/Shanghai）

更新日期：2026-10-03（Asia/Shanghai）

负责人：成员一

## 1. 版本基线

| 对象 | 固定版本 | 说明 |
|---|---|---|
| 主仓库基线分支 | `master` | 历史集成基线；成员一当前工作分支为 `member1`，实验身份以实际 SHA 为准 |
| 主仓库提交 | `cf9ed25e41887a633c220ba1661a995ccab6d131` | 第一周实验统一基准提交 |
| `SimCCL` 子模块 | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` | 由主仓库 Git tree 记录确认 |
| `aicb` 子模块 | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` | 由主仓库 Git tree 记录确认 |
| `ns-3-alibabacloud` 子模块 | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` | 由主仓库 Git tree 记录确认 |

`.gitmodules` 只声明以上三个子模块。`astra-sim-alibabacloud` 与 `vidur-alibabacloud` 是主仓库直接跟踪的目录，其内容已经包含在主仓库提交中，不应另填“子模块 SHA”。

## 2. 固定输入及 SHA-256

| 用途 | 文件 | SHA-256 |
|---|---|---|
| 主通信基线 | `example/workload_analytical.txt` | `8c2e255aa7397d8c5c7e01daa04d4b3c97a6b015a27bd425770ef8e7e5cbe0a1` |
| 网络参数 | `example/busbw.yaml` | `ae063b004c098c15f3e5e3cf78c037f13187a06f5394499a876b8c86094a1a87` |
| 最小通信冒烟 | `example/microAllReduce.txt` | `5aea5b1afc033d4423897323348c0ed8eac6596ef7b5ce66a6017c259c0caae2` |
| PD 调度测试 | `vidur-alibabacloud/tests/test_pd_separation.py` | `c1d627de37e60c309c7d9101f4de082083b1ac5df0615ec029bfb1d9b9e203a5` |

上表是正式 Linux LF 检出哈希，与成员四记录及本次内存换行规范化复核一致。Day 1 原哈希来自 Windows CRLF；原 Day 2 文档已不在当前文档树中，不能再以其作为可访问的历史值来源。成员一保留的原始证据位置见 [验收表](week1_acceptance.md)。跨平台哈希不同应先核对 Git blob 和换行方式；同为 LF 却不一致则检查输入差异，未解释前不横向比较。

## 3. 统一环境要求

- Ubuntu 20.04 或更高版本。
- GCC/G++ 9.4 或更高版本。
- CMake 3.14 或更高版本。
- Python 3.10 或更高版本；记录 pytest 版本。
- 记录内核、CPU 型号、逻辑核数、内存总量和可用磁盘空间。
- 正式记录必须来自 Linux 环境；Windows 只用于文档和只读预检。

## 4. 统一命令

版本与输入检查：

```bash
git rev-parse HEAD
git submodule status --recursive
sha256sum example/workload_analytical.txt \
  example/busbw.yaml \
  example/microAllReduce.txt \
  vidur-alibabacloud/tests/test_pd_separation.py
```

初始化与主通信基线：

```bash
git submodule update --init --recursive
./scripts/build.sh -c analytical
./bin/SimAI_analytical -w ./example/workload_analytical.txt \
  -g 9216 -nv 360 -nic 48.5 -n_p_s 8 -g_p_s 8 -r example-
```

Vidur PD 基线：

```bash
cd vidur-alibabacloud
pytest tests/test_pd_separation.py
```

已取得成员二成功的 ns-3 冒烟记录（`W1-M2-20260905-02`）：

```bash
python3 ./astra-sim-alibabacloud/inputs/topo/gen_Topo_Template.py \
  --ro -g 8 -gt H20 -bw 200Gbps -nvbw 2400Gbps
./bin/SimAI_simulator -t 8 \
  -w ./example/microAllReduce.txt \
  -n ./Rail_Opti_SingleToR_8g_8gps_200Gbps_H20 \
  -c ./astra-sim-alibabacloud/inputs/config/SimAI.conf
```

日志含 2/2 streams 完成；完整环境、版本、拓扑/config 原件及退出码仍待补证。

## 5. 记录与归档规则

- 每次运行使用独立记录，模板见 [实验记录模板](../../templates/experiment_record.md)；组长计划与验收文档统一归档在 `docs/plan/weekN/`，本周新增实验记录可放在 `docs/plan/week1/records/`，目录规则见 [周计划总索引](../README.md)。
- 记录编号格式：`W1-M<成员编号>-YYYYMMDD-<序号>`。
- 原始日志文件名：`<记录编号>-<任务>-stdout.log` 和 `<记录编号>-<任务>-stderr.log`。
- 结果归档按“成员/记录编号/任务”组织；生成物不提交 Git。
- 文档中记录结果位置和校验值，不提交 `bin/`、`results/`、缓存、私有画像或密钥。
- 所有失败必须保留退出码、错误原文、最小复现步骤和已排查项。
- 只有顶层提交、三个子模块 SHA、固定输入哈希和命令口径均一致的结果，才能进入横向比较。

## 6. 仓库治理口径

- 不直接在 `master` 开发；文档、实验、设计或修复分别使用单一主题分支和 PR。
- Issue 使用现有 `.github/ISSUE_TEMPLATE/` 模板；PR 使用现有 `.github/pull_request_template.md`。
- 第一周发现的核心逻辑问题先记录 Issue，不为制造“成功结果”而临时修改算法。
- 跨模块接口变更必须先有设计 Issue，并由受影响模块负责人共同审核。
- 子模块版本变更必须记录新旧 SHA、上游来源、测试结果和回滚方式。

## 7. 当前验收边界

成员一 Day 2 已通过 Ubuntu 22.04 WSL2 采集子模块 SHA 并运行基线。早期 Windows Git PATH 问题已不再阻碍 Linux 检查；从 Windows 挂载目录运行仍须注意 CRLF。

截至 2026-10-03，成员二、三、四成果均已取得并审核。成员二身份资料、成员三 Linux 实验和成员四完整日志仍待补证，最新进度见 [验收表](week1_acceptance.md)。

`busbw.yaml` 保留作文件身份记录；主命令按参数自动计算，并不读取它，当前 binary 也不支持 `-busbw`。记录该文件存在不能解释为配置已加载。
