#!/bin/bash
# 视频演示①：bug 修复 + 新功能（含 --plan 计划模式）
# 每次运行都会重建全新的演示工作区，结果可复现。
set -euo pipefail
cd "$(dirname "$0")/.."

WS="$(mktemp -d /tmp/agent_demo_bugfix.XXXXXX)"
mkdir -p "$WS"

cat > "$WS/todo.py" <<'PYEOF'
"""简易待办应用。"""
import json
from pathlib import Path

DATA_FILE = Path(__file__).parent / "todos.json"


def load():
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text())


def save(todos):
    DATA_FILE.write_text(json.dumps(todos, indent=2))


def add(title):
    todos = load()
    todos.append({"id": len(todos), "title": title, "done": False})
    save(todos)


def list_all():
    for todo in load():
        print(todo["id"], todo["title"])


def main():
    import sys

    cmd = sys.argv[1]
    if cmd == "add":
        add(sys.argv[2])
    elif cmd == "list":
        list_all()
    else:
        print("未知命令")


if __name__ == "__main__":
    main()
PYEOF

cat > "$WS/test_todo.py" <<'PYEOF'
"""测试：应覆盖 add 与 list。"""
import todo


def test_add_and_list(capsys):
    todo.DATA_FILE = type(todo.DATA_FILE)("todos_test.json")
    if todo.DATA_FILE.exists():
        todo.DATA_FILE.unlink()
    todo.add("买菜")
    todo.add("写作业")
    todo.list_all()
    out = capsys.readouterr().out
    assert "买菜" in out and "写作业" in out


def test_id_starts_from_one():
    todo.DATA_FILE = type(todo.DATA_FILE)("todos_test2.json")
    if todo.DATA_FILE.exists():
        todo.DATA_FILE.unlink()
    todo.add("第一项")
    todo.add("第二项")
    todos = todo.load()
    assert todos[0]["id"] == 1 and todos[1]["id"] == 2
PYEOF

TASK="修复 todo.py 的 bug 并添加功能：1) 新增待办的 id 应该从 1 开始，现在是 0；2) 增加 mark 子命令：mark <id> 把该待办标记为完成；3) list 时完成项显示 [x] 未完成显示 [ ]；4) 为 mark 补充测试，运行全部测试确保通过"

echo "演示工作区: $WS"
exec .venv/bin/python main.py --plan "$TASK" --workspace "$WS"
