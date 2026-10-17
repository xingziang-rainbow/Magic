# Version: V0.1
"""
Ollama 本地模型后端
通过 HTTP API 调用本地 Ollama 服务
自动检测并启动 Ollama 服务
"""
import json
import socket
import subprocess
import time
import os
from typing import List, Dict

import requests

try:
    from .base import BaseBackend
except ImportError:
    from base import BaseBackend


def ensure_ollama_running(host='localhost', port=11434, timeout=30):
    """确保 Ollama 服务在运行，如果未运行则自动启动"""
    def is_port_open():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex((host, port)) == 0

    if is_port_open():
        return True

    print("Ollama 服务未运行，正在自动启动...")
    log_path = os.path.expanduser("~/rainbow/ollama.log")
    with open(log_path, "a") as log_file:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True
        )

    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_open():
            print("Ollama 服务已启动")
            return True
        time.sleep(0.5)

    raise RuntimeError(f"Ollama 服务启动超时 ({timeout} 秒)")


class OllamaBackend(BaseBackend):
    """Ollama 本地后端"""

    def __init__(self, model: str, keep_alive: str = "30m",
                 temperature: float = 0.2, url: str = "http://localhost:11434"):
        self.model = model
        self.keep_alive = keep_alive
        self.temperature = temperature
        self.url = url + "/api/chat"

        ensure_ollama_running()

    def _post(self, messages: List[Dict], stream: bool, images: List[str] = None) -> str:
        if images:
            messages = messages.copy()
            messages[-1] = dict(messages[-1])
            messages[-1]["images"] = images

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature},
        }

        if not stream:
            resp = requests.post(self.url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            return msg.get("content") or msg.get("thinking") or ""
        else:
            return self._stream(payload)

    def _stream(self, payload: dict):
        with requests.post(self.url, json=payload, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})
                    text = msg.get("content") or msg.get("thinking") or ""
                    if text:
                        yield text
                except json.JSONDecodeError:
                    continue

    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        return self._post(messages, stream)

    def vision(self, prompt: str, image_b64: str, stream: bool = False) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self._post(messages, stream, images=[image_b64])
