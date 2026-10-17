"""
配置加载器
读取 config.yaml，返回字典
"""
import os
import yaml

# 配置文件路径（和本文件同目录）
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config():
    """读取 YAML 配置，返回字典"""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 全局配置对象，其他模块直接 import 这个
CONFIG = load_config()
