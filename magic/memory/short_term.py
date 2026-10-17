# Version: V0.1
"""
短期记忆：存最近 N 轮对话，放在内存里
会话结束就丢，不持久化
"""

from typing import List, Dict
from collections import deque


class ShortTermMemory:
    """短期对话记忆，保留最近 N 轮"""

    def __init__(self, max_turns: int = 10):
        """
        max_turns: 最多保留多少轮对话（一问一答算一轮）
        """
        self.max_turns = max_turns
        # deque 自动丢弃超出长度的旧元素
        self.messages = deque(maxlen=max_turns * 2)

    def add_user(self, content: str):
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        """添加助手回复"""
        self.messages.append({"role": "assistant", "content": content})

    def get_messages(self) -> List[Dict]:
        """返回所有消息，供模型调用"""
        return list(self.messages)

    def clear(self):
        """清空短期记忆"""
        self.messages.clear()

    def __len__(self):
        """返回消息条数"""
        return len(self.messages)

