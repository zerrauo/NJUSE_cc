"""工具本地执行：读写文件、执行 shell 命令。所有路径被限制在工作区内。

设计要点：
- 路径解析后必须仍位于工作区内，防止模型读写无关文件；
- 所有工具输出都有长度上限，避免单次输出撑爆上下文；
- 工具失败不抛异常中断循环，而是返回错误文本，让模型自行修正。
"""
import re
import subprocess
from pathlib import Path
from typing import Optional

MAX_OUTPUT_CHARS = 6000
DEFAULT_COMMAND_TIMEOUT = 120
MAX_LIST_ENTRIES = 200

IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".idea", ".vscode"}

# 危险命令黑名单：不可逆或影响共享状态的操作，执行前需要用户确认
DANGEROUS_PATTERNS = [
    r"\brm\s+-[a-z]*r[a-z]*\s+",  # rm -r / rm -rf 等递归删除
    r"\bgit\s+reset\s+--hard",  # 丢弃未提交修改
    r"\bgit\s+push\s+[^|&;]*(-f|--force)",  # 强推覆盖远端
    r"\bgit\s+clean\s+-[a-z]*f",  # 删除未跟踪文件
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\b(shutdown|reboot|halt|poweroff)\b",
    r":\(\)\s*\{",  # fork bomb
]


class ToolExecutor:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        # 危险命令确认回调，由上层注入（亮点功能，未注入时直接执行）
        self.confirm_command = None

    def _resolve(self, path: str) -> Path:
        p = (self.workspace / path).resolve()
        if not p.is_relative_to(self.workspace):
            raise ValueError(f"路径越出工作区，已拒绝: {path}")
        return p

    @staticmethod
    def is_dangerous(command: str) -> bool:
        return any(re.search(pat, command) for pat in DANGEROUS_PATTERNS)

    @staticmethod
    def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
        if len(text) <= limit:
            return text
        half = limit // 2
        return text[:half] + f"\n...[中间省略 {len(text) - limit} 字符]...\n" + text[-half:]

    # ---- 文件工具 ----

    def read_file(self, path: str, offset: int = 1, limit: Optional[int] = None) -> str:
        p = self._resolve(path)
        if not p.exists():
            return f"错误：文件不存在 {path}"
        if p.is_dir():
            return f"错误：{path} 是目录，请用 list_files 查看"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if limit is None:
            limit = len(lines)
        start = max(1, offset)
        end = min(len(lines), start + limit - 1)
        if start > len(lines):
            return f"错误：起始行 {start} 超出文件总行数 {len(lines)}"
        numbered = "\n".join(f"{i:5d} | {lines[i - 1]}" for i in range(start, end + 1))
        return f"{path}（第 {start}-{end} 行 / 共 {len(lines)} 行）\n{numbered}"

    def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入 {path}（{len(content)} 字符）"

    def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        """精确字符串替换：old_string 必须与文件内容唯一匹配，否则拒绝修改。

        要求唯一匹配可以避免模型凭记忆"盲改"，迫使它先 read_file 确认现状。
        """
        p = self._resolve(path)
        if not p.exists():
            return f"错误：文件不存在 {path}"
        text = p.read_text(encoding="utf-8")
        count = text.count(old_string)
        if count == 0:
            return "错误：未找到与 old_string 完全匹配的片段。请先 read_file 确认当前内容。"
        if count > 1:
            return f"错误：old_string 匹配到 {count} 处，不唯一。请提供更长的上下文片段使其唯一。"
        p.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        return f"已替换 {path} 中 1 处匹配"

    def list_files(self, path: str = ".") -> str:
        base = self._resolve(path)
        if not base.exists():
            return f"错误：目录不存在 {path}"
        entries = []
        for p in sorted(base.rglob("*")):
            if any(part in IGNORED_DIRS for part in p.parts):
                continue
            rel = p.relative_to(self.workspace)
            entries.append(str(rel) + ("/" if p.is_dir() else ""))
        if len(entries) > MAX_LIST_ENTRIES:
            shown = entries[:MAX_LIST_ENTRIES]
            return "\n".join(shown) + f"\n...（还有 {len(entries) - MAX_LIST_ENTRIES} 项未显示，请缩小范围）"
        return "\n".join(entries) if entries else "（空目录）"

    # ---- 命令工具 ----

    def run_command(self, command: str, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> str:
        if self.is_dangerous(command) and self.confirm_command is not None:
            if not self.confirm_command(command):
                return "用户拒绝了该命令的执行。请改用更安全的替代方案。"
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"错误：命令执行超过 {timeout} 秒被终止"
        parts = [f"退出码: {proc.returncode}"]
        if proc.stdout:
            parts.append("标准输出:\n" + self._truncate(proc.stdout))
        if proc.stderr:
            parts.append("标准错误:\n" + self._truncate(proc.stderr))
        return "\n".join(parts)
