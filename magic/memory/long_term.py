# Version: V0.1
"""
长期记忆：存用户偏好、重要信息，持久保存到 SQLite
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Tuple


class LongTermMemory:
    """长期记忆，存在 SQLite 里"""

    def __init__(self, db_path: str = "~/.local/share/rainbow/memory.db"):
        # 展开 ~ 为用户家目录
        self.db_path = os.path.expanduser(db_path)

        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # 连接数据库并建表
        self.conn = sqlite3.connect(self.db_path)
        self._init_table()

    def _init_table(self):
        """初始化表结构"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def add(self, content: str, category: str = "general"):
        """
        添加一条记忆
        category: general（一般）或 profile（个人偏好）
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT INTO memories (content, category, created_at) VALUES (?, ?, ?)",
            (content, category, now)
        )
        self.conn.commit()

    def search(self, keyword: str, limit: int = 5) -> List[Tuple]:
        """按关键词搜索记忆"""
        cursor = self.conn.execute(
            "SELECT content, category, created_at FROM memories "
            "WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{keyword}%", limit)
        )
        return cursor.fetchall()

    def get_recent(self, limit: int = 5) -> List[Tuple]:
        """获取最近的 N 条记忆"""
        cursor = self.conn.execute(
            "SELECT content, category, created_at FROM memories "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return cursor.fetchall()

    def delete(self, keyword: str) -> int:
        """删除包含关键词的记忆，返回删除条数"""
        cursor = self.conn.execute(
            "DELETE FROM memories WHERE content LIKE ?",
            (f"%{keyword}%",)
        )
        self.conn.commit()
        return cursor.rowcount

    def close(self):
        """关闭数据库连接"""
        self.conn.close()
