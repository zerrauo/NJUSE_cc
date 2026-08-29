"""上下文管理：token 估算与超限时的自动摘要压缩。

策略：每次调用模型前估算消息总 token 数，超过阈值（默认 75% 上下文窗口）时，
把最旧的一段历史交给模型压缩成"进度摘要"，替换原消息；最近若干条消息原样保留，
保证模型对当前局面的记忆不丢失。

压缩失败的兜底：直接丢弃旧消息（只留摘要请求失败前的结构），agent 依然能继续，
只是会丢失部分历史细节。
"""
from typing import List

from .config import Config

SUMMARY_INSTRUCTION = """请把以下 agent 工作历史压缩成简洁的进度摘要（中文，尽量精简），必须保留：
1. 用户最初的任务要求；
2. 已完成的具体修改（文件名 + 改了什么）；
3. 验证/测试的结果；
4. 尚未完成的事项和已知问题。
只输出摘要本身。"""


def estimate_tokens(text: str) -> int:
    """粗略估算：CJK 字符约 1 token，其余约 4 字符 1 token。"""
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return cjk + (len(text) - cjk) // 4


def estimate_messages(messages: List[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content") or ""
        total += estimate_tokens(content) + 4  # 每条消息的固定开销
        # tool_calls 的参数（如 write_file 的完整文件内容）同样计入
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            total += estimate_tokens(str(fn.get("arguments", ""))) + 8
    return total


class ContextManager:
    def __init__(self, config: Config):
        self.max_tokens = config.max_context_tokens
        self.keep_recent = config.keep_recent

    def prepare(self, messages: List[dict], llm) -> List[dict]:
        """在调用模型前检查并压缩。返回（可能已压缩的）消息列表。"""
        if estimate_messages(messages) <= self.max_tokens:
            return messages
        return self._compress(messages, llm)

    def _compress(self, messages: List[dict], llm) -> List[dict]:
        cut = max(1, len(messages) - self.keep_recent)
        # tool 消息必须紧跟其 assistant(tool_calls) 消息，切口不能落在 tool 消息上
        while cut < len(messages) and messages[cut].get("role") == "tool":
            cut += 1
        if cut <= 1:
            return messages  # 没有可压缩的历史
        middle = messages[1:cut]
        tail = messages[cut:]

        try:
            summary = llm.summarize(middle)
        except Exception:
            summary = None
        if summary:
            summary_msg = {
                "role": "user",
                "content": f"（以下是更早工作历史的摘要，供你继续任务时参考）\n{summary}",
            }
            return [messages[0], summary_msg] + tail
        return [messages[0]] + tail
