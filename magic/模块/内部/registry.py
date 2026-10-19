# Version: V0.4
"""
工具注册表
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
_web_mod = _load_module("web", os.path.join(_BASE, "web.py"))

TOOLS = {
    # ... 前面 system 和 file 的定义保持不变 ...
    "open_app": {"desc": "打开应用", "params": {"name": "应用名"}, "module": "system", "method": "open_app"},
    "volume": {"desc": "调整音量", "params": {"text": "调整指令"}, "module": "system", "method": "volume"},
    "get_time": {"desc": "获取时间", "params": {}, "module": "system", "method": "get_time"},
    "screenshot": {"desc": "截图", "params": {}, "module": "system", "method": "screenshot"},
    "lock_screen": {"desc": "锁屏", "params": {}, "module": "system", "method": "lock_screen"},
    "clipboard_copy": {"desc": "复制到剪贴板", "params": {"text": "内容"}, "module": "system", "method": "clipboard_copy"},
    "clipboard_paste": {"desc": "读取剪贴板", "params": {}, "module": "system", "method": "clipboard_paste"},
    "search": {"desc": "浏览器搜索", "params": {"query": "关键词"}, "module": "system", "method": "search"},
    "run_command": {"desc": "执行命令", "params": {"command": "命令"}, "module": "system", "method": "run_command"},
    "create_file": {"desc": "创建文件", "params": {"filename": "文件名", "content": "内容"}, "module": "file", "method": "create_file"},
    "write_file": {"desc": "写文件", "params": {"filename": "文件名", "content": "内容"}, "module": "file", "method": "write_file"},
    "read_file": {"desc": "读文件", "params": {"filename": "文件名"}, "module": "file", "method": "read_file"},
    "search_files": {"desc": "搜索文件", "params": {"keyword": "关键词"}, "module": "file", "method": "search_files"},
    "list_dir": {"desc": "列出目录", "params": {"path": "路径"}, "module": "file", "method": "list_dir"},
    "delete": {"desc": "删除文件", "params": {"path": "路径"}, "module": "file", "method": "delete"},
    "copy": {"desc": "复制文件", "params": {"src": "源", "dst": "目标"}, "module": "file", "method": "copy"},
    "move": {"desc": "移动文件", "params": {"src": "源", "dst": "目标"}, "module": "file", "method": "move"},
    "create_dir": {"desc": "创建目录", "params": {"name": "目录名"}, "module": "file", "method": "create_dir"},
    
    # 修改 web_search 的描述，强制 AI 提炼关键词
    "web_search": {
        "desc": "联网搜索。提取最精简的关键词（如：用“AI 行业动态”代替“帮我搜一下最近AI新闻”），不需要带礼貌用语。",
        "params": {"query": "精简的搜索词"},
        "module": "web",
        "method": "web_search",
    },
}

class ToolRegistry:
    def __init__(self):
        self.system = _system_mod.SystemTools()
        self.file = _file_mod.FileTools()
        self.web = _web_mod.WebTools()

    def get_prompt(self) -> str:
        lines = ["【可用工具】"]
        lines.append("当你需要操作系统时，只输出一行 JSON，不要附加其他文字：")
        lines.append("")
        for name, info in TOOLS.items():
            example = f'{{"tool": "{name}"'
            if info["params"]:
                for k in info["params"].keys():
                    example += f', "{k}": "..."'
            example += "}"
            lines.append(f"- {name}：{info['desc']}")
            lines.append(f"  格式：{example}")
        lines.append("")
        lines.append("【重要规则】")
        lines.append("- 日常聊天直接回答，不要输出 JSON")
        lines.append("- 需要操作电脑时才输出 JSON，一次只调用一个工具")
        lines.append("- 使用 web_search 时，必须提取精简的关键词，不要原样照抄用户的话")
        return "\n".join(lines)

    def execute(self, tool_name: str, args: dict) -> str:
        info = TOOLS.get(tool_name)
        if not info: return f"❌ 未知工具：{tool_name}"
        if info["module"] == "system": target = self.system
        elif info["module"] == "file": target = self.file
        elif info["module"] == "web": target = self.web
        else: return f"❌ 未知模块：{info['module']}"

        method = getattr(target, info["method"], None)
        if not method: return f"❌ 方法不存在：{info['method']}"
        
        param_names = list(info["params"].keys())
        try:
            if not param_names: return method()
            values = [args.get(k, "") for k in param_names]
            return method(*values)
        except Exception as e:
            return f"❌ 执行出错：{e}"
