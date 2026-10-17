# Version: V0.3
"""
Magic 主循环
AI 自己判断：聊天 or 调用工具
脚本只负责给工具定义、执行工具、把结果返回 AI
"""

import os
import sys
import json
import re
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import CONFIG
from backends.ollama_backend import OllamaBackend
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory

# 加载中文目录下的 registry
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_registry_mod = _load_module(
    "registry",
    os.path.join(_BASE, "模块", "内部", "registry.py")
)
ToolRegistry = _registry_mod.ToolRegistry


class Magic:
    """Magic 主类"""

    def __init__(self):
        cfg = CONFIG

        self.backend = OllamaBackend(
            model=cfg["model"]["name"],
            keep_alive=cfg["model"]["keep_alive"],
            temperature=cfg["model"]["temperature"],
        )
        self.short_mem = ShortTermMemory(max_turns=cfg["memory"]["max_short_term"])
        self.long_mem = LongTermMemory(db_path=cfg["memory"]["db_path"])
        self.registry = ToolRegistry()

        # 基础人设
        self.base_prompt = (
            "你是 Magic，Rainbow 系统的 AI 助手。回答简洁，用中文。\n"
            "只回答用户问题，不要解释自己是 AI。\n\n"
        )

        # 完整系统提示词 = 人设 + 工具说明书
        self.system_prompt = self.base_prompt + self.registry.get_prompt()

    # ============ 解析 AI 输出中的工具调用 ============
    def _parse_tool_call(self, text: str):
        """
        从 AI 回复中提取工具调用 JSON
        返回 (tool_name, args) 或 None
        """
        # 去掉 markdown 代码块
        text = re.sub(r"```json\s*|\s*```", "", text).strip()

        # 找第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None

        candidate = text[start:end + 1]

        # 如果文本里除了 JSON 还有别的（说明是解释性的），不算工具调用
        # 简单判断：JSON 长度应该占文本大部分
        if len(candidate) < len(text.strip()) * 0.5:
            return None

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None
        if "tool" not in data:
            return None

        tool_name = data.pop("tool")
        return tool_name, data

    # ============ 处理一次输入 ============
    def chat(self, user_input: str):
        """处理一次用户输入，返回 (回复文本, 是否已打印)"""
        self.short_mem.add_user(user_input)

        messages = [{"role": "system", "content": self.system_prompt}]
        messages += self.short_mem.get_messages()

        # 第一次调用：让 AI 判断
        print("Magic: ", end="", flush=True)
        full_reply = ""
        for chunk in self.backend.chat(messages, stream=True):
            print(chunk, end="", flush=True)
            full_reply += chunk
        print()

        # 检查是不是工具调用
        tool_call = self._parse_tool_call(full_reply)

        if tool_call is None:
            # 普通对话，直接返回
            self.short_mem.add_assistant(full_reply)
            return full_reply, True

        # ==== 是工具调用，执行它 ====
        tool_name, args = tool_call
        print(f"  ⚙️  执行工具：{tool_name} {args}")

        result = self.registry.execute(tool_name, args)
        print(f"  📋 结果：{result}")

        # 把工具执行结果发回 AI，让它组织最终回复
        self.short_mem.add_assistant(full_reply)
        self.short_mem.add_user(f"工具执行结果：{result}\n请用一句自然的话告诉用户。")

        messages = [{"role": "system", "content": self.base_prompt}]
        messages += self.short_mem.get_messages()

        print("Magic: ", end="", flush=True)
        final_reply = ""
        for chunk in self.backend.chat(messages, stream=True):
            print(chunk, end="", flush=True)
            final_reply += chunk
        print()

        self.short_mem.add_assistant(final_reply)
        return final_reply, True

    # ============ 主循环 ============
    def run(self):
        print("=" * 50)
        print("Magic 已启动（输入 exit 退出）")
        print("=" * 50)

        while True:
            try:
                user_input = input("\n你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见")
                break

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "退出"]:
                print("Magic: 再见")
                break

            self.chat(user_input)


if __name__ == "__main__":
    magic = Magic()
    magic.run()
