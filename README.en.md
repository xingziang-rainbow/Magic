Magic - Local AI Desktop Assistant

A fully offline, locally-run AI agent capable of deeply controlling your computer.

This project is a purely local desktop AI assistant, independent of any specific operating system.

What is this?

Magic is a local AI assistant program built with Python. It doesn't just chat like a normal AI; it uses Tool Calling to directly interact with your system and perform tasks for you.

Key Features:

· 100% Offline: No cloud servers required, ensuring complete privacy.
· System Operations: Open apps, adjust volume, take screenshots, lock screen, etc.
· File Management: Create, read, write, search, and delete files.
· Web Search: Automatically search the internet when needed.
· Command Execution: Execute system commands (dangerous commands require user confirmation).
· Smart Routing: The AI decides whether to call a tool, while the script only provides definitions and executes them.

Architecture

The core philosophy of Magic is: The script doesn't guess user intent; the LLM makes the decision.

User Input
↓
Script sends [Tool Definitions + User Input] to AI
↓
AI decides:
├─ Normal Chat → Direct reply
└─ Needs Action → Outputs JSON Tool Call
↓
Script executes tool → Returns result to AI
↓
AI generates final response → Returns to user

Directory Structure

```text
Magic/
├── core/                     # Main program directory
│   ├── config.yaml           # Configuration file
│   ├── config_loader.py      # Config loader
│   └── loop.py               # Core main loop (Entry point)
├── 模块/                     # Tool modules (Internal/Ext)
├── memory/                   # Memory module (Short & Long term)
└── backends/                 # Model backends (Auto-starts Ollama)
```

---

Detailed Setup Guide (Important)

Before running Magic, you must configure the following environment. Please follow the steps in order:

Step 1: Install Ollama Framework

Magic relies on Ollama to run local LLMs. Install it via terminal:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Step 2: Download the Recommended AI Model

For sufficient reasoning and tool-calling capabilities, we highly recommend the following model:

```bash
ollama pull qwen2.5vl:7b-q4_K_M
```

(Note: If your PC specs are lower, try qwen2.5:3b; if very high, try qwen2.5:14b. Ensure Ollama is running in the background.)

Step 3: Install System Dependencies

Install required system tools (Example for Debian/Ubuntu):

```bash
sudo apt install xclip xdotool wmctrl xbacklight gnome-screenshot -y
```

Step 4: Configure Python Environment

Ensure Python 3.13+ is installed.

```bash
# 1. Clone or download this project and navigate to its directory
# 2. Create a Python virtual environment
python3 -m venv ~/ai_env

# 3. Activate the virtual environment
source ~/ai_env/bin/activate

# 4. Install Python dependencies
pip install pyyaml requests
```

Step 5: Launch Magic

Once configured, simply run:

```bash
cd ~/Magic/core
python3 loop.py
```

---

Usage Examples

Once started, you can give Magic commands in natural language:

Your Input Magic's Action
Hello / Introduce yourself Normal conversation
What time is it Returns system time
Open Firefox Opens the browser
Set volume to 50% Adjusts system volume
Take a screenshot Takes and saves a screenshot
Create file note.txt with content Hello Creates a file
Read note.txt Reads the file content
Search for Python tutorials Searches the web
exit Quits the program

Roadmap

☑ Core Architecture (AI decision + Tool calling)
☑ System/File Operation Modules & Memory
☐ Desktop UI (Tauri)
☐ More extensible tools

Author：XingZiang

License

MIT