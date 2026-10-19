#!/bin/bash
set -e

# 强制使用清华源加速 pip
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

echo "==> 1/5 安装系统依赖"
sudo apt update
sudo apt install -y git python3-dev python3-venv python3-pip build-essential libxslt1-dev libxml2-dev zlib1g-dev libffi-dev libssl-dev python3-babel wget unzip

echo "==> 2/5 克隆 SearXNG 源码（使用 Gitee 国内镜像）"
rm -rf ~/searxng
mkdir -p ~/searxng
cd ~/searxng

# 使用 Gitee 镜像，网络稳定
git clone https://gitee.com/tswsoft/searxng.git searxng-src
cd searxng-src

echo "==> 3/5 配置 Python 虚拟环境并安装依赖"
python3 -m venv ~/searxng/venv
source ~/searxng/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# 注意：这里删除了 pip install -e . 避免 Python 3.13 的构建报错

echo "==> 4/5 生成配置文件并强制开启 JSON 接口"
mkdir -p ~/searxng/config
# 复制默认配置，并利用 Python 脚本自动修改 YAML
python3 -c "
import yaml
import secrets
with open('searx/settings.yml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
if 'search' not in data: data['search'] = {}
# 开启 JSON 格式
data['search']['formats'] = ['html', 'json']
# 生成随机密钥防止报错
data['server']['secret_key'] = secrets.token_hex(32)
data['server']['port'] = 8080
with open('/home/xingziang/searxng/config/settings.yml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, allow_unicode=True)
"

echo "==> 5/5 启动 SearXNG 并验证"
# 将配置路径写入环境变量并后台启动
export SEARXNG_SETTINGS_PATH=~/searxng/config/settings.yml
nohup python searx/webapp.py > ~/searxng/searxng.log 2>&1 &
echo "等待 3 秒让服务启动..."
sleep 3

echo "验证接口响应："
curl -s "http://127.0.0.1:8080/search?q=test&format=json" | head -c 300
echo ""
echo "=== 部署完成！如果上面输出了 JSON 数据，就说明成功了。 ==="
