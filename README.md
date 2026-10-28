# filesweep

> 把堆成山的下载目录整理干净：一条命令归位，一条命令撤回。

`filesweep` 是一个零依赖的 Python 命令行小工具，用来整理杂乱目录里的文件。它按**扩展名**、**文件类型**或**修改日期**把顶层文件分进子目录，默认先给你看计划，移动之后还会写一份撤销日志——反悔时一键还原。

## 特性

- **三种分组方式**：`ext`（按扩展名）、`type`（图片/文档/音视频……）、`date`（年/月）
- **先预览再动手**：`--dry-run` 只打印计划，不碰任何文件
- **绝不覆盖**：目标重名时自动变成 `report (1).pdf`、`report (2).pdf`
- **可撤销**：每次整理都写 JSON 日志，`filesweep undo` 原路搬回
- **零运行时依赖**，支持 Python 3.9+，Windows / macOS / Linux 通用
- 自带 24 个单元测试和 GitHub Actions CI

## 安装

```bash
git clone https://github.com/Destiny-del666/filesweep.git
cd filesweep
pip install -e .
```

不安装也能直接跑：

```bash
python -m filesweep --help
```

## 快速开始

先看看会怎么分（不会移动文件）：

```console
$ filesweep organize ~/Downloads --by type --dry-run
mode: type
  Archives/  <- 1 file(s)
  Audio/  <- 1 file(s)
  Code/  <- 1 file(s)
  Documents/  <- 2 file(s)
  Images/  <- 2 file(s)
  Other/  <- 1 file(s)
dry run: 8 file(s) would move; nothing changed
```

满意了就去掉 `--dry-run`：

```console
$ filesweep organize ~/Downloads --by type -y
moved 8 file(s), 8.0 KB
undo log: ~/Downloads/.filesweep/undo-20261028-190232-29168.json
revert with: filesweep undo --log "~/Downloads/.filesweep/undo-20261028-190232-29168.json"
```

整理后的目录：

```
Downloads/
├── Archives/    archive.zip
├── Audio/       song.mp3
├── Code/        script.py
├── Documents/   notes.md, report.pdf
├── Images/      photo.jpg, screenshot.png
└── Other/       installer.exe
```

## 三种模式

| 模式 | 命令 | 效果 |
| --- | --- | --- |
| 扩展名 | `filesweep organize . --by ext` | `txt/`、`pdf/`、`jpg/`；没有后缀的进 `_noext/` |
| 类型 | `filesweep organize . --by type` | `Images/`、`Documents/`、`Audio/`、`Video/`、`Archives/`、`Code/`、`Other/` |
| 日期 | `filesweep organize . --by date` | `2024/03/`、`2025/12/`（按文件修改时间） |

## 撤销

```bash
# 撤销最近一次整理（自动在 ./.filesweep 里找最新日志）
filesweep undo -y

# 撤销指定的某一次
filesweep undo --log ./Downloads/.filesweep/undo-20261028-190232-29168.json -y
```

日志可以跨平台复用，里面的路径是绝对路径。如果文件已经被你手动挪走或删掉，`undo` 会跳过它并在结尾列出失败项，而不是报错中断。

## 安全边界

- **只移动，不删除**，也不改文件内容
- **只处理当前这一层的文件**，不会递归进子目录，不会有「把整个项目搬散」的意外
- **跳过符号链接**，避免制造悬空链接
- **跳过已经在目标位置的文件**，重复运行不会产生 `a (1) (1).txt` 这种套娃

## 开发

```bash
python -m unittest discover -s tests -t .   # 跑测试
pip install ruff && ruff check .            # 跑 lint
```

项目结构：

```
src/filesweep/
├── core.py      # 扫描 / 计划 / 执行 / 撤销（纯逻辑，可单独 import）
├── cli.py       # argparse 命令行外壳
└── __main__.py  # python -m filesweep
tests/
├── test_core.py # 计划、冲突、日期、撤销
└── test_cli.py  # 端到端命令行
```

## 许可

[MIT](LICENSE)