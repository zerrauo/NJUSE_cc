#!/bin/bash
# 视频演示②：危险命令确认——agent 尝试 rm -rf 被拦截，
# 用户拒绝后模型自动改用更安全的删除方式。
set -euo pipefail
cd "$(dirname "$0")/.."

WS="$(mktemp -d /tmp/agent_demo_danger.XXXXXX)"
mkdir -p "$WS/dist"
echo "old build artifact" > "$WS/dist/old.js"
echo "keep me" > "$WS/keep.txt"

echo "演示工作区: ${WS}（含 dist/ 目录）"
echo "提示：出现安全确认时输入 n 拒绝，观察 agent 如何改用安全方案。"
exec .venv/bin/python main.py "删除 dist 目录及其全部内容，不要动其他文件" --workspace "$WS"
