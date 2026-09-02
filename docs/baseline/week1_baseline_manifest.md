# 第一周统一基线清单

状态：候选基线已冻结，等待四位成员在统一 Linux 环境确认  
冻结日期：2026-09-02（Asia/Shanghai）  
负责人：成员一

## 1. 版本基线

| 对象 | 固定版本 | 说明 |
|---|---|---|
| 主仓库分支 | `master` | 当前实际检出分支；在默认分支迁移完成前按受保护分支规则管理 |
| 主仓库提交 | `cf9ed25e41887a633c220ba1661a995ccab6d131` | 第一周实验统一基准提交 |
| `SimCCL` 子模块 | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` | 由主仓库 Git tree 记录确认 |
| `aicb` 子模块 | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` | 由主仓库 Git tree 记录确认 |
| `ns-3-alibabacloud` 子模块 | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` | 由主仓库 Git tree 记录确认 |

`.gitmodules` 只声明以上三个子模块。`astra-sim-alibabacloud` 与 `vidur-alibabacloud` 是主仓库直接跟踪的目录，其内容已经包含在主仓库提交中，不应另填“子模块 SHA”。

## 2. 固定输入及 SHA-256

| 用途 | 文件 | SHA-256 |
|---|---|---|
| 主通信基线 | `example/workload_analytical.txt` | `25b4458383fc584034203c39dd99db61995f4cde8caed50cd930c3fa2b5770aa` |
| 网络参数 | `example/busbw.yaml` | `7f262ce340bd6800c111bace3492f09b9fad340b8d1fd07cf99258a3bb8b9fe5` |
| 最小通信冒烟 | `example/microAllReduce.txt` | `6884bc5b9623a42a04b862ea7af58fdf820f75b13b92e6ea5f3f6b42b0f8115e` |
| PD 调度测试 | `vidur-alibabacloud/tests/test_pd_separation.py` | `821efc780a4952e552ef8a44b5b4c76916af49d18dcea84e39989fb5197cf0db` |

任何哈希不一致均视为输入不一致，不能与统一基线直接比较。

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

最小通信冒烟的实际命令由成员二根据仓库当前 CLI 入口补充，并在执行前由成员一审核；不得猜测参数或用不同输入替代。

## 5. 记录与归档规则

- 每次运行使用独立记录，模板见 `docs/templates/experiment_record.md`。
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

## 7. 当前限制

本清单是在 Windows 工作区通过只读命令生成。当前 Windows Git for Windows 环境的 `git submodule status --recursive` 因 PATH 中缺少 `basename`、`sed` 和 `git-sh-setup` 无法运行；上述三个子模块 SHA 改由 `git ls-tree HEAD` 从主仓库提交树可靠读取。正式 Day 1 确认仍须在统一 Linux 环境重新运行全部版本检查命令。

当前工作区含尚未提交的第一周计划和本次 Day 1 文档。执行实验前，每位成员必须记录工作区状态；建议从固定提交建立干净实验检出，避免把文档工作区误当作干净基线。
