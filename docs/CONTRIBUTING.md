# 贡献指南

## 基本规则

禁止直接在默认分支开发。当前仓库检出分支为 `master`，但团队工作流以受保护的 `main` 作为集成分支。**TODO：仓库管理员批准并执行 `master` → `main` 默认分支迁移后，再启用 `main` 保护。** 在此之前，`master` 必须执行同等的保护和 PR 规则。

## 开发环境配置

- Linux Ubuntu 20.04+；GCC/G++ 9.4+；CMake 3.14+；Vidur 测试环境使用 Python 3.10+。
- 使用 `git submodule update --init --recursive` 初始化子模块。
- `.env.example` 仅供参考，构建脚本不会自动加载它；请在 shell 或 CI secret 配置中导出变量。不得提交 `.env`、Token、私有拓扑数据、画像日志、二进制文件或结果。
- 构建命令与注意事项见 `docs/getting_started/installation.md` 和 `docs/configuration/build-options.md`。

## 分支命名

```text
main
├── feat/<short-topic>
├── fix/<short-topic>
├── docs/<short-topic>
├── refactor/<short-topic>
└── test/<short-topic>
```

每个分支只解决一个主题。上游同步使用 `chore/upstream-sync-YYYYMMDD`。不要提交 `bin/`、`results/`、画像缓存或复制生成的 ns-3 后端文件。

## Commit 规范

推荐使用 Conventional Commit 风格：

```text
feat: add EP traffic-matrix schema
fix: preserve topology hash in cache key
docs: clarify ns-3 build requirements
test: cover PD cluster split
refactor: isolate communication result adapter
chore: update pinned submodule commit
```

标题使用祈使句并限定范围；不兼容行为、数据 schema 变更或上游 SHA 变更必须在正文说明。

## Issue 流程

1. 先搜索重复项，再用提供的功能或缺陷模板创建 Issue。
2. 说明背景、目标、任务、验收标准、相关文件、依赖、负责人和里程碑。
3. 在分支和 PR 中关联 Issue；架构/API 变更必须先有设计 Issue。

## Pull Request 流程

1. 按团队策略 rebase 或合并当前受保护分支；不得对共享分支 force-push。
2. 完整填写 PR 模板，包括实际执行的命令/测试与跳过项。
3. 不提交生成输出；公开行为、配置、架构或上游变更必须同步更新文档。
4. 至少需要一名批准者；跨模块改动还需每个受影响组件的负责人批准。
5. 仅当必须 CI 通过、讨论已解决且满足完成定义后才能合并。

## Code Review

评审应检查正确性、可复现性、错误处理、测试、公开接口/文档变更、与固定子模块的兼容性及许可证影响。性能结论必须给出输入、硬件/拓扑元数据、基线和测量方法；不可验证的精度结论应被拒绝。

## 测试要求

- 文档/配置 PR：检查路径、链接、命令及治理 CI。
- Python 改动：目标 pytest 加语法/编译检查。
- SimCCL/Astra-Sim 改动：确定性的集合通信冒烟测试；影响算法或协议时运行完整 SimCCL 套件。
- ns-3/网络改动：固定小拓扑集成测试；未运行完整仿真时必须说明。
- GPU/校准改动：记录 GPU、驱动、CUDA、模型、拓扑、随机种子、输入 trace 与对比指标。

## 完成定义（Definition of Done）

- 已关联 Issue，PR 描述范围清晰。
- 代码、配置和文档一致；不含生成产物或密钥。
- 适用测试通过；跳过项有明确理由。
- 新增或变更的公开 schema/配置包含兼容性和迁移说明。
- 已完成要求的评审批准和 CI 检查。
- 子模块更新时，PR 记录新旧 SHA、上游来源、测试结果和回滚路径。
