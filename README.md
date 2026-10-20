# Magic - 本地 AI 桌面智能体 V0.2

一个完全离线运行、可深度操控你电脑的 AI 智能体（Agent）。支持文件管理、系统操作与工具调用，保护隐私，无需联网。

## 项目简介

Magic 是一个基于 Python 开发的本地 AI 桌面助手程序。与普通的聊天机器人不同，它不仅能像人类一样理解自然语言，还能通过工具调用（Tool Calling）机制，直接接管你的系统，帮你完成各种复杂的操作。

它是 Rainbow 操作系统生态的核心组件，但本身具有极高的独立性，可以作为独立的桌面 AI 助手，运行在任何主流的 Linux 发行版上。我们的核心理念是：让 AI 成为系统的原生大脑，而不是一个外挂的聊天窗口。

## 核心特性

- **完全离线运行**：基于本地部署的大语言模型（通过 Ollama 调度，如 Qwen2.5-VL 等），不依赖任何云端服务器，你的所有对话和操作指令都不会离开你的电脑，彻底保护隐私。
- **强大的系统操作能力**：可以通过自然语言指令，直接打开应用、调节系统音量、获取当前时间、进行屏幕截图、锁定屏幕等。
- **全栈文件管理**：支持通过对话创建、读取、写入、搜索、删除、复制、移动文件和目录，甚至可以自动创建多级文件夹。
- **内置安全确认机制**：为了保证系统安全，当 AI 尝试执行高危命令（如 rm、mkfs、shutdown 等）时，程序会暂停执行，并在终端请求用户的二次确认，只有输入 y 才会真正执行。
- **智能路由与自主决策**：脚本不写死任何硬编码规则，所有的意图识别全部交由 AI 模型自行判断。它会自己决定是进行普通对话，还是输出 JSON 来调用系统工具。
- **高度可扩展的模块化设计**：底层架构采用模块化拆分，系统工具、文件工具相互独立。未来不仅开发者可以轻松添加新工具，甚至可以让 AI 自己编写插件并动态加载。

## 工作原理

传统的语音助手或对话脚本，通常使用大量正则表达式去猜测用户的意图，这种做法非常脆弱，稍微换个说法就会失效。

Magic 的核心设计理念是：脚本不猜用户想干什么，判断权完全交还给模型。

工作流程如下：

1. 用户输入文字（例如："帮我打开火狐浏览器"）
2. 脚本将"工具说明书"连同用户的输入，一起发送给本地的大模型
3. 模型经过思考后，判断这是一个操作请求，于是输出一段包含具体参数的 JSON（例如：`{"tool": "open_app", "name": "firefox"}`）
4. 脚本接收到 JSON 后，调用底层的 system.py 模块，执行真正的系统命令
5. 工具执行成功后，脚本把结果返回给模型，模型再用一句自然、友好的话回复用户（例如："好的，Firefox 已经为你打开了"）

## 目录结构

```
magic/
├── core/                    # 核心主程序目录
│   ├── loop.py              # 核心主循环入口，负责与模型通信和调度工具
│   ├── config.yaml          # 全局配置文件
│   └── config_loader.py     # 配置加载器
├── backends/                # 大模型后端适配层
│   ├── base.py              # 后端基类定义
│   └── ollama_backend.py    # Ollama 接口封装
├── memory/                  # 记忆系统目录
│   ├── short_term.py        # 短期记忆管理（保留最近的对话上下文）
│   └── long_term.py         # 长期记忆管理（基于 SQLite）
└── 模块/                    # 存放所有工具模块的目录
    ├── 内部/                # 系统内置的核心工具
    │   ├── system.py        # 系统级别操作（应用、音量、截图等）
    │   ├── file.py          # 文件系统的增删改查
    │   └── registry.py      # 工具注册表
    └── 扩展/                # 预留给未来 AI 自己编写或用户自定义的扩展工具
```

## 快速开始

### 环境要求

- Linux 操作系统（推荐 Debian 或 Ubuntu）
- Python 3.10 及以上版本
- 已安装 Ollama 并下载了模型（推荐 qwen2.5vl:7b-q4_K_M）

### 安装步骤

1. **安装系统底层的辅助工具**：
   ```bash
   sudo apt install xclip xdotool wmctrl xbacklight gnome-screenshot -y
   ```

2. **创建并激活 Python 虚拟环境**：
   ```bash
   python3 -m venv ai_env
   source ai_env/bin/activate
   ```

3. **安装 Python 依赖包**：
   ```bash
   pip install pyyaml requests
   ```

### 运行方式

```bash
cd magic/core
python3 loop.py
```

## 对话示例

| 示例 | 说明 |
|------|------|
| "你好，你是谁？" | 普通对话，Magic 会直接回答你的问题 |
| "现在几点了？" | 调用 get_time 工具，返回当前精确时间 |
| "帮我打开 Firefox" | 调用 open_app 工具，启动浏览器 |
| "音量调到 30%" | 调用 volume 工具，调节系统声音 |
| "创建文件 note.txt 内容 你好世界" | 调用 create_file 工具，在你的文档目录下生成文件 |
| "执行 ls -la" | 调用 run_command 工具，列出当前目录内容 |

## 下载与安装

| 平台 | 下载链接 | 说明 |
| :--- | :--- | :--- |
| **Gitee (国内推荐)** | [点击下载源码压缩包](https://gitee.com/xingziang-rainbow/Magic/repository/archive/master.zip) | 国内访问极快 |
| **GitHub** | [点击下载源码压缩包](https://github.com/xingziang-rainbow/Magic/archive/refs/heads/master.zip) | 需科学上网 |
| **历史版本** | [前往 Releases 页面](https://gitee.com/xingziang-rainbow/Magic/releases) | 查看所有版本 |

## 开源协议

本项目采用 MIT License，欢迎自由使用、修改和分发。

**制作者**：XingZiang