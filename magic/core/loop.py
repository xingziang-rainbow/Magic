# Version: V0.5
"""
Magic 主循环
新增：启动时后台预热模型，解决第一次提问慢的问题
"""
import os
import sys
import json
import re
import importlib.util
import threading
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import CONFIG
from backends.ollama_backend import OllamaBackend
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_registry_mod = _load_module("registry", os.path.join(_BASE, "模块", "内部", "registry.py"))
ToolRegistry = _registry_mod.ToolRegistry


class Magic:
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

        self.base_prompt = (
            "你是 Magic，Rainbow 系统的 AI 助手。回答简洁，用中文。\n"
            "只回答用户问题，不要解释自己是 AI。\n\n"
        )
        self.system_prompt = self.base_prompt + self.registry.get_prompt()

    def _warmup_model(self):
        """后台预热模型，防止首次提问等待过久"""
        try:
            # 发送一个极简请求，要求只生成 1 个 token，强制 Ollama 加载模型
            payload = {
                "model": CONFIG["model"]["name"],
                "messages": [{"role": "user", "content": "."}],
                "stream": False,
                "keep_alive": CONFIG["model"]["keep_alive"],
                "options": {"num_predict": 1}
            }
            requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
        except Exception:
            pass

    def _parse_tool_call(self, text: str):
        text = re.sub(r"```json\s*|\s*```", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1: return None
        candidate = text[start:end + 1]
        if len(candidate) < len(text.strip()) * 0.5: return None
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or "tool" not in data: return None
        tool_name = data.pop("tool")
        return tool_name, data

    def chat(self, user_input: str):
        self.short_mem.add_user(user_input)
        messages = [{"role": "system", "content": self.system_prompt}]
        messages += self.short_mem.get_messages()

        # 1. 让 AI 判断
        print("Magic: ", end="", flush=True)
        full_reply = ""
        for chunk in self.backend.chat(messages, stream=True):
            print(chunk, end="", flush=True)
            full_reply += chunk
        print()

        tool_call = self._parse_tool_call(full_reply)
        if tool_call is None:
            self.short_mem.add_assistant(full_reply)
            return full_reply, True

        # 2. 执行工具
        tool_name, args = tool_call
        print(f"  ⚙️  执行工具：{tool_name} {args}")

        result = self.registry.execute(tool_name, args)
        
        # --- 重点：把长文本放到 [思考过程] 里 ---
        if tool_name in ["web_search", "read_file"] and len(result) > 100:
            print(f"\n  🤔 [思考过程] 读取到长文本，正在提取关键信息...")
            print("  ┌" + "─" * 40)
            # 截取前 300 个字符显示，避免刷屏
            preview = result[:300].replace("\n", "\n  │ ")
            print(f"  │ {preview}...")
            print("  └" + "─" * 40 + "\n")
            print(f"  📋 已获取内容，交由 AI 总结。")
        else:
            print(f"  📋 结果：{result}")

        # 3. 把结果给 AI 总结
        self.short_mem.add_assistant(full_reply)
        
        # 给 AI 的提示：过滤垃圾信息
        summary_prompt = (
            f"我刚调用工具抓取到了以下内容，里面可能包含广告、页脚或无关信息。\n"
            f"请忽略无关内容，提取与用户问题相关的信息，用通顺、精炼的中文回复我。\n\n"
            f"【抓取内容】\n{result}"
        )
        self.short_mem.add_user(summary_prompt)

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

    def run(self):
        # 启动后台线程预热模型
        threading.Thread(target=self._warmup_model, daemon=True).start()
        
        print("=" * 50)
        print("Magic 已启动（模型正在后台预热...）")
        print("=" * 50)

        while True:
            try:
                user_input = input("\n你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见")
                break
            if not user_input: continue
            if user_input.lower() in ["exit", "quit", "退出"]:
                print("Magic: 再见")
                break
            self.chat(user_input)

if __name__ == "__main__":
    magic = Magic()
    magic.run()
