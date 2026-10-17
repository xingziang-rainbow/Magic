# Rainbow One

基于 Linux 内核的个人操作系统项目，AI 深度集成。

## 项目定位

- 只兼容 Windows 应用（不兼容 macOS）
- 核心兼容层：NTSync + Wine/Proton
- 包管理：Flatpak 为主，双击安装
- 系统设计：不可变系统（核心只读、原子更新、失败回滚）
- 完全离线运行，不依赖任何服务器
- 零资金投入，非商业项目



## Magic 是什么

Magic 的 AI 助手，能：
- 聊天、回答问题
- 打开应用、调音量、截图、锁屏
- 创建/读取/写入/搜索/删除文件
- 执行系统命令（危险命令需确认）
- 联网搜索

核心架构：**AI 自己判断要不要调用工具，脚本只负责给工具定义、执行工具、把结果返回 AI。**

## 当前进度

- ✅ Magic 核心架构（AI 判断 + 工具调用）
- ✅ 系统操作模块
- ✅ 文件操作模块
- ✅ 记忆模块（短期 + 长期）
- ✅ 模型后端（自动启动 Ollama）
- ⏳ UI（Tauri，未开始）
- ⏳ 兼容层（NTSync + Wine/Proton，未开始）

## 目录结构

```
rainbow/
├── magic/                    # AI Agent（Python）
│   ├── core/                 # 主循环、配置
│   │   ├── config.yaml
│   │   ├── config_loader.py
│   │   └── loop.py
│   ├── 模块/                 # 工具模块
│   │   ├── 内部/             # 系统、文件等内置
│   │   └── 扩展/             # 可添加的模块
│   ├── memory/               # 记忆
│   └── backends/             # 模型后端
├── ui/                       # Tauri 界面（待开发）
├── apps/                     # 自研应用（待开发）
├── assets/                   # 图标、壁纸
├── docs/                     # 文档
└── scripts/                  # 构建脚本
```

## 环境要求

- Debian 13（或其他 Linux 发行版）
- Python 3.13+
- Ollama
- 模型：`qwen2.5vl:7b-q4_K_M`（或兼容的其他模型）

## 安装

### 1. 安装 Ollama 和模型

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5vl:7b-q4_K_M
```

### 2. 装系统依赖

```bash
sudo apt install xclip xdotool wmctrl xbacklight gnome-screenshot -y
```

### 3. 创建 Python 虚拟环境

```bash
python3 -m venv ~/ai_env
source ~/ai_env/bin/activate
pip install pyyaml requests
```

## 使用

```bash
cd ~/rainbow/magic/core
python3 loop.py
```

### 支持的操作示例

| 输入 | 效果 |
| --- | --- |
| `你好` | 普通对话 |
| `现在几点` | 返回时间 |
| `帮我打开 Firefox` | 打开浏览器 |
| `音量调到 50%` | 调音量 |
| `截图` | 截图保存 |
| `创建文件 note.txt 内容 你好世界` | 创建文件 |
| `读一下 note.txt` | 读取文件内容 |
| `搜索 Python 教程` | 浏览器搜索 |
| `介绍一下你自己` | 普通对话 |
| `exit` | 退出 |

## 架构设计

```
用户输入
  ↓
脚本把 [工具定义 + 用户输入] 发给 AI
  ↓
AI 自己判断：
  ├─ 普通对话 → 直接回答
  └─ 需要操作 → 输出 JSON 工具调用
  ↓
脚本执行工具 → 结果返回 AI
  ↓
AI 组织最终回复 → 返回给用户
```

**关键点：脚本不猜用户想干什么，AI 自己判断。**

## 许可证

MIT
