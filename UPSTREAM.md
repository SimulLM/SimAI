# 上游基线与同步策略

## 主仓库

| 项目 | 已记录值 | 依据 |
|---|---|---|
| 上游仓库 | `https://github.com/aliyun/SimAI.git` | 本地 `upstream` remote |
| 当前 Fork | `https://github.com/SimulLM/SimAI.git` | 本地 `origin` remote |
| 基线分支 | `upstream/master` | 本地远程跟踪分支 |
| 基线提交 | `cef83f9ddd96540e3e9f48934f11335d52d54fce` | `HEAD`、`upstream/master`，2026-08-14 |
| 上游发布背景 | SimAI 1.7 | `CHANGELOG.md` |
| 根许可证 | Apache License 2.0 | `LICENSE` |

创建本文件时，`HEAD` 与 `upstream/master` 指向同一提交。这只是当时的本地记录，不代表远程仓库不会继续变化。

## 仓库关系与布局

本仓库是 SimAI 的维护型 Fork。`astra-sim-alibabacloud` 和 `vidur-alibabacloud` 由父仓库直接跟踪；以下目录为 Git 子模块，拥有独立历史：

| 路径 | 固定提交 | `.gitmodules` 中的读取地址 | 本地观察到的许可证 |
|---|---|---|---|
| `SimCCL` | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` | `https://github.com/SimulLM/SimCCL.git` | Apache-2.0（`SimCCL/LICENSE`） |
| `aicb` | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` | `https://github.com/SimulLM/aicb.git` | Apache-2.0 声明（`aicb/License`） |
| `ns-3-alibabacloud` | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` | `https://github.com/aliyun/ns-3-alibabacloud` | GPL-2.0（`ns-3-alibabacloud/LICENSE`） |

计划中的开发预计会修改 SimCCL 与 AICB，因此它们指向团队 Fork；其本地 `origin` 为 SimulLM Fork，`upstream` 仍为对应的 aliyun 仓库。ns-3 子模块暂保留上游地址，直到明确需要变更其 RDMA、NIC、交换机、队列或拓扑行为。

## 许可证说明

父仓库保持 Apache-2.0。ns-3 子模块为 GPL-2.0，顶层构建脚本会在 ns-3 模式下将其复制到 Astra-Sim 构建目录。发布包含或链接该组合的二进制文件或镜像前，必须进行许可证/合规审查。本文档仅记录技术观察，不构成法律意见。

## 同步策略

1. 不要在功能分支上随意执行 `git submodule update --remote`：它可能同时推进多个独立代码库。
2. 创建专用 `chore/upstream-sync-YYYYMMDD` 分支和一条跟踪 Issue。
3. 拉取各上游远程，记录候选提交，阅读发行说明，并按父仓库、SimCCL、AICB、ns-3 分类变更。
4. 一次只更新一个组件；在父仓库提交中保留精确子模块 SHA，并运行相应构建/测试矩阵。
5. 在归属仓库解决冲突，不要修改生成的 `extern/network_backend/ns3-interface` 文件。
6. PR 必须说明新旧提交、许可证影响、兼容性影响、已运行测试及回滚提交。

## 已知同步风险

- SimAI、SimCCL、AICB、ns-3 独立演进；父仓库提交可兼容并不意味着更新后的子模块 HEAD 仍兼容。
- CMake 文件在 Astra-Sim 与 `SimCCL/src/mock` 之间使用相对路径；改变目录布局或 mock 版本可能导致构建失败。
- `scripts/build.sh -c ns3` 会把 ns-3 子模块复制到生成的 Astra-Sim 目录，因此生成文件不能作为事实来源。
- AICB 输出 schema 被 Vidur 缓存/预测器代码消费；上游变更可能悄然使缓存 profile 失效。
- TODO：第一次上游同步前，定义受支持的 Linux 编译器/CUDA/驱动矩阵，并保存基线测试报告。
