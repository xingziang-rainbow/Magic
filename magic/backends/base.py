"""
模型后端统一接口
不管是本地 Ollama 还是云端 API，都要实现这个接口
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Generator


class BaseBackend(ABC):
    """所有模型后端的基类"""

    @abstractmethod
    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        """
        普通对话
        - messages: [{"role": "user", "content": "..."}]
        - stream: True 逐字返回，False 一次性返回
        """
        pass

    @abstractmethod
    def vision(self, prompt: str, image_b64: str, stream: bool = False) -> str:
        """
        带图片的对话
        - prompt: 文字提示
        - image_b64: base64 编码的图片
        """
        pass
