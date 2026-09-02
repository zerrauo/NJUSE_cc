"""工具定义：以 OpenAI function calling 格式声明工具，注册到本地执行器。"""
from typing import Callable, Dict, List

from .executor import ToolExecutor

# 只读模式下从工具列表中移除的写工具
READONLY_BLOCKED_TOOLS = {"write_file", "edit_file"}


def get_tool_specs(readonly: bool = False) -> List[dict]:
    """只读模式直接不把写工具发给模型——模型无从发起写操作，是硬保证。"""
    if not readonly:
        return TOOL_SPECS
    return [
        s for s in TOOL_SPECS if s["function"]["name"] not in READONLY_BLOCKED_TOOLS
    ]

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出工作区内目录结构（自动忽略 .git、venv 等）。用于了解项目现状。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区的目录路径，默认 '.'"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件，返回带行号的内容。修改文件前必须先读取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区的文件路径"},
                    "offset": {"type": "integer", "description": "起始行号，默认 1"},
                    "limit": {"type": "integer", "description": "最多读取的行数，默认全部"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建新文件或整体覆盖已有文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区的文件路径"},
                    "content": {"type": "string", "description": "完整文件内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "对文件做精确替换：old_string 必须在文件中唯一且完全一致（含空白字符）。"
                "若匹配不到或不唯一会报错，此时应扩大 old_string 的上下文或先 read_file。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区的文件路径"},
                    "old_string": {"type": "string", "description": "文件中要替换的原文片段"},
                    "new_string": {"type": "string", "description": "替换后的新内容"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "在工作区内执行 shell 命令，返回退出码、标准输出与标准错误（超长输出会被截断）。"
                "用于运行测试、查看 git 状态、验证修改效果等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 120"},
                },
                "required": ["command"],
            },
        },
    },
]


def build_registry(executor: ToolExecutor) -> Dict[str, Callable]:
    return {
        "list_files": executor.list_files,
        "read_file": executor.read_file,
        "write_file": executor.write_file,
        "edit_file": executor.edit_file,
        "run_command": executor.run_command,
    }
