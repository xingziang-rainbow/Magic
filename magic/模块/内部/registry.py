# Version: V0.2
"""
工具注册表
- 把所有可用工具列出来（给 AI 看）
- 根据 AI 返回的 JSON，调用对应的方法
"""

import os
import importlib.util

_BASE = os.path.dirname(os.path.abspath(__file__))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_system_mod = _load_module("system", os.path.join(_BASE, "system.py"))
_file_mod = _load_module("file", os.path.join(_BASE, "file.py"))


# 工具定义：名称 → (说明, 参数名, 属于哪个模块, 方法名)
TOOLS = {
    # ===== 系统操作 =====
    "open_app": {
        "desc": "打开应用",
        "params": {"name": "应用名（中英文都行）"},
        "module": "system",
        "method": "open_app",
    },
    "volume": {
        "desc": "调整音量",
        "params": {"text": "如：音量调到50%、静音、音量加"},
        "module": "system",
        "method": "volume",
    },
    "get_time": {
        "desc": "获取当前时间和日期",
        "params": {},
        "module": "system",
        "method": "get_time",
    },
    "screenshot": {
        "desc": "截图并保存",
        "params": {},
        "module": "system",
        "method": "screenshot",
    },
    "lock_screen": {
        "desc": "锁定屏幕",
        "params": {},
        "module": "system",
        "method": "lock_screen",
    },
    "clipboard_copy": {
        "desc": "复制内容到剪贴板",
        "params": {"text": "要复制的内容"},
        "module": "system",
        "method": "clipboard_copy",
    },
    "clipboard_paste": {
        "desc": "读取剪贴板内容",
        "params": {},
        "module": "system",
        "method": "clipboard_paste",
    },
    "search": {
        "desc": "浏览器搜索",
        "params": {"query": "搜索关键词"},
        "module": "system",
        "method": "search",
    },
    "run_command": {
        "desc": "执行系统命令（危险命令会向用户确认）",
        "params": {"command": "要执行的命令"},
        "module": "system",
        "method": "run_command",
    },

    # ===== 文件操作 =====
    "create_file": {
        "desc": "创建文件（可带内容）",
        "params": {"filename": "文件名（如 note.txt）", "content": "文件内容（可选）"},
        "module": "file",
        "method": "create_file",
    },
    "write_file": {
        "desc": "向文件追加内容",
        "params": {"filename": "文件名", "content": "要追加的内容"},
        "module": "file",
        "method": "write_file",
    },
    "read_file": {
        "desc": "读取文件内容",
        "params": {"filename": "文件名或路径"},
        "module": "file",
        "method": "read_file",
    },
    "search_files": {
        "desc": "搜索文件",
        "params": {"keyword": "关键词"},
        "module": "file",
        "method": "search_files",
    },
    "list_dir": {
        "desc": "列出目录内容",
        "params": {"path": "目录路径（可选，默认 ~/Documents）"},
        "module": "file",
        "method": "list_dir",
    },
    "delete": {
        "desc": "删除文件或目录（会向用户确认）",
        "params": {"path": "路径"},
        "module": "file",
        "method": "delete",
    },
    "copy": {
        "desc": "复制文件或目录",
        "params": {"src": "源路径", "dst": "目标路径"},
        "module": "file",
        "method": "copy",
    },
    "move": {
        "desc": "移动或重命名文件",
        "params": {"src": "源路径", "dst": "目标路径"},
        "module": "file",
        "method": "move",
    },
    "create_dir": {
        "desc": "创建目录",
        "params": {"name": "目录名或路径"},
        "module": "file",
        "method": "create_dir",
    },
}


class ToolRegistry:
    """工具注册表 + 执行器"""

    def __init__(self):
        self.system = _system_mod.SystemTools()
        self.file = _file_mod.FileTools()

    def get_prompt(self) -> str:
        """生成给 AI 的工具说明书"""
        lines = ["【可用工具】"]
        lines.append("当你需要操作系统时，只输出一行 JSON，不要附加其他文字：")
        lines.append("")

        for name, info in TOOLS.items():
            params_str = ", ".join(
                f'"{k}": "{v}"' for k, v in info["params"].items()
            )
            example = f'{{"tool": "{name}"'
            if info["params"]:
                for k in info["params"].keys():
                    example += f', "{k}": "..."'
            example += "}"

            lines.append(f"- {name}：{info['desc']}")
            lines.append(f"  格式：{example}")

        lines.append("")
        lines.append("【重要规则】")
        lines.append("- 日常聊天（打招呼、问问题、闲聊）→ 直接回答，不要输出 JSON")
        lines.append("- 需要操作电脑时才输出 JSON，一次只调用一个工具")
        lines.append("- 不确定要不要操作时，直接回答，不调用")
        return "\n".join(lines)

    def execute(self, tool_name: str, args: dict) -> str:
        """执行 AI 指定的工具"""
        info = TOOLS.get(tool_name)
        if not info:
            return f"❌ 未知工具：{tool_name}"

        if info["module"] == "system":
            target = self.system
        elif info["module"] == "file":
            target = self.file
        else:
            return f"❌ 未知模块：{info['module']}"

        method = getattr(target, info["method"], None)
        if not method:
            return f"❌ 方法不存在：{info['method']}"

        param_names = list(info["params"].keys())
        try:
            if not param_names:
                return method()
            else:
                values = [args.get(k, "") for k in param_names]
                return method(*values)
        except Exception as e:
            return f"❌ 执行出错：{e}"
