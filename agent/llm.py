"""LLM 客户端封装：基于 openai SDK 对接任意 OpenAI 兼容网关（默认 DeepSeek）。

错误处理策略：
- 网络错误、限流、超时、5xx 服务端错误 → 指数退避重试（这类错误重试大概率能成功）；
- 4xx 客户端错误（如参数错误）→ 立即抛出，重试无意义且浪费调用。
"""
import time
from typing import List, Optional

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from .config import Config

SYSTEM_PROMPT = """你是一个编程智能体（coding agent），工作区为当前目录。你可以使用工具读写文件、执行命令，自主完成用户的编程任务。

工作方式：
1. 先了解现状：用 list_files 查看目录结构，用 read_file 读取相关文件，必要时用 run_command 运行命令（如 git status、pytest）确认行为。
2. 修改文件前必须先 read_file；小范围修改用 edit_file 做精确替换（old_string 必须与文件内容完全一致，匹配多处时需提供更长上下文）；创建新文件用 write_file。
3. 每次修改后用 run_command 验证结果（运行测试、执行脚本等）。
4. 命令或工具报错时，仔细阅读错误信息，自行定位并修正，不要轻易放弃。
5. 任务完成后，总结你做了什么、如何验证的、结果如何。

约束：
- 只能访问工作区内的文件，路径均为相对工作区的路径。
- 用简洁的中文回复。"""

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # 2s, 4s, 8s 指数退避

_RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None):
        for attempt in range(MAX_RETRIES):
            try:
                return self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    tools=tools,
                )
            except _RETRYABLE as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                time.sleep(delay)
        raise RuntimeError("unreachable")

    def summarize(self, messages: List[dict]) -> str:
        """让模型压缩历史消息为进度摘要（不携带工具，避免摘要过程再触发工具）。"""
        from .context import SUMMARY_INSTRUCTION

        payload = [
            {"role": "system", "content": SUMMARY_INSTRUCTION},
            {
                "role": "user",
                "content": "\n\n".join(
                    f"[{m.get('role')}] {m.get('content') or '(工具调用)'}"
                    for m in messages
                    if m.get("role") != "system"
                ),
            },
        ]
        resp = self.chat(payload)
        return resp.choices[0].message.content or ""
