# 成员四：第一周环境与输入基线记录

## 1. 记录状态

- 初次记录时间：2026-09-02 11:05:09 +08:00（Asia/Shanghai）
- Linux 验收时间：2026-09-02 11:27:40 +08:00（Asia/Shanghai）
- 记录人：成员四
- 仓库与输入基线：已完成
- 子模块初始化：已完成
- 统一 Linux 环境验收：已完成（Ubuntu 24.04.4 LTS，WSL2）
- 解析后端构建、主通信基线与 Vidur PD pytest：已完成并归档

## 2. 主仓库版本

| 项目 | 记录值 |
|---|---|
| 远端 | `https://github.com/SimulLM/SimAI.git` |
| 分支 | `master` |
| Git SHA | `cf9ed25e41887a633c220ba1661a995ccab6d131` |
| 最新提交 | `docs: 更新文档以包含 DeepSeek profile-data 校准策略和相关信息` |
| 同步结果 | `git pull --ff-only` 返回 `Already up to date.` |
| Windows 工作区状态 | 同步时干净；当前仅新增本环境记录文件，尚未提交 |
| Linux 正式验收目录 | `/root/SimAI-week1`，ext4 干净克隆 |

## 3. 子模块版本

已执行：

```bash
git submodule update --init --recursive
```

| 子模块 | Git SHA |
|---|---|
| SimCCL | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` |
| aicb | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` |
| ns-3-alibabacloud | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` |

说明：这里记录的是主仓库当前固定的 gitlink 提交，不使用 `git submodule update --remote`，避免各成员拉到不同的子模块版本。

## 4. 固定输入及校验值

哈希算法统一使用 SHA-256。

以下是 Ubuntu ext4 干净克隆中的正式验收值。

| 用途 | 文件 | Linux SHA-256 | Git blob |
|---|---|---|---|
| 主通信基线 | `example/workload_analytical.txt` | `8C2E255AA7397D8C5C7E01DAA04D4B3C97A6B015A27BD425770EF8E7E5CBE0A1` | `90a4882c951f865740c0c6498a618e2fba70f261` |
| 网络参数 | `example/busbw.yaml` | `AE063B004C098C15F3E5E3CF78C037F13187A06F5394499A876B8C86094A1A87` | `398a2dc5ed2865c10d16111be973bc15a8462c00` |
| 最小通信冒烟 | `example/microAllReduce.txt` | `5AEA5B1AFC033D4423897323348C0ED8EAC6596EF7B5CE66A6017C259C0CAAE2` | `447b9ef1e45f0caea835256d1e79ec3561008ef2` |
| PD 调度基线 | `vidur-alibabacloud/tests/test_pd_separation.py` | `C1D627DE37E60C309C7D9101F4DE082083B1AC5DF0615EC029BFB1D9B9E203A5` | `5fac51f61060a227494f24e135ae06d55e4ff7cb` |

Windows 工作区的同一文件使用 CRLF 行尾，因此原始 SHA-256 与 Linux LF 检出不同。跨平台确认代码身份时优先比较 Git SHA 与 Git blob；团队统一 Linux 实验则比较上表的 Linux SHA-256。

Linux 复核命令：

```bash
sha256sum \
  example/workload_analytical.txt \
  example/busbw.yaml \
  example/microAllReduce.txt \
  vidur-alibabacloud/tests/test_pd_separation.py
```

## 5. Windows 本机预检环境

本节仅用于说明采集环境，不作为团队统一 Linux 验收结果。

| 项目 | 当前值 |
|---|---|
| 操作系统 | Microsoft Windows 10.0.26200，x86-64 |
| PowerShell | 7.6.5 |
| Git | 2.51.0.windows.2 |
| Python | 3.11.7 |
| CMake | 4.1.2 |
| GCC/G++ | MinGW-w64 15.2.0 |
| Docker 客户端 | 29.6.2 |
| WSL | 初次预检仅有 `docker-desktop`；随后已安装并注册 `Ubuntu-24.04` |
| clang | 未检测到 |
| GNU make | 未检测到 |
| ninja | 已安装；项目安装文档指出 ns-3 构建环境不应安装 ninja |

结论：Windows 工具链不作为正式验收环境；正式结果见下一节。

## 6. Ubuntu WSL 正式验收结果

正式验收使用 Ubuntu 自身 ext4 文件系统中的干净克隆：

```bash
cd /root/SimAI-week1
```

| 检查项 | 实际值 | 结论 |
|---|---|---|
| Linux 发行版 | Ubuntu 24.04.4 LTS | 通过 |
| WSL/Kernel | WSL2，`6.18.33.2-microsoft-standard-WSL2` | 通过 |
| 架构 | x86-64 | 通过 |
| Git | 2.43.0 | 通过 |
| GCC | 13.3.0 | 通过 |
| G++ | 13.3.0 | 通过 |
| C++17 | 最小语法编译检查 `CPP17_OK` | 通过 |
| Python | 3.12.3 | 通过 |
| CMake | 3.28.3 | 通过 |
| GNU Make | 4.3 | 通过 |
| ninja | 未安装 | 通过 |
| 主仓库与远端 | `master...origin/master`，工作区干净 | 通过 |
| 主仓库 SHA | `cf9ed25e41887a633c220ba1661a995ccab6d131` | 通过 |
| 三个子模块 SHA | 与第 3 节一致 | 通过 |
| 四个输入哈希 | 与第 4 节 Linux SHA-256 一致 | 通过 |

工具链安装命令：

```bash
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential cmake
```

验收结论：

- Ubuntu 版本高于项目规定的 20.04+ 下限；
- GCC/G++、Python 与 CMake 均满足最低版本；
- C++17 检查通过；
- 主仓库、子模块和输入文件均已锁定；
- 正式验收克隆无未提交修改；
- 未安装 ninja，满足 ns-3 构建前置要求。

## 7. 统一基线运行结果

补充验收时间：2026-09-07（Asia/Shanghai）。仍使用 `/root/SimAI-week1` 中固定在
`cf9ed25e41887a633c220ba1661a995ccab6d131` 的干净基线代码；构建物、虚拟环境和结果文件
只保留在该验收克隆，不提交到主仓库。

### 7.1 解析后端构建

实际执行：

```bash
cd /root/SimAI-week1
./scripts/build.sh -c analytical
```

结果：退出码 0，`SimAI_analytical` 构建至 100%。GCC 报告了上游代码已有的
`control reaches end of non-void function` 和 string literal 转 `char*` 等警告，但没有编译错误。

### 7.2 主通信基线

实际执行计划规定的完整命令：

```bash
/usr/bin/time -f 'ELAPSED=%e\nMAX_RSS_KB=%M\nEXIT=%x' \
  ./bin/SimAI_analytical \
  -w ./example/workload_analytical.txt \
  -g 9216 -nv 360 -nic 48.5 -n_p_s 8 -g_p_s 8 \
  -r example-
```

| 项目 | 实际值 |
|---|---|
| 退出状态 | `EXIT=0`，日志结尾为 `SimAI-Analytical finished.` |
| Wall-clock | 1.24 s |
| 峰值 RSS | 7,620 KiB |
| 输出 | `/root/SimAI-week1/results/example-EndToEnd.csv` |
| 输出行数 | 1,792 |
| 输出 SHA-256 | `b3d73975f0081c119094852f15b7926b288afb33b337aa19fd46ed6a20acdd69` |
| Summary total time | 7,545,619（沿用输出文件原始时间单位） |
| Total computation | 4,542,795（60.20%） |
| Total exposed communication | 2,656,839（35.21%） |
| Bubble time | 345,984（4.59%） |

结果文件中，无通信或零字节通信行的 `algbw` 会出现 `-nan`。这不影响本次基线正常退出，
但后续数据清洗不得把 `-nan` 当作零或有效带宽；应按通信类型与字节量将其标记为“不适用”。

### 7.3 Vidur PD 测试

系统最初没有 `pytest`，因此安装 Ubuntu 官方 `python3.12-venv`，并在子模块目录创建隔离环境
`.venv-week1`。测试所需的最小额外包为 `pytest` 与 `networkx`。

```bash
cd /root/SimAI-week1/vidur-alibabacloud
python3 -m venv .venv-week1
.venv-week1/bin/python -m pip install pytest networkx
.venv-week1/bin/python -m pytest tests/test_pd_separation.py -q
```

结果：`10 passed in 0.13s`，退出码 0。覆盖 PD 关闭、PD 开启、Prefill/Decode 独立 world size、
阶段参数回退、非法比例拒绝和显式 Prefill 副本数优先级。

## 8. 复核结果归档

| 检查项 | 实际值 | 结论 |
|---|---|---|
| Linux 发行版 | Ubuntu 24.04.4 LTS | 通过 |
| Kernel | 6.18.33.2-microsoft-standard-WSL2 | 通过 |
| GCC/G++ | 13.3.0 / 13.3.0 | 通过 |
| Python | 3.12.3 | 通过 |
| CMake | 3.28.3 | 通过 |
| 主仓库 SHA | `cf9ed25e41887a633c220ba1661a995ccab6d131` | 通过 |
| SimCCL SHA | `fd7cd57d16f9bd42e3ccb70911c977e18ec294b9` | 通过 |
| aicb SHA | `23eec3c48ca2d2d93dd888a4c7b22ab4421e782f` | 通过 |
| ns-3-alibabacloud SHA | `3e0c7c1bfbbe9f77890ddcf5e5b9c79fc6dd7437` | 通过 |
| 输入哈希 | 四项均与第 4 节一致 | 通过 |
| 解析后端构建 | 100%，退出码 0 | 通过 |
| 主通信基线 | 退出码 0；1,792 行结果，SHA-256 已记录 | 通过 |
| Vidur PD 测试 | 10 passed | 通过 |

## 9. 当前结论

统一基线已经闭环：Ubuntu 24.04 WSL 工具链满足项目要求，主仓库、三个子模块和四项固定输入
均已唯一标识；解析后端构建、主通信基线和 Vidur PD 测试均通过。`-nan` 仅出现在无通信/零字节
行，已作为结果解析边界记录。
