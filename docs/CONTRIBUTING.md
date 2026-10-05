# 贡献指南

## 基本规则

团队开发集成分支统一为 `dev`；`master` 保留为默认/历史基线分支，本周不迁移到 `main`。禁止直接向 `dev` 或默认分支推送实现，使用任务分支和目标为 `dev` 的 PR。历史成员分支不作为第二周集成入口。

管理员应为远程 `dev` 设置禁止 force-push/删除、至少一名非作者批准、必须检查通过和讨论解决后合并的保护规则。本文是团队约定，不表示远程保护已经启用；启动会上确认权限及实际保护状态。CI 的分支触发配置也不等于分支保护。

## 开发环境配置

- Linux Ubuntu 20.04+；GCC/G++ 9.4+；CMake 3.14+；Vidur 测试环境使用 Python 3.10+。
- 使用 `git submodule update --init --recursive` 初始化子模块。
- `.env.example` 仅供参考，构建脚本不会自动加载它；请在 shell 或 CI secret 配置中导出变量。不得提交 `.env`、Token、私有拓扑数据、画像日志、二进制文件或结果。
- 构建命令与注意事项见 `docs/getting_started/installation.md` 和 `docs/configuration/build-options.md`。

## 分支命名

```text
dev
├── week2-comm-contract
├── week2-ep-backend
├── week2-vidur-ep
└── week2-traffic-matrix
```

以上为本周主任务分支名；新增任务可使用 `feat/`、`fix/`、`docs/`、`refactor/`、`test/` 前缀，自动化新建分支默认用 `codex/`。每个分支只解决一个主题，合并后新任务从最新 `dev` 重新建分支。上游同步使用 `chore/upstream-sync-YYYYMMDD`。不要提交 `bin/`、`results/`、画像缓存或复制生成的 ns-3 后端文件。

### 从共同基线开工与同步

组长公布 `dev` 的起始 SHA 和固定子模块 SHA。以下在 Linux 仓库内执行，先确保 `git status` 干净；有自己的改动先保存，不用 reset/checkout 强行覆盖：

```bash
git fetch origin
git switch dev
git pull --ff-only origin dev
git switch -c <任务分支>
git submodule update --init --recursive
```

每天开始、发起评审和合并前同步 `origin/dev`：在任务分支运行 `git fetch origin`、`git merge origin/dev`，然后重跑受影响测试。团队统一用 merge 同步共享任务分支，不 rebase 已共享历史、不 force-push。发生冲突先与文件负责人确认；子模块内有改动时先保存，不强制更新覆盖。

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

### 任务卡与状态

任务拆到半天至一天可独立交付；超过一天的任务拆子项，不以“完成整个模块”作为首项任务。每项写明：任务编号、唯一负责人、评审人、文件/函数范围、输入/输出样例、依赖、截止工作日、验收命令和预期结果；实现后补实际结果及 PR 链接。命令尚未确定时标待确认，不编造通过记录。

状态统一为“待开始 → 开发中 → 待评审 → 待验收 → 完成”；阻塞作为附加标记，注明原因、所需协助人和下一次确认时间。PR 合入 `dev` 后进入待验收，独立复现/联调通过才完成。实现评审和验收可以由同一位非作者负责，但必须分别留下证据。

Issue/PR 维护任务细节，组长只在对应周验收表汇总状态和链接，不重复复制一套任务记录。每天同步交付、下一项和阻塞；接口阻塞超过半天由组长当天裁决。

## Pull Request 流程

1. 目标分支为 `dev`，按上述 merge 策略同步最新集成状态；不得对共享分支 force-push。
2. 完整填写 PR 模板，包括实际执行的命令/测试与跳过项。
3. 不提交生成输出；公开行为、配置、架构或上游变更必须同步更新文档。
4. 至少需要一名批准者；跨模块改动还需每个受影响组件的负责人批准。
5. 仅当必须 CI 通过、讨论已解决且满足完成定义后才能合并。
6. 每个 PR 保持小而聚焦，未完成可先开 Draft PR；不得把“计划运行”写成“测试通过”。评审批准后若有实质修改，重新请求受影响负责人评审。
7. 默认由成员一确认依赖和验收安排后使用普通 merge commit 合并，不 squash/rebase 团队共享提交。成员一自己的 PR 由非作者评审；实际合并可由有权限者执行，未经批准不能自合。
8. 接口改动先由调用方和实现方共同确认字段、单位、失败语义及迁移方式，再实现；子模块改动先在子模块仓库提交并提供可获取的 commit/PR，主仓库单独审核 gitlink 更新，不编辑复制生成目录。

当前 CI 覆盖元数据、Vidur 测试及 SimCCL 冒烟，不代表完整 ns-3 或 EP→Vidur 已通过。作者须补受影响模块的 Linux 测试；若 CI 失败或无法运行，保持待评审/待验收并说明原因，不把未触发检查视为通过。

## 周计划与验收文档

组长制定的小组计划、成果审核和验收记录统一放在 `docs/plan/weekN/`，如 `week1`、`week2`；实验记录可放在对应周的 `records/` 子目录。新增周次或迁移文件时同步更新 [周计划索引](plan/README.md)、[文档导航](README.md) 和相关相对链接，不保留多份并行维护的状态文档。

计划与实际验收分开记录：验收表注明更新日期、证据来源、完成状态和待补项，不把计划目标当作已完成成果。原始日志、CSV 等生成物保持在归档存储，文档引用运行编号、路径和校验值；本地 `results/` 不随 Git 分发，交付时需提供团队可获取的归档位置。总体路线图仍维护于 `docs/DEVELOPMENT_PLAN.md`。

本周统一验收入口为 [Week 2 验收表](plan/week2/week2_acceptance.md)，记录适用的 W2-A 编号、源码/输入身份、实际命令、结果、非作者审核、限制和归档获取位置。评审失败先修复并重测；合并后发现回归时由组长协调暂停后续依赖合并，以 revert PR 恢复可运行状态，不 reset 共享分支历史。

## Code Review

评审应检查正确性、可复现性、错误处理、测试、公开接口/文档变更、与固定子模块的兼容性及许可证影响。性能结论必须给出输入、硬件/拓扑元数据、基线和测量方法；不可验证的精度结论应被拒绝。

## 测试要求

- 文档/配置 PR：检查路径、链接、命令及治理 CI。
- Python 改动：目标 pytest 加语法/编译检查。
- SimCCL/Astra-Sim 改动：确定性的集合通信冒烟测试；影响算法或协议时运行完整 SimCCL 套件。
- ns-3/网络改动：固定小拓扑集成测试；未运行完整仿真时必须说明。
- GPU/校准改动：记录 GPU、驱动、CUDA、模型、拓扑、随机种子、输入 trace 与对比指标。

## 完成定义（Definition of Done）

下列为实现 PR 的合并条件；任务完成还须非作者验收，周完成还须周计划规定的端到端检查，不要求每个基础 PR 都先跑通整周闭环。

- 已关联 Issue，PR 描述范围清晰。
- 代码、配置和文档一致；不含生成产物或密钥。
- 适用测试通过；跳过项有明确理由。
- 新增或变更的公开 schema/配置包含兼容性和迁移说明。
- 已完成要求的评审批准和 CI 检查。
- 子模块更新时，PR 记录新旧 SHA、上游来源、测试结果和回滚路径。
