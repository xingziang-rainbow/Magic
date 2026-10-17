# Version: V0.2
"""
文件操作模块
创建、读取、写入、搜索、删除、复制、移动、列目录
删除操作需用户确认
"""

import os
import re
import shutil
import subprocess


class FileTools:
    """文件操作"""

    def __init__(self, default_dir: str = "~/Documents"):
        self.default_dir = os.path.expanduser(default_dir)
        os.makedirs(self.default_dir, exist_ok=True)

    # ============ 创建文件 ============
    def create_file(self, filename: str, content: str = "") -> str:
        """
        创建文件
        - filename: 文件名（如 note.txt）
        - content:  文件内容（可选）
        """
        filepath = self._resolve_path(filename.strip())

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return f"✅ 已创建文件：{filepath}"
        except Exception as e:
            return f"❌ 创建失败：{e}"

    # ============ 写内容到文件 ============
    def write_file(self, filename: str, content: str) -> str:
        """向文件追加内容"""
        filepath = self._resolve_path(filename.strip())

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(content + "\n")
            return f"✅ 已写入：{filepath}"
        except Exception as e:
            return f"❌ 写入失败：{e}"

    # ============ 读取文件 ============
    def read_file(self, filename: str) -> str:
        filepath = self._resolve_path(filename.strip())
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return f"📄 {filepath}：\n{content[:2000]}"
        except FileNotFoundError:
            return f"❌ 文件不存在：{filepath}"
        except Exception as e:
            return f"❌ 读取失败：{e}"

    # ============ 搜索文件 ============
    def search_files(self, keyword: str) -> str:
        keyword = keyword.strip()
        if not keyword:
            return "❌ 请提供搜索关键词"

        try:
            r = subprocess.run(
                ["find", os.path.expanduser("~"), "-name", f"*{keyword}*", "-type", "f"],
                capture_output=True, text=True, timeout=15
            )
            lines = r.stdout.strip().split("\n")[:20]
            if lines and lines[0]:
                return "🔍 找到以下文件：\n" + "\n".join(lines)
            return f"❌ 未找到包含 '{keyword}' 的文件"
        except subprocess.TimeoutExpired:
            return "❌ 搜索超时"
        except Exception as e:
            return f"❌ 搜索失败：{e}"

    # ============ 列出目录 ============
    def list_dir(self, path: str = "") -> str:
        dirpath = self._resolve_path(path.strip()) if path.strip() else self.default_dir
        try:
            entries = os.listdir(dirpath)
            return f"📁 {dirpath}：\n" + "\n".join(entries[:50])
        except FileNotFoundError:
            return f"❌ 目录不存在：{dirpath}"
        except Exception as e:
            return f"❌ 列出失败：{e}"

    # ============ 删除（需确认） ============
    def delete(self, path: str) -> str:
        filepath = self._resolve_path(path.strip())

        if not os.path.exists(filepath):
            return f"❌ 不存在：{filepath}"

        print(f"\n⚠️  即将删除：{filepath}")
        answer = input("   确认删除？(y/N): ").strip().lower()
        if answer != "y":
            return "❌ 已取消"

        try:
            if os.path.isdir(filepath):
                shutil.rmtree(filepath)
            else:
                os.remove(filepath)
            return f"✅ 已删除：{filepath}"
        except Exception as e:
            return f"❌ 删除失败：{e}"

    # ============ 复制 ============
    def copy(self, src: str, dst: str) -> str:
        src_path = self._resolve_path(src.strip())
        dst_path = self._resolve_path(dst.strip())

        try:
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)
            return f"✅ 已复制：{src_path} → {dst_path}"
        except Exception as e:
            return f"❌ 复制失败：{e}"

    # ============ 移动/重命名 ============
    def move(self, src: str, dst: str) -> str:
        src_path = self._resolve_path(src.strip())
        dst_path = self._resolve_path(dst.strip())

        try:
            shutil.move(src_path, dst_path)
            return f"✅ 已移动：{src_path} → {dst_path}"
        except Exception as e:
            return f"❌ 移动失败：{e}"

    # ============ 创建目录 ============
    def create_dir(self, name: str) -> str:
        dirpath = self._resolve_path(name.strip())
        try:
            os.makedirs(dirpath, exist_ok=True)
            return f"✅ 已创建目录：{dirpath}"
        except Exception as e:
            return f"❌ 创建失败：{e}"

    # ============ 辅助：补全路径 ============
    def _resolve_path(self, path: str) -> str:
        """如果路径是相对路径，补到默认目录下"""
        path = os.path.expanduser(path)
        if os.path.isabs(path):
            return path
        return os.path.join(self.default_dir, path)
