# 打开 SimAI 知识图谱 Dashboard —— 全流程

> 本文档说明：如何生成 SimAI 项目的知识图谱，以及如何启动交互式可视化 Dashboard。
> 适用范围：本仓库（SimAI，排除 ns-3-alibabacloud/ 子模块）。
> 最后更新：2026-09-02

---

## 一、这是什么

`understand-anything` 是一个 Claude Code 插件，能把整个代码库分析成一张**知识图谱**（`knowledge-graph.json`），并用一个本地 Web Dashboard 交互式浏览。

- **图谱内容**：文件、函数、类、文档、配置、数据表等节点 + 它们之间的 imports / calls / contains / exports / configures 等边。
- **产物文件**：`.ua/knowledge-graph.json`（图谱本体）、`.ua/fingerprints.json`（增量更新指纹）、`.ua/meta.json`（元信息）。

两个命令分别负责两件事：

| 命令 | 作用 | 产出 |
|------|------|------|
| `/understand` | 分析代码库，生成知识图谱 | `.ua/knowledge-graph.json` |
| `/understand-dashboard` | 启动可视化服务，浏览图谱 | 一个本地 URL（含 token） |

---

## 二、前置条件

1. **环境**：Node.js ≥ 22、`pnpm`、`npx` 均已安装（本机位于 `/c/nvm4w/nodejs/`）。
2. **图谱已生成**：`.ua/knowledge-graph.json` 存在。若不存在，先运行 `/understand`。

---

## 三、快速方式（推荐）

在 Claude Code 对话框直接输入：

```
/understand-dashboard
```

它会自动：定位项目 → 校验图谱 → 启动服务 → 返回带 token 的访问 URL。你只需点击返回的链接即可。

---

## 四、手动方式（完整命令）

当 `/understand-dashboard` 不可用，或需要手动排查时，按以下步骤执行。

### 4.1 定位路径

```bash
PROJECT_DIR="C:/Users/zhongjiahui/Desktop/FinalSimAI/SimAI"
UA_DIR="$PROJECT_DIR/.ua"                    # 本项目使用 .ua/（非旧的 .understand-anything/）
PLUGIN_ROOT="C:/Users/zhongjiahui/.claude/plugins/cache/understand-anything/understand-anything/2.9.4"
DASHBOARD_DIR="$PLUGIN_ROOT/packages/dashboard"
```

### 4.2 校验图谱存在

```bash
test -f "$UA_DIR/knowledge-graph.json" && echo "OK" || echo "请先运行 /understand"
```

### 4.3 启动 Dashboard（两条路径，优先 Fast path）

**Fast path（优先）** —— 下载官方预打包 viewer，无需 build：

```bash
PLUGIN_VERSION=$(node -p "require('$PLUGIN_ROOT/package.json').version")
VIEWER_URL="https://github.com/Egonex-AI/Understand-Anything/releases/download/v${PLUGIN_VERSION}/understand-anything-viewer.tgz"
npx --yes "$VIEWER_URL" "$PROJECT_DIR"
```

> ⚠️ 需要访问 GitHub Releases。本机实测**失败**（拉取超时，国内网络访问 GitHub 不稳定），自动回退到下面的本地 Vite 方式。

**Fallback（本地 Vite）** —— 依赖已在插件目录装好，直接起 dev server：

```bash
cd "$DASHBOARD_DIR"
GRAPH_DIR="$PROJECT_DIR" npx vite --host 127.0.0.1
```

> 若首次运行报缺依赖，先执行 `cd "$DASHBOARD_DIR" && pnpm install`，再 `cd "$PLUGIN_ROOT" && pnpm --filter @understand-anything/core build`。

### 4.4 获取访问 URL（含 token）

服务启动后，在输出里找这一行：

```
🔑  Dashboard URL: http://127.0.0.1:5173/?token=xxxxxxxxxxxxxxxxxxxxxxxx
```

- **必须带 `?token=` 参数**，否则页面会被「Access Token Required」拦截。
- 端口默认 `5173`，被占用时会自动顺延到下一个可用端口。
- token 每次启动都会重新生成。

### 4.5 打开浏览器

Windows 下用默认浏览器打开（把下面的 URL 换成 4.4 里拿到的实际地址）：

```powershell
Start-Process "http://127.0.0.1:5173/?token=xxxxxxxx"
```

---

## 五、本次（2026-09-02）实际执行记录

| 步骤 | 结果 |
|------|------|
| `/understand` 全量分析（排除 ns-3） | ✅ 7 阶段全通，500 文件 → 1263 节点 / 2219 边 / 6 层 / 11 步导览 |
| Fast path（npx 下载 viewer） | ❌ GitHub Releases 拉取超时，exit code 1 |
| Fallback（本地 Vite dev server） | ✅ 启动成功，`http://127.0.0.1:5173/?token=1a24eac2bd8b7dfdf7948f0826fced71` |
| 浏览器打开 | ✅ 通过 `Start-Process` 成功 |

**结论**：本机（国内网络）应**直接走 Vite 本地方式**，跳过 Fast path，避免 GitHub 下载卡顿。

---

## 六、常见问题排查

| 现象 | 原因 | 处理 |
|------|------|------|
| 页面显示「Access Token Required」 | URL 漏了 `?token=` | 从启动日志复制完整 URL（含 token） |
| `npx --yes <viewer.tgz>` 卡住或报错 | GitHub 网络不通 | 放弃 Fast path，改走 Vite fallback（见 4.3） |
| Vite 报 `Cannot find module` | dashboard 依赖未装 | `cd "$DASHBOARD_DIR" && pnpm install` |
| 端口 5173 已占用 | 其他进程占用了 | Vite 会自动换端口；或手动 `--port 5174` |
| `pnpm: command not found` | pnpm 未安装 | 安装 pnpm ≥ 10 |

---

## 七、停止服务

- 交互式终端里按 `Ctrl+C`。
- 或在 Claude Code 里让助手停掉对应的后台任务。
