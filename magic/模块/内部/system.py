# Version: V0.3
"""
系统操作模块
打开应用、音量、时间、截图、剪贴板、窗口、搜索、命令
能用系统命令的，绝不走视觉
危险命令执行前需用户确认
"""

import os
import re
import subprocess
from datetime import datetime


# 应用映射表：别名 → 实际命令
APP_MAP = {
    "firefox": "firefox", "火狐": "firefox", "火狐浏览器": "firefox",
    "chromium": "chromium", "chrome": "chromium", "谷歌浏览器": "chromium",
    "终端": "xfce4-terminal", "命令行": "xfce4-terminal", "terminal": "xfce4-terminal",
    "文件管理器": "thunar", "文件夹": "thunar", "files": "thunar",
    "vscode": "code", "vs code": "code", "代码编辑器": "code",
    "文本编辑器": "gedit", "记事本": "gedit",
    "libreoffice": "libreoffice", "office": "libreoffice", "办公": "libreoffice",
    "vlc": "vlc", "播放器": "vlc", "视频播放器": "vlc",
    "计算器": "galculator", "calculator": "galculator",
    "系统监视器": "xfce4-taskmanager", "任务管理器": "xfce4-taskmanager",
    "设置": "xfce4-settings-manager", "系统设置": "xfce4-settings-manager",
    "截图工具": "xfce4-screenshooter",
    "图片查看器": "eog", "看图": "eog",
    "邮件": "thunderbird", "邮箱": "thunderbird",
    "pdf": "evince", "PDF阅读器": "evince",
    "归档管理器": "file-roller", "压缩": "file-roller",
}


# 危险命令关键词（执行前需要用户确认）
DANGEROUS_KEYWORDS = [
    "rm ", "rm-", "rmdir", "mkfs", "dd ", "shutdown", "reboot",
    "poweroff", "halt", "init 0", "init 6", "> /dev/sd",
    "chmod", "chown", "sudo", "su ",
]


class SystemTools:
    """系统操作"""

    # ============ 打开应用 ============
    def open_app(self, name: str) -> str:
        """打开应用，支持模糊匹配"""
        name_lower = name.lower().strip()

        cmd = APP_MAP.get(name_lower)
        if not cmd:
            for alias, real in APP_MAP.items():
                if alias in name_lower or name_lower in alias:
                    cmd = real
                    break

        if not cmd:
            cmd = name_lower

        try:
            subprocess.Popen(
                [cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return f"✅ 已打开 {cmd}"
        except FileNotFoundError:
            return f"❌ 未找到应用：{cmd}"
        except Exception as e:
            return f"❌ 打开失败：{e}"

    # ============ 音量控制 ============
    def volume(self, text: str) -> str:
        text_lower = text.lower()

        m = re.search(r'(\d+)\s*%', text_lower)
        if m:
            percent = min(100, max(0, int(m.group(1))))
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
                           capture_output=True)
            return f"✅ 音量已调到 {percent}%"

        if "静音" in text_lower or "关闭声音" in text_lower:
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                           capture_output=True)
            return "✅ 已切换静音"

        if "音量加" in text_lower or "大声" in text_lower:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"],
                           capture_output=True)
            return "✅ 音量 +10%"

        if "音量减" in text_lower or "小声" in text_lower:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"],
                           capture_output=True)
            return "✅ 音量 -10%"

        return "❌ 没理解音量指令"

    # ============ 获取时间 ============
    def get_time(self) -> str:
        """获取当前时间"""
        now = datetime.now()
        week = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
        return f"现在是 {now.strftime('%Y年%m月%d日 %H:%M:%S')}，星期{week}"

    # ============ 截图 ============
    def screenshot(self) -> str:
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            desktop = os.path.expanduser("~/桌面")
            if not os.path.exists(desktop):
                desktop = os.path.expanduser("~/Pictures")
            if not os.path.exists(desktop):
                desktop = os.path.expanduser("~")
            path = os.path.join(desktop, f"screenshot_{ts}.png")

            subprocess.run(["gnome-screenshot", "-f", path], capture_output=True, timeout=5)
            return f"✅ 截图已保存：{path}"
        except Exception as e:
            return f"❌ 截图失败：{e}"

    # ============ 锁屏 ============
    def lock_screen(self) -> str:
        try:
            subprocess.Popen(["xdg-screensaver", "lock"])
            return "✅ 屏幕已锁定"
        except Exception as e:
            return f"❌ 锁屏失败：{e}"

    # ============ 剪贴板 ============
    def clipboard_copy(self, text: str) -> str:
        try:
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=text.encode(), timeout=3)
            return f"✅ 已复制：{text[:30]}..."
        except Exception as e:
            return f"❌ 复制失败：{e}"

    def clipboard_paste(self) -> str:
        try:
            r = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                               capture_output=True, text=True, timeout=3)
            content = r.stdout.strip()
            return f"剪贴板内容：{content}" if content else "剪贴板为空"
        except Exception as e:
            return f"❌ 读取失败：{e}"

    # ============ 窗口控制 ============
    def window(self, text: str) -> str:
        text_lower = text.lower()
        try:
            if "最小化" in text_lower:
                subprocess.run(["xdotool", "getactivewindow", "windowminimize"],
                               capture_output=True)
                return "✅ 窗口已最小化"
            if "关闭窗口" in text_lower:
                subprocess.run(["xdotool", "getactivewindow", "windowkill"],
                               capture_output=True)
                return "✅ 窗口已关闭"
            if "切换窗口" in text_lower or "下一个窗口" in text_lower:
                subprocess.run(["xdotool", "key", "alt+Tab"], capture_output=True)
                return "✅ 已切换窗口"
            if "显示桌面" in text_lower:
                subprocess.run(["xdotool", "key", "super+d"], capture_output=True)
                return "✅ 已显示桌面"
            if "窗口列表" in text_lower:
                r = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
                return f"当前窗口：\n{r.stdout}"
        except Exception as e:
            return f"❌ 窗口操作失败：{e}"
        return "❌ 没理解窗口指令"

    # ============ 搜索 ============
    def search(self, query: str) -> str:
        import urllib.parse
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        try:
            subprocess.Popen(["xdg-open", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"✅ 已在浏览器搜索：{query}"
        except Exception as e:
            return f"❌ 搜索失败：{e}"

    # ============ 执行命令（危险命令需用户确认） ============
    def run_command(self, command: str) -> str:
        cmd_lower = command.lower()

        is_dangerous = any(kw in cmd_lower for kw in DANGEROUS_KEYWORDS)

        if is_dangerous:
            print(f"\n⚠️  检测到危险命令：{command}")
            answer = input("   确认执行？(y/N): ").strip().lower()
            if answer != "y":
                return "❌ 已取消，未执行"

        try:
            r = subprocess.run(command, shell=True, capture_output=True,
                               text=True, timeout=30)
            output = r.stdout.strip() or r.stderr.strip()
            return f"✅ 执行结果：\n{output[:1000]}" if output else "✅ 命令执行完成（无输出）"
        except subprocess.TimeoutExpired:
            return "❌ 命令超时"
        except Exception as e:
            return f"❌ 执行失败：{e}"
