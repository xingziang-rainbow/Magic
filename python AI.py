#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphos AI 桌面助手
====================
三层处理结构：
  第一层：内置命令（0.01 秒）
  第二层：直接操作（0.1~2 秒，不走模型）
  第三层：屏幕操作循环（30~60 秒，截图→推理→执行）
  第四层：兜底对话（5~10 秒，走模型）

模型: qwen2.5vl:7b-q4_K_M
环境: Debian 13 + XFCE, Python 3.13, ~/ai_env

依赖:
    pip install ollama pyautogui pillow mss psutil
    sudo apt install xdotool xclip wmctrl xbacklight -y

用法:
    source ~/ai_env/bin/activate
    python3 ai_agent.py
"""

import os
import sys
import re
import json
import time
import base64
import sqlite3
import hashlib
import random
import threading
import subprocess
import traceback
import shlex
import urllib.parse
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

import ollama
import pyautogui
from PIL import Image

# 安全设置
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

# 尝试导入 mss
try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False
    print("⚠️  mss 未安装，使用 pyautogui 截图。建议: pip install mss")

# 尝试导入 psutil
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("⚠️  psutil 未安装，系统信息功能不可用。建议: pip install psutil")


# ==================== 配置 ====================

@dataclass
class Config:
    """全局配置"""
    
    # --- 模型 ---
    MODEL_NAME: str = "qwen2.5vl:7b-q4_K_M"
    TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 1024
    KEEP_ALIVE: str = "30m"
    
    # --- 屏幕操作循环 ---
    MAX_STEPS: int = 5
    STEP_DELAY: float = 0.5
    SCREENSHOT_SCALE: float = 0.4
    SCREENSHOT_QUALITY: int = 75
    REPEAT_LIMIT: int = 2
    
    # --- 截图 ---
    SCREENSHOT_METHOD: str = "mss"
    SCREENSHOT_COOLDOWN: float = 1.0
    
    # --- 记忆 ---
    MAX_SHORT_TERM: int = 10
    LONG_TERM_COUNT: int = 5
    DB_PATH: str = os.path.expanduser("~/.delphos_memory.db")
    
    # --- 调试 ---
    DEBUG: bool = False
    SAVE_SCREENSHOT: bool = False


# ==================== 系统提示词 ====================

SCREEN_AGENT_PROMPT = """你是 Delphos 桌面助手，能直接操作电脑。

【能力】
- 看截图识别按钮、输入框、图标、文字
- 模拟鼠标点击、键盘输入
- 打开应用、执行命令、搜索网页

【操作格式 - 只输出一行 JSON】
{"action":"click","x":100,"y":200}
{"action":"type","text":"要输入的内容"}
{"action":"key","key":"enter"}
{"action":"hotkey","keys":["ctrl","c"]}
{"action":"open_app","name":"firefox"}
{"action":"run_command","command":"ls"}
{"action":"search","query":"Python教程"}
{"action":"done"}

【规则】
1. 先看截图，再决定操作
2. 一次只输出一个 JSON，不要输出别的
3. 日常对话直接回答，不要输出 JSON
4. 不确定时先问用户"""

CHAT_PROMPT = """你是 Delphos 桌面助手，运行在 Debian Linux + XFCE 桌面。

【回复要求】
- 简洁直接，用中文
- 不输出 JSON 操作（除非用户要求操作屏幕）
- 诚实：不确定的事情直接说明"""


# ==================== 内置命令（第一层） ====================

GREETINGS = {
    "你好": "你好！我是 Delphos 助手，有什么可以帮你的？\n\n💡 提示：\n  - 直接说「打开 Firefox」我可以操作屏幕\n  - 输入 help 查看更多命令",
    "嗨": "嗨！有什么需要帮忙的吗？",
    "hi": "Hi! I'm Delphos Assistant. How can I help you?",
    "hello": "Hello! I'm Delphos Assistant. How can I help you?",
    "在吗": "在的！有什么需要帮忙的？",
    "你好吗": "我很好，谢谢关心！有什么可以帮你的？",
    "在不在": "在！随时待命。",
}

JOKES = [
    "为什么程序员总是搞混万圣节和圣诞节？因为 Oct 31 == Dec 25！",
    "一个 SQL 语句走进酒吧，看见两张桌子，问：我能 JOIN 你们吗？",
    "程序员最讨厌的两种状态：一是没网，二是有网但很慢。",
    "bug 的定义：当你自信地说「这不可能出错」时，它就出错了。",
    "Linux 用户的问题：90% 的时间在配置，10% 的时间在炫耀配置。",
    "为什么 Python 程序员不用蛇皮袋？因为她们有 pip！",
    "回车键坏了的程序员：我的代码没有 bug，只是需要深呼吸。",
]

# 应用映射表
APP_MAP = {
    "firefox": "firefox", "火狐": "firefox", "火狐浏览器": "firefox",
    "浏览器": "firefox", "browser": "firefox",
    "chromium": "chromium", "chrome": "chromium", "谷歌浏览器": "chromium",
    "google chrome": "chromium", "谷歌": "chromium",
    "终端": "xfce4-terminal", "命令行": "xfce4-terminal",
    "terminal": "xfce4-terminal", "shell": "xfce4-terminal",
    "bash": "xfce4-terminal", "终端模拟器": "xterm",
    "文件管理器": "thunar", "文件夹": "thunar", "文件": "thunar",
    "files": "thunar", "资源管理器": "thunar",
    "vscode": "code", "vs code": "code", "代码编辑器": "code",
    "visual studio code": "code", "编辑器": "code",
    "libreoffice": "libreoffice", "office": "libreoffice",
    "办公套件": "libreoffice", "办公": "libreoffice",
    "vlc": "vlc", "视频播放器": "vlc", "媒体播放器": "vlc",
    "播放器": "vlc", "视频": "vlc",
    "计算器": "galculator", "calculator": "galculator",
    "系统监视器": "xfce4-taskmanager", "任务管理器": "xfce4-taskmanager",
    "task manager": "xfce4-taskmanager", "监视器": "xfce4-taskmanager",
    "设置": "xfce4-settings-manager", "系统设置": "xfce4-settings-manager",
    "settings": "xfce4-settings-manager", "偏好设置": "xfce4-settings-manager",
    "文本编辑器": "gedit", "记事本": "gedit", "gedit": "gedit",
    "笔记": "gedit", "文本": "gedit",
    "图片查看器": "eog", "看图": "eog", "图片": "eog",
    "image viewer": "eog", "eog": "eog",
    "音乐播放器": "rhythmbox", "音乐": "rhythmbox",
    "rhythmbox": "rhythmbox", "音频": "rhythmbox",
    "截图工具": "xfce4-screenshooter", "截屏": "xfce4-screenshooter",
    "归档管理器": "file-roller", "压缩": "file-roller",
    "解压": "file-roller", "压缩包": "file-roller",
    "pdf 阅读器": "evince", "pdf": "evince", "evince": "evince",
    "邮件": "thunderbird", "邮箱": "thunderbird",
    "thunderbird": "thunderbird", "雷鸟": "thunderbird",
}

# 命令白名单
CMD_WHITELIST = [
    "ls", "cat", "head", "tail", "grep", "find", "which", "whereis",
    "echo", "date", "cal", "df", "du", "free", "ps", "uname",
    "hostname", "ip", "ping", "whoami", "pwd", "id", "uptime", "w",
    "systemctl status", "journalctl", "git status", "git log",
]

# 危险命令黑名单
CMD_BLACKLIST = [
    "rm -rf", "rm -r", "mkfs", "dd if=", "shutdown", "reboot",
    "poweroff", "halt", "init 0", "init 6", "> /dev/sda",
    ":(){ :|:& };:", "chmod 777 /", "chown", "sudo", "su",
]


# ==================== 数据库 ====================

class MemoryDB:
    """SQLite 持久化记忆数据库"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS short_term (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    has_image BOOLEAN DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_info TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    importance REAL DEFAULT 0.5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_access DATETIME DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_st_time ON short_term(timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lt_category ON long_term(category)")
            conn.commit()
    
    def add_message(self, role: str, content: str, has_image: bool = False):
        if role == "user":
            cleaned = content.strip().lower()
            if len(cleaned) <= 2:
                return
            simple_greetings = ["你好", "hi", "hello", "在吗", "早", "晚安", "88", "拜拜", "谢谢", "ok", "嗯", "哦", "嗨"]
            if cleaned in simple_greetings:
                return
        
        if role == "assistant" and len(content.strip()) <= 2:
            return
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO short_term (role, content, has_image) VALUES (?, ?, ?)",
                (role, content, has_image)
            )
            conn.commit()
    
    def get_recent(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT role, content, has_image, timestamp FROM short_term ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(row) for row in reversed(rows)]
    
    def clear_short_term(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM short_term")
            conn.commit()
    
    def add_long_term(self, key_info: str, category: str = "general", importance: float = 0.5):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO long_term (key_info, category, importance) VALUES (?, ?, ?)",
                (key_info, category, importance)
            )
            conn.commit()
    
    def search_long_term(self, query: str, limit: int = 5) -> List[Dict]:
        keywords = query.lower().split()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conditions = " OR ".join(["key_info LIKE ?" for _ in keywords])
            params = [f"%{kw}%" for kw in keywords]
            rows = conn.execute(f"""
                SELECT *, (access_count * 0.1 + importance * 0.9) as score
                FROM long_term WHERE {conditions}
                ORDER BY score DESC LIMIT ?
            """, params + [limit]).fetchall()
            return [dict(row) for row in rows]


# ==================== 截图管理 ====================

class ScreenshotManager:
    """截图管理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.last_time: float = 0
        self._lock = threading.Lock()
    
    def capture(self) -> Optional[Tuple[bytes, Tuple[int, int]]]:
        """截图并返回 JPEG bytes + 尺寸"""
        with self._lock:
            now = time.time()
            if now - self.last_time < self.config.SCREENSHOT_COOLDOWN:
                time.sleep(self.config.SCREENSHOT_COOLDOWN - (now - self.last_time))
            self.last_time = time.time()
        
        try:
            if self.config.SCREENSHOT_METHOD == "mss" and HAS_MSS:
                with mss.MSS() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            else:
                img = pyautogui.screenshot()
            
            orig_size = img.size
            new_size = (
                int(orig_size[0] * self.config.SCREENSHOT_SCALE),
                int(orig_size[1] * self.config.SCREENSHOT_SCALE)
            )
            img = img.resize(new_size, Image.LANCZOS)
            
            buffer = BytesIO()
            img.convert("RGB").save(buffer, format="JPEG", quality=self.config.SCREENSHOT_QUALITY)
            image_bytes = buffer.getvalue()
            
            if self.config.DEBUG:
                print(f"📸 截图: {new_size[0]}x{new_size[1]}, {len(image_bytes)/1024:.0f}KB")
            
            return image_bytes, new_size
            
        except Exception as e:
            print(f"❌ 截图失败: {e}")
            return None
    
    def save_screenshot(self) -> Optional[str]:
        """保存截图到文件"""
        try:
            if self.config.SCREENSHOT_METHOD == "mss" and HAS_MSS:
                with mss.MSS() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            else:
                img = pyautogui.screenshot()
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.expanduser(f"~/截图_{timestamp}.png")
            img.save(path)
            return path
        except Exception as e:
            print(f"❌ 保存截图失败: {e}")
            return None


# ==================== 操作执行器 ====================

class ActionExecutor:
    """执行屏幕操作"""
    
    def __init__(self, config: Config):
        self.config = config
    
    def execute(self, action: Dict) -> Tuple[bool, str]:
        action_type = action.get("action", "")
        
        try:
            if action_type == "click":
                return self._click(action)
            elif action_type == "double_click":
                return self._double_click(action)
            elif action_type == "right_click":
                return self._right_click(action)
            elif action_type == "type":
                return self._type_text(action)
            elif action_type == "key":
                return self._press_key(action)
            elif action_type == "hotkey":
                return self._hotkey(action)
            elif action_type == "open_app":
                return self._open_app(action)
            elif action_type == "run_command":
                return self._run_command(action)
            elif action_type == "search":
                return self._search(action)
            elif action_type == "screenshot":
                return True, "已截图"
            elif action_type == "done":
                return True, "任务完成"
            else:
                return False, f"未知操作: {action_type}"
        except Exception as e:
            return False, f"执行失败: {e}"
    
    def _click(self, action: Dict) -> Tuple[bool, str]:
        x, y = action.get("x", 0), action.get("y", 0)
        pyautogui.click(x, y)
        return True, f"点击 ({x}, {y})"
    
    def _double_click(self, action: Dict) -> Tuple[bool, str]:
        x, y = action.get("x", 0), action.get("y", 0)
        pyautogui.doubleClick(x, y)
        return True, f"双击 ({x}, {y})"
    
    def _right_click(self, action: Dict) -> Tuple[bool, str]:
        x, y = action.get("x", 0), action.get("y", 0)
        pyautogui.rightClick(x, y)
        return True, f"右键 ({x}, {y})"
    
    def _type_text(self, action: Dict) -> Tuple[bool, str]:
        text = action.get("text", "")
        if not text:
            return False, "文本为空"
        
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode('utf-8'),
                capture_output=True,
                timeout=5
            )
            pyautogui.hotkey('ctrl', 'v')
            return True, f"输入文本 ({len(text)}字)"
        except FileNotFoundError:
            try:
                pyautogui.write(text, interval=0.05)
                return True, f"输入文本 ({len(text)}字)"
            except:
                return False, "输入失败（请安装 xclip: sudo apt install xclip）"
        except Exception as e:
            return False, f"输入失败: {e}"
    
    def _press_key(self, action: Dict) -> Tuple[bool, str]:
        key = action.get("key", "").lower()
        key_map = {
            "enter": "enter", "return": "enter", "回车": "enter",
            "esc": "escape", "escape": "escape",
            "tab": "tab", "space": "space", "空格": "space",
            "backspace": "backspace", "退格": "backspace",
            "delete": "delete", "del": "delete",
            "up": "up", "down": "down", "left": "left", "right": "right",
            "上": "up", "下": "down", "左": "left", "右": "right",
        }
        mapped = key_map.get(key, key)
        pyautogui.press(mapped)
        return True, f"按键 {mapped}"
    
    def _hotkey(self, action: Dict) -> Tuple[bool, str]:
        keys = action.get("keys", [])
        if not keys:
            return False, "按键为空"
        pyautogui.hotkey(*keys)
        return True, f"组合键 {'+'.join(keys)}"
    
    def _open_app(self, action: Dict) -> Tuple[bool, str]:
        name = action.get("name", "").strip().lower()
        if not name:
            return False, "应用名为空"
        
        cmd = None
        for alias, real_cmd in APP_MAP.items():
            if alias in name or name in alias:
                cmd = real_cmd
                break
        
        if not cmd:
            cmd = name
        
        try:
            subprocess.Popen(
                [cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return True, f"启动 {cmd}"
        except FileNotFoundError:
            return False, f"未找到应用: {cmd}"
        except Exception as e:
            return False, f"启动失败: {e}"
    
    def _run_command(self, action: Dict) -> Tuple[bool, str]:
        command = action.get("command", "").strip()
        if not command:
            return False, "命令为空"
        
        cmd_lower = command.lower()
        for dangerous in CMD_BLACKLIST:
            if dangerous in cmd_lower:
                return False, f"⚠️ 危险命令已拦截"
        
        allowed = False
        for allowed_cmd in CMD_WHITELIST:
            if cmd_lower.startswith(allowed_cmd):
                allowed = True
                break
        
        if not allowed:
            return False, f"⚠️ 命令不在白名单中: {command.split()[0]}"
        
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True,
                timeout=10
            )
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                if len(output) > 2000:
                    output = output[:2000] + "\n... (已截断)"
                return True, output
            else:
                return True, "命令执行完成（无输出）"
        except subprocess.TimeoutExpired:
            return False, "命令超时"
        except Exception as e:
            return False, f"执行失败: {e}"
    
    def _search(self, action: Dict) -> Tuple[bool, str]:
        query = action.get("query", "").strip()
        if not query:
            return False, "搜索词为空"
        
        encoded = urllib.parse.quote(query)
        url = f"https://www.bing.com/search?q={encoded}"
        
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return True, f"搜索: {query}"
        except Exception as e:
            return False, f"搜索失败: {e}"


# ==================== 第二层：直接操作（不走模型） ====================

class DirectActionHandler:
    """直接操作处理器 - 通过系统命令完成，不截图不走模型
    
    覆盖：打开应用、音量、亮度、WiFi、截图、锁屏、关机、
          文件操作、剪贴板、通知、搜索、命令执行、窗口控制
    """
    
    def __init__(self, config: Config, screenshot_mgr: ScreenshotManager):
        self.config = config
        self.screenshot_mgr = screenshot_mgr
    
    def try_handle(self, text: str) -> Optional[str]:
        """尝试处理输入，成功返回结果字符串，失败返回 None"""
        text_stripped = text.strip()
        text_lower = text_stripped.lower()
        
        # 按优先级逐一尝试
        handlers = [
            self._handle_open_app,
            self._handle_search,
            self._handle_volume,
            self._handle_brightness,
            self._handle_wifi,
            self._handle_system_control,
            self._handle_file_operation,
            self._handle_clipboard,
            self._handle_notification,
            self._handle_run_command,
            self._handle_window_control,
        ]
        
        for handler in handlers:
            result = handler(text_stripped, text_lower)
            if result is not None:
                return result
        
        return None
    
    # ---- 打开应用 ----
    
    def _handle_open_app(self, text: str, text_lower: str) -> Optional[str]:
        # 匹配：打开/启动/运行/开启 + 应用名
        patterns = [
            r'(?:打开|启动|运行|开启|open|launch|run)\s+(.+)',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                app_name = match.group(1).strip().lower()
                return self._launch_app(app_name)
        
        return None
    
    def _launch_app(self, name: str) -> Optional[str]:
        """根据名称启动应用"""
        # 模糊匹配应用映射表
        cmd = None
        for alias, real_cmd in APP_MAP.items():
            if alias in name or name in alias:
                cmd = real_cmd
                break
        
        if not cmd:
            return None  # 没匹配到，不处理
        
        try:
            subprocess.Popen(
                [cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return f"✅ 已启动 {cmd}"
        except FileNotFoundError:
            return f"⚠️ 未找到应用: {cmd}，请确认已安装"
        except Exception as e:
            return f"❌ 启动失败: {e}"
    
    # ---- 搜索 ----
    
    def _handle_search(self, text: str, text_lower: str) -> Optional[str]:
        # Bing 搜索
        bing_patterns = [
            r'(?:搜索|搜|查一下|帮我搜)\s+(.+)',
        ]
        for pattern in bing_patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                if not self._is_screen_action_query(query):
                    return self._open_search(query, "bing")
        
        # 百度搜索
        if re.search(r'百度', text):
            for suffix in ['百度', '百度一下', '百度搜索', '百度搜']:
                if text_lower.startswith(suffix.lower()):
                    query = text[len(suffix):].strip()
                    if query:
                        return self._open_search(query, "baidu")
        
        # 谷歌搜索
        if re.search(r'(?:谷歌|google)', text_lower):
            for suffix in ['谷歌', 'google', '谷歌搜索', 'google search']:
                if text_lower.startswith(suffix.lower()):
                    query = text[len(suffix):].strip()
                    if query:
                        return self._open_search(query, "google")
        
        return None
    
    def _is_screen_action_query(self, query: str) -> bool:
        """如果搜索词涉及屏幕操作，不走搜索"""
        screen_words = ["屏幕", "当前", "显示", "桌面上", "界面"]
        return any(w in query for w in screen_words)
    
    def _open_search(self, query: str, engine: str = "bing") -> str:
        encoded = urllib.parse.quote(query)
        urls = {
            "bing": f"https://www.bing.com/search?q={encoded}",
            "baidu": f"https://www.baidu.com/s?wd={encoded}",
            "google": f"https://www.google.com/search?q={encoded}",
        }
        url = urls.get(engine, urls["bing"])
        
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            engine_names = {"bing": "必应", "baidu": "百度", "google": "Google"}
            return f"✅ 已在{engine_names.get(engine, engine)}中搜索: {query}"
        except Exception as e:
            return f"❌ 搜索失败: {e}"
    
    # ---- 音量控制 ----
    
    def _handle_volume(self, text: str, text_lower: str) -> Optional[str]:
        # 音量调到 XX%
        match = re.search(r'音量(?:调到|设为|设置到?|调整到?)\s*(\d+)%?', text)
        if match:
            vol = match.group(1)
            return self._run_pactl(f"set-sink-volume @DEFAULT_SINK@ {vol}%", f"音量已设为 {vol}%")
        
        # 最大音量
        if re.search(r'最大音量|音量最大', text):
            return self._run_pactl("set-sink-volume @DEFAULT_SINK@ 100%", "音量已调至最大")
        
        # 音量加
        if re.search(r'音量加|大声点|调大音量|增加音量|音量增大|声音大点', text):
            return self._run_pactl("set-sink-volume @DEFAULT_SINK@ +10%", "音量已增加 10%")
        
        # 音量减
        if re.search(r'音量减|小声点|调小音量|减少音量|音量减小|声音小点', text):
            return self._run_pactl("set-sink-volume @DEFAULT_SINK@ -10%", "音量已减少 10%")
        
        # 静音切换
        if re.search(r'静音|关闭声音|关声音|消音', text):
            return self._run_pactl("set-sink-mute @DEFAULT_SINK@ toggle", "已切换静音状态")
        
        # 取消静音
        if re.search(r'取消静音|开启声音|开声音|解除静音', text):
            return self._run_pactl("set-sink-mute @DEFAULT_SINK@ 0", "已取消静音")
        
        # 查询音量
        if re.search(r'静音了吗|音量多少|当前音量|音量状态', text):
            try:
                result = subprocess.run(
                    ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                    capture_output=True, text=True, timeout=5
                )
                mute_result = subprocess.run(
                    ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                    capture_output=True, text=True, timeout=5
                )
                vol_info = result.stdout.strip()
                mute_info = mute_result.stdout.strip()
                return f"🔊 {vol_info}\n   {mute_info}"
            except:
                return None
        
        return None
    
    def _run_pactl(self, args: str, success_msg: str) -> str:
        try:
            subprocess.run(
                ["pactl"] + args.split(),
                capture_output=True, timeout=5
            )
            return f"✅ {success_msg}"
        except FileNotFoundError:
            return "⚠️ pactl 未安装，无法控制音量"
        except Exception as e:
            return f"❌ 音量控制失败: {e}"
    
    # ---- 屏幕亮度 ----
    
    def _handle_brightness(self, text: str, text_lower: str) -> Optional[str]:
        # 亮度调到 XX%
        match = re.search(r'亮度(?:调到|设为|设置到?|调整到?)\s*(\d+)%?', text)
        if match:
            val = match.group(1)
            try:
                subprocess.run(["xbacklight", "-set", val], capture_output=True, timeout=5)
                return f"✅ 亮度已设为 {val}%"
            except FileNotFoundError:
                return "⚠️ xbacklight 未安装，请运行: sudo apt install xbacklight"
            except Exception as e:
                return f"❌ 亮度调节失败: {e}"
        
        # 亮度加
        if re.search(r'亮度加|亮一点|调亮|增加亮度', text):
            try:
                subprocess.run(["xbacklight", "+10"], capture_output=True, timeout=5)
                return "✅ 亮度已增加 10%"
            except FileNotFoundError:
                return "⚠️ xbacklight 未安装"
            except Exception as e:
                return f"❌ 亮度调节失败: {e}"
        
        # 亮度减
        if re.search(r'亮度减|暗一点|调暗|减少亮度', text):
            try:
                subprocess.run(["xbacklight", "-10"], capture_output=True, timeout=5)
                return "✅ 亮度已减少 10%"
            except FileNotFoundError:
                return "⚠️ xbacklight 未安装"
            except Exception as e:
                return f"❌ 亮度调节失败: {e}"
        
        return None
    
    # ---- 网络控制 ----
    
    def _handle_wifi(self, text: str, text_lower: str) -> Optional[str]:
        # 连接 WiFi
        match = re.search(r'(?:连接|连上|连接上)\s*(?:wifi|WiFi|无线)?\s*(.+)', text)
        if match:
            ssid = match.group(1).strip()
            try:
                subprocess.run(
                    ["nmcli", "device", "wifi", "connect", ssid],
                    capture_output=True, text=True, timeout=15
                )
                return f"✅ 正在连接 WiFi: {ssid}"
            except FileNotFoundError:
                return "⚠️ nmcli 不可用"
            except Exception as e:
                return f"❌ 连接失败: {e}"
        
        # 断开 WiFi
        if re.search(r'断开\s*(?:wifi|WiFi|无线)|关闭\s*(?:wifi|WiFi|无线)', text):
            try:
                subprocess.run(["nmcli", "radio", "wifi", "off"], capture_output=True, timeout=10)
                return "✅ WiFi 已关闭"
            except FileNotFoundError:
                return "⚠️ nmcli 不可用"
            except Exception as e:
                return f"❌ 操作失败: {e}"
        
        # 开启 WiFi
        if re.search(r'打开\s*(?:wifi|WiFi|无线)|开启\s*(?:wifi|WiFi|无线)', text):
            try:
                subprocess.run(["nmcli", "radio", "wifi", "on"], capture_output=True, timeout=10)
                return "✅ WiFi 已开启"
            except FileNotFoundError:
                return "⚠️ nmcli 不可用"
            except Exception as e:
                return f"❌ 操作失败: {e}"
        
        # WiFi 列表
        if re.search(r'(?:查看|显示|列出)\s*(?:wifi|WiFi|无线)|wifi\s*(?:列表|list)', text_lower):
            try:
                result = subprocess.run(
                    ["nmcli", "device", "wifi", "list"],
                    capture_output=True, text=True, timeout=10
                )
                output = result.stdout.strip()
                if output:
                    return f"📡 WiFi 列表:\n{output[:1500]}"
                return "📡 未扫描到 WiFi 网络"
            except:
                return "⚠️ nmcli 不可用"
        
        # 网络状态
        if re.search(r'网络状态|网络连接', text):
            try:
                result = subprocess.run(
                    ["nmcli", "general", "status"],
                    capture_output=True, text=True, timeout=5
                )
                return f"🌐 网络状态:\n{result.stdout.strip()}"
            except:
                return "⚠️ nmcli 不可用"
        
        return None
    
    # ---- 系统控制 ----
    
    def _handle_system_control(self, text: str, text_lower: str) -> Optional[str]:
        # 截图
        if text_lower in ["截图", "截屏", "screenshot", "屏幕截图"]:
            path = self.screenshot_mgr.save_screenshot()
            if path:
                return f"✅ 截图已保存: {path}"
            return "❌ 截图失败"
        
        # 锁屏
        if re.search(r'锁屏|锁定屏幕|锁屏幕|lock', text_lower):
            try:
                subprocess.Popen(
                    ["xdg-screensaver", "lock"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                return "✅ 屏幕已锁定"
            except:
                # 备选方案
                try:
                    subprocess.Popen(
                        ["dm-tool", "lock"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    return "✅ 屏幕已锁定"
                except:
                    return "⚠️ 无法锁定屏幕"
        
        # 关机（需确认）
        if re.search(r'关机|关闭电脑|shutdown|poweroff', text_lower):
            # 检查是否已经确认
            return self._confirm_dangerous_action(
                "关机", ["systemctl", "poweroff"],
                "确认关机？(y/N): "
            )
        
        # 重启（需确认）
        if re.search(r'重启|重新启动|reboot|restart', text_lower):
            return self._confirm_dangerous_action(
                "重启", ["systemctl", "reboot"],
                "确认重启？(y/N): "
            )
        
        # 注销
        if re.search(r'注销|登出|logout|sign out', text_lower):
            return self._confirm_dangerous_action(
                "注销", ["xfce4-session-logout"],
                "确认注销？(y/N): "
            )
        
        # 休眠
        if re.search(r'休眠|睡眠|suspend|sleep', text_lower):
            try:
                subprocess.run(["systemctl", "suspend"], capture_output=True, timeout=5)
                return "✅ 系统进入休眠"
            except:
                return "⚠️ 休眠失败"
        
        return None
    
    def _confirm_dangerous_action(self, name: str, cmd: List[str], prompt: str) -> str:
        """需要用户确认的危险操作 - 返回提示信息，让用户在下一轮确认"""
        # 存储待确认的操作
        self._pending_action = (name, cmd)
        return f"⚠️ 确认{name}？请输入 y 确认，或输入 n 取消。"
    
    def check_pending_confirmation(self, text: str) -> Optional[str]:
        """检查用户是否确认之前的危险操作"""
        if not hasattr(self, '_pending_action') or self._pending_action is None:
            return None
        
        text_lower = text.strip().lower()
        name, cmd = self._pending_action
        
        if text_lower in ['y', 'yes', '是', '确认', '确定', '好']:
            self._pending_action = None
            try:
                subprocess.Popen(cmd, start_new_session=True)
                return f"✅ 正在执行{name}..."
            except Exception as e:
                return f"❌ {name}失败: {e}"
        
        elif text_lower in ['n', 'no', '否', '不', '取消', '算了']:
            self._pending_action = None
            return f"❎ 已取消{name}"
        
        # 还在等待确认
        return f"⚠️ 请确认：输入 y 执行{name}，输入 n 取消"
    
    # ---- 文件操作 ----
    
    def _handle_file_operation(self, text: str, text_lower: str) -> Optional[str]:
        # 打开文件
        match = re.search(r'打开文件\s+(.+)', text)
        if match:
            filepath = os.path.expanduser(match.group(1).strip())
            if os.path.exists(filepath):
                try:
                    subprocess.Popen(
                        ["xdg-open", filepath],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    return f"✅ 已打开: {filepath}"
                except:
                    return f"❌ 无法打开: {filepath}"
            return f"⚠️ 文件不存在: {filepath}"
        
        # 打开目录
        match = re.search(r'打开(?:目录|文件夹)\s+(.+)', text)
        if match:
            dirpath = os.path.expanduser(match.group(1).strip())
            if os.path.isdir(dirpath):
                try:
                    subprocess.Popen(
                        ["xdg-open", dirpath],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    return f"✅ 已打开目录: {dirpath}"
                except:
                    return f"❌ 无法打开: {dirpath}"
            return f"⚠️ 目录不存在: {dirpath}"
        
        # 搜索文件
        match = re.search(r'搜索文件\s+(.+)', text)
        if match:
            keyword = match.group(1).strip()
            try:
                result = subprocess.run(
                    ["find", os.path.expanduser("~"), "-name", f"*{keyword}*", "-type", "f"],
                    capture_output=True, text=True, timeout=10
                )
                output = result.stdout.strip()
                if output:
                    lines = output.split('\n')[:20]
                    return f"📁 找到 {len(lines)} 个文件:\n" + "\n".join(lines)
                return f"📁 未找到包含 '{keyword}' 的文件"
            except:
                return "❌ 搜索失败"
        
        # 查看文件
        match = re.search(r'查看文件\s+(.+)', text)
        if match:
            filepath = os.path.expanduser(match.group(1).strip())
            if os.path.isfile(filepath):
                try:
                    with open(filepath, 'r', errors='ignore') as f:
                        content = f.read(2000)
                    return f"📄 {filepath}:\n{content}"
                except:
                    return f"❌ 无法读取: {filepath}"
            return f"⚠️ 文件不存在: {filepath}"
        
        # 文件大小
        match = re.search(r'文件大小\s+(.+)', text)
        if match:
            filepath = os.path.expanduser(match.group(1).strip())
            if os.path.exists(filepath):
                try:
                    result = subprocess.run(
                        ["du", "-sh", filepath],
                        capture_output=True, text=True, timeout=5
                    )
                    return f"📊 {result.stdout.strip()}"
                except:
                    return "❌ 查询失败"
            return f"⚠️ 路径不存在: {filepath}"
        
        # 磁盘空间
        if re.search(r'磁盘空间|磁盘使用|硬盘空间', text):
            try:
                result = subprocess.run(["df", "-h"], capture_output=True, text=True, timeout=5)
                return f"💾 磁盘使用:\n{result.stdout.strip()[:1500]}"
            except:
                return "❌ 查询失败"
        
        return None
    
    # ---- 剪贴板 ----
    
    def _handle_clipboard(self, text: str, text_lower: str) -> Optional[str]:
        # 复制
        match = re.search(r'(?:复制|拷贝|clipboard copy)\s+(.+)', text)
        if match:
            content = match.group(1).strip()
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=content.encode('utf-8'),
                    capture_output=True,
                    timeout=5
                )
                return f"✅ 已复制到剪贴板: {content[:50]}{'...' if len(content) > 50 else ''}"
            except FileNotFoundError:
                return "⚠️ xclip 未安装，请运行: sudo apt install xclip"
            except Exception as e:
                return f"❌ 复制失败: {e}"
        
        # 粘贴
        if re.search(r'粘贴|读取剪贴板|查看剪贴板|clipboard paste', text_lower):
            try:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, text=True, timeout=5
                )
                content = result.stdout.strip()
                if content:
                    return f"📋 剪贴板内容:\n{content[:1000]}"
                return "📋 剪贴板为空"
            except:
                return "⚠️ xclip 未安装"
        
        # 清空剪贴板
        if re.search(r'清空剪贴板|清除剪贴板|clear clipboard', text_lower):
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=b'',
                    capture_output=True,
                    timeout=5
                )
                return "✅ 剪贴板已清空"
            except:
                return "⚠️ xclip 未安装"
        
        return None
    
    # ---- 通知 ----
    
    def _handle_notification(self, text: str, text_lower: str) -> Optional[str]:
        match = re.search(r'(?:通知我|提醒我|notify)\s+(.+)', text)
        if match:
            content = match.group(1).strip()
            try:
                subprocess.Popen(
                    ["notify-send", "Delphos", content],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                return f"✅ 已发送通知: {content}"
            except:
                return "⚠️ notify-send 不可用"
        
        return None
    
    # ---- 执行命令 ----
    
    def _handle_run_command(self, text: str, text_lower: str) -> Optional[str]:
        match = re.search(r'(?:执行|运行命令|执行命令|run)\s+(.+)', text)
        if not match:
            return None
        
        command = match.group(1).strip()
        cmd_lower = command.lower()
        
        # 安全检查
        for dangerous in CMD_BLACKLIST:
            if dangerous in cmd_lower:
                return f"⚠️ 危险命令已拦截"
        
        # 白名单检查
        allowed = False
        for allowed_cmd in CMD_WHITELIST:
            if cmd_lower.startswith(allowed_cmd):
                allowed = True
                break
        
        if not allowed:
            return f"⚠️ 命令不在白名单中，仅允许安全命令如: ls, cat, echo, date, df, free, ps, ping..."
        
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True,
                timeout=10
            )
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                if len(output) > 2000:
                    output = output[:2000] + "\n... (已截断)"
                return f"📟 执行结果:\n{output}"
            else:
                return "✅ 命令执行完成（无输出）"
        except subprocess.TimeoutExpired:
            return "⚠️ 命令超时"
        except Exception as e:
            return f"❌ 执行失败: {e}"
    
    # ---- 窗口控制 ----
    
    def _handle_window_control(self, text: str, text_lower: str) -> Optional[str]:
        # 最小化窗口
        if re.search(r'最小化窗口|minimize', text_lower):
            try:
                subprocess.run(
                    ["xdotool", "getactivewindow", "windowminimize"],
                    capture_output=True, timeout=3
                )
                return "✅ 窗口已最小化"
            except:
                return "⚠️ xdotool 不可用"
        
        # 关闭窗口
        if re.search(r'关闭窗口|close window', text_lower):
            try:
                subprocess.run(
                    ["xdotool", "getactivewindow", "windowkill"],
                    capture_output=True, timeout=3
                )
                return "✅ 窗口已关闭"
            except:
                return "⚠️ xdotool 不可用"
        
        # 切换窗口
        if re.search(r'切换窗口|下一个窗口|switch window', text_lower):
            try:
                subprocess.run(
                    ["xdotool", "key", "alt+Tab"],
                    capture_output=True, timeout=3
                )
                return "✅ 已切换窗口"
            except:
                return "⚠️ xdotool 不可用"
        
        # 显示桌面
        if re.search(r'显示桌面|show desktop|桌面', text_lower) and len(text) <= 6:
            try:
                subprocess.run(
                    ["xdotool", "key", "super+d"],
                    capture_output=True, timeout=3
                )
                return "✅ 已显示桌面"
            except:
                return "⚠️ xdotool 不可用"
        
        # 查看窗口列表
        if re.search(r'查看窗口列表|窗口列表|window list', text_lower):
            try:
                result = subprocess.run(
                    ["wmctrl", "-l"],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout.strip()
                if output:
                    return f"🪟 窗口列表:\n{output[:1500]}"
                return "🪟 无窗口"
            except:
                return "⚠️ wmctrl 不可用"
        
        return None


# ==================== 屏幕操作循环（第三层） ====================

class ScreenAgent:
    """屏幕操作循环 - 截图 → 模型推理 → 执行 → 再截图"""
    
    def __init__(self, config: Config, screenshot_mgr: ScreenshotManager,
                 executor: ActionExecutor, memory_db: MemoryDB):
        self.config = config
        self.screenshot_mgr = screenshot_mgr
        self.executor = executor
        self.memory_db = memory_db
    
    def run(self, user_request: str) -> str:
        print(f"\n🔁 开始屏幕操作: {user_request}")
        print(f"   最大步数: {self.config.MAX_STEPS}")
        
        messages = [
            {"role": "system", "content": SCREEN_AGENT_PROMPT},
            {"role": "user", "content": f"用户要求：{user_request}"},
        ]
        
        last_action = None
        self._repeat_count = 0
        
        for step in range(self.config.MAX_STEPS):
            print(f"\n--- 第 {step + 1}/{self.config.MAX_STEPS} 步 ---")
            
            result = self.screenshot_mgr.capture()
            if not result:
                return "❌ 截图失败"
            
            image_bytes, size = result
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            step_msg = {
                "role": "user",
                "content": f"当前屏幕截图（第{step+1}步）。请给出下一个操作，只输出一行 JSON。如果任务已完成，输出 {{\"action\":\"done\"}}",
                "images": [image_b64]
            }
            
            try:
                response = ollama.chat(
                    model=self.config.MODEL_NAME,
                    messages=messages + [step_msg],
                    keep_alive=self.config.KEEP_ALIVE,
                    options={
                        "temperature": self.config.TEMPERATURE,
                        "num_predict": 512,
                    }
                )
            except Exception as e:
                return f"❌ 模型调用失败: {e}"
            
            content = response['message']['content'].strip()
            print(f"   🤖 模型输出: {content[:200]}")
            
            action = self._parse_action(content)
            
            if action is None:
                messages.append({"role": "assistant", "content": content})
                continue
            
            if action.get("action") == "done":
                print("   ✅ 模型报告任务完成")
                return "✅ 任务完成"
            
            action_key = json.dumps(action, sort_keys=True)
            if action_key == last_action:
                self._repeat_count += 1
                if self._repeat_count >= self.config.REPEAT_LIMIT:
                    return f"⚠️ 检测到连续 {self._repeat_count} 次重复操作，任务中止"
                print(f"   ⚠️ 重复操作 ({self._repeat_count}/{self.config.REPEAT_LIMIT})")
                messages.append({
                    "role": "user",
                    "content": "这个操作和上一步相同，请尝试其他方法"
                })
                continue
            else:
                self._repeat_count = 0
            
            last_action = action_key
            
            success, result_msg = self.executor.execute(action)
            status = "✅" if success else "❌"
            print(f"   {status} {result_msg}")
            
            messages.append({
                "role": "assistant",
                "content": f"[执行操作] {json.dumps(action)} → {result_msg}"
            })
            
            time.sleep(self.config.STEP_DELAY)
            
            confirm_result = self.screenshot_mgr.capture()
            if confirm_result:
                confirm_bytes, _ = confirm_result
                confirm_b64 = base64.b64encode(confirm_bytes).decode('utf-8')
                messages.append({
                    "role": "user",
                    "content": "操作执行后的屏幕（确认结果）",
                    "images": [confirm_b64]
                })
            
            if not success:
                messages.append({
                    "role": "user",
                    "content": f"上一步操作失败: {result_msg}。请尝试其他方法。"
                })
        
        return f"⏰ 达到最大步数 ({self.config.MAX_STEPS})，任务可能未完成。"
    
    def _parse_action(self, text: str) -> Optional[Dict]:
        try:
            return json.loads(text)
        except:
            pass
        
        json_patterns = [
            r'\{[^{}]*"action"[^{}]*\}',
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1) if match.lastindex else match.group()
                    return json.loads(json_str)
                except:
                    continue
        
        return None


# ==================== 主助手 ====================

class DelphosAssistant:
    """Delphos 主助手 - 三层处理结构"""
    
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.memory_db = MemoryDB(self.config.DB_PATH)
        self.screenshot_mgr = ScreenshotManager(self.config)
        self.executor = ActionExecutor(self.config)
        self.screen_agent = ScreenAgent(
            self.config, self.screenshot_mgr, self.executor, self.memory_db
        )
        self.direct_handler = DirectActionHandler(self.config, self.screenshot_mgr)
        
        self._base_chat_prompt = CHAT_PROMPT
        self._base_agent_prompt = SCREEN_AGENT_PROMPT
        self._think_mode = False
        self._pending_confirmation = False
        
        self.stats = {
            "total_queries": 0,
            "direct_actions": 0,
            "screen_actions": 0,
            "chat_queries": 0,
            "total_time": 0.0,
        }
        
        print(f"✅ Delphos 助手已就绪")
        print(f"   模型: {self.config.MODEL_NAME}")
        print(f"   架构: 内置命令 | 直接操作 | 屏幕循环 | 对话")
    
    # ---- 第一层：内置命令 ----
    
    def _handle_builtin(self, user_input: str) -> Optional[str]:
        text = user_input.strip()
        text_lower = text.lower()
        
        # 问候
        if text_lower in GREETINGS:
            return GREETINGS[text_lower]
        
        # 时间
        if text_lower in ["时间", "几点了", "time", "现在几点"]:
            now = datetime.now()
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            return f"🕐 现在是 {now.strftime('%Y年%m月%d日')} 星期{weekdays[now.weekday()]} {now.strftime('%H:%M:%S')}"
        
        # 日期
        if text_lower in ["日期", "今天几号", "星期几", "今天日期"]:
            now = datetime.now()
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            return f"📅 {now.strftime('%Y年%m月%d日')} 星期{weekdays[now.weekday()]}"
        
        # IP
        if text_lower in ["ip", "我的ip", "ip地址", "内网ip"]:
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return f"🌐 本机内网 IP: {ip}"
            except:
                return "⚠️ 无法获取 IP 地址"
        
        # 系统信息
        if text_lower in ["系统信息", "sysinfo", "系统状态"]:
            if not HAS_PSUTIL:
                return "⚠️ 需要安装 psutil: pip install psutil"
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            return f"""📊 系统状态：
CPU: {cpu}%
内存: {mem.percent}% ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)
磁盘: {disk.percent}% ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)"""
        
        # 笑话
        if text_lower in ["笑话", "讲个笑话", "joke"]:
            return random.choice(JOKES)
        
        # 帮助
        if text_lower in ["帮助", "help", "/help", "命令", "功能"]:
            return self._help_text()
        
        # 数学表达式
        math_match = re.match(r'^[\d\+\-\*\/\(\)\.\s\%\^]+$', text)
        if math_match and any(c.isdigit() for c in text):
            try:
                result = eval(text.replace('^', '**'))
                return f"🧮 {text} = {result}"
            except:
                pass
        
        # /think on/off
        if text_lower == "/think on":
            self._think_mode = True
            return "🧠 思考模式已开启"
        if text_lower == "/think off":
            self._think_mode = False
            return "🧠 思考模式已关闭"
        
        # /stats
        if text_lower == "/stats":
            avg = self.stats["total_time"] / max(self.stats["total_queries"], 1)
            return f"""📊 使用统计：
总查询: {self.stats['total_queries']}
直接操作: {self.stats['direct_actions']}
屏幕操作: {self.stats['screen_actions']}
对话: {self.stats['chat_queries']}
平均耗时: {avg:.1f}s
思考模式: {'开' if self._think_mode else '关'}"""
        
        # /memory
        if text_lower.startswith("/memory"):
            keyword = text[7:].strip()
            if not keyword:
                return "用法: /memory 关键词"
            memories = self.memory_db.search_long_term(keyword, 5)
            if memories:
                lines = [f"  - [{m['category']}] {m['key_info']}" for m in memories]
                return f"🧠 找到 {len(memories)} 条记忆:\n" + "\n".join(lines)
            return "未找到相关记忆"
        
        # /clear
        if text_lower == "/clear":
            self.memory_db.clear_short_term()
            return "🧹 短期记忆已清空"
        
        return None
    
    def _help_text(self) -> str:
        return """📖 Delphos 助手命令：

【直接操作】（秒回，不走 AI）
  打开/启动 XX        打开应用（支持中英文别名）
  搜索/搜 XX          必应搜索
  百度 XX             百度搜索
  谷歌 XX             Google 搜索
  音量加/减/调到 XX%  音量控制
  静音/取消静音       静音切换
  亮度加/减/调到 XX%  屏幕亮度
  连接 WiFi XX        连接无线网络
  截图                保存截图
  锁屏                锁定屏幕
  关机/重启           需二次确认
  复制 XX / 粘贴      剪贴板操作
  通知我 XX           发送桌面通知
  执行 XX             运行白名单命令
  打开文件 XX         打开文件/目录
  搜索文件 XX         查找文件
  显示桌面            最小化所有窗口
  磁盘空间            查看磁盘使用

【屏幕操作】（AI 看图操作，30~60 秒）
  屏幕现在显示什么？    识别屏幕内容
  点击 XX 按钮         精准点击
  在浏览器里点收藏      应用内操作

【智能对话】（5~10 秒）
  直接提问，AI 会回答

【快捷命令】
  /think on|off  思考模式
  /stats         统计
  /memory 关键词 搜索记忆
  /clear         清空记忆
  exit / 退出    退出"""
    
    # ---- 判断是否需要屏幕操作 ----
    
    def _is_screen_action(self, text: str) -> bool:
        """收紧的关键词：只匹配真正需要看屏幕的操作"""
        screen_keywords = [
            "点击", "点一下", "点开", "双击", "右键",
            "屏幕显示什么", "屏幕上有什么", "看看屏幕", "当前界面",
            "帮我看看", "识别", "找到屏幕上的", "屏幕上的",
            "在浏览器里点", "在应用里点", "在软件里点",
            "屏幕上", "界面里", "截图看看",
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in screen_keywords)
    
    # ---- 主对话接口 ----
    
    def chat(self, user_input: str) -> str:
        """主对话接口 - 三层处理"""
        start_time = time.time()
        self.stats["total_queries"] += 1
        
        # === 第一层：内置命令 ===
        builtin_result = self._handle_builtin(user_input)
        if builtin_result is not None:
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            # 不打印耗时，内置命令太快
            return builtin_result
        
        # === 检查是否有待确认的操作 ===
        confirm_result = self.direct_handler.check_pending_confirmation(user_input)
        if confirm_result is not None:
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            return confirm_result
        
        # === 第二层：直接操作 ===
        direct_result = self.direct_handler.try_handle(user_input)
        if direct_result is not None:
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            self.stats["direct_actions"] += 1
            print(f"⚡ 直接操作 ({elapsed:.2f}s)")
            return direct_result
        
        # === 第三层：屏幕操作循环 ===
        if self._is_screen_action(user_input):
            self.stats["screen_actions"] += 1
            result = self.screen_agent.run(user_input)
            
            self.memory_db.add_message("user", user_input)
            self.memory_db.add_message("assistant", result)
            
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            print(f"⏱️ 屏幕操作完成 ({elapsed:.1f}s)")
            return result
        
        # === 第四层：兜底对话 ===
        self.stats["chat_queries"] += 1
        print("\n💭 思考中...", end="", flush=True)
        
        chat_prompt = self._base_chat_prompt
        if self._think_mode:
            chat_prompt += "\n\n请先一步步思考，再给出最终答案。"
        
        short_term = self.memory_db.get_recent(self.config.MAX_SHORT_TERM)
        long_term = self.memory_db.search_long_term(user_input, self.config.LONG_TERM_COUNT)
        
        messages = [{"role": "system", "content": chat_prompt}]
        
        if long_term:
            memories = "\n".join([f"- {m['key_info']}" for m in long_term])
            messages.append({
                "role": "system",
                "content": f"【相关记忆】\n{memories}"
            })
        
        for msg in short_term:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        messages.append({"role": "user", "content": user_input})
        
        try:
            stream = ollama.chat(
                model=self.config.MODEL_NAME,
                messages=messages,
                stream=True,
                keep_alive=self.config.KEEP_ALIVE,
                options={
                    "temperature": 0.7,
                    "num_predict": self.config.MAX_TOKENS,
                }
            )
            
            print("\r🤖 ", end="", flush=True)
            response_parts = []
            
            for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    content = chunk['message']['content']
                    response_parts.append(content)
                    print(content, end="", flush=True)
            
            print()
            response_text = "".join(response_parts).strip()
            
            self.memory_db.add_message("user", user_input)
            self.memory_db.add_message("assistant", response_text)
            
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            print(f"⏱️ ({elapsed:.1f}s)")
            
            return response_text
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            return f"❌ 调用失败: {e}"


# ==================== 主入口 ====================

def main():
    """主函数"""
    
    print("""
╔══════════════════════════════════════════╗
║     🖥️  Delphos AI 桌面助手             ║
║     qwen2.5vl:7b-q4_K_M  |  Debian     ║
╠══════════════════════════════════════════╣
║  三层处理：内置命令 | 直接操作 | AI     ║
║  输入 help 查看命令列表                  ║
║  输入 exit 退出                          ║
╚══════════════════════════════════════════╝
""")
    
    config = Config()
    print(f"✅ 使用模型: {config.MODEL_NAME}")
    
    # 检查必要工具
    for tool, pkg in [("xclip", "xclip"), ("xdotool", "xdotool")]:
        try:
            subprocess.run(["which", tool], capture_output=True, check=True)
        except:
            print(f"⚠️  {tool} 未安装，部分功能可能不可用: sudo apt install {pkg} -y")
    
    assistant = DelphosAssistant(config)
    
    while True:
        try:
            user_input = input("\n💬 你: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["exit", "quit", "退出", "/exit", "/quit", "/q"]:
                print("👋 再见！")
                break
            
            response = assistant.chat(user_input)
            # Bug修复：删除了 main() 中的重复打印
            # chat() 内部已经完成了所有输出（流式打印 + 返回值）
            # 对于非流式的直接操作，chat() 返回结果字符串
            # 这里只打印返回值（如果不是空或 None）
            if response:
                print(f"\n🤖 {response}")
            
        except KeyboardInterrupt:
            print("\n\n👋 再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            if config.DEBUG:
                traceback.print_exc()


if __name__ == "__main__":
    main()