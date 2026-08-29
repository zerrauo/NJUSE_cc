"""主循环：调用模型 → 解析 tool_calls → 本地执行 → 回填结果，直到模型给出最终回复。

终止条件（按优先级）：
1. 模型不再发起工具调用 → 视为任务完成，返回最终回复；
2. 达到 max_turns → 追加"停止使用工具"的指令做最后一次调用，避免死循环烧钱；
3. 模型中途被工具错误卡住时不会终止循环——错误文本会回传给模型，由它自行修正。
"""
import json
from typing import Callable, Dict, List, Optional

from .config import Config
from .context import ContextManager
from .llm import LLMClient, SYSTEM_PROMPT
from .tools import TOOL_SPECS, build_registry

STUCK_WARN_THRESHOLD = 3


class AgentLoop:
    def __init__(self, config: Config, llm: LLMClient, executor, on_event: Optional[Callable] = None):
        self.config = config
        self.llm = llm
        self.executor = executor
        self.context = ContextManager(config)
        self.registry: Dict[str, Callable] = build_registry(executor)
        self.on_event = on_event or (lambda turn, name, args, result: None)
        self.history: List[dict] = []  # 完整对话记录，供上下文管理/调试使用

    def _emit(self, turn: int, name: str, args: dict, result: str) -> None:
        self.on_event(turn, name, args, result)

    def _execute(self, tool_call) -> str:
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            return "错误：工具参数不是合法 JSON，请重新生成参数。"
        handler = self.registry.get(name)
        if handler is None:
            return f"错误：未知工具 {name}，可用工具为 {sorted(self.registry)}"
        try:
            result = handler(**args)
        except TypeError as e:
            return f"错误：工具参数不合法（{e}），请检查参数名与类型后重试。"
        except Exception as e:
            return f"错误：工具执行异常（{type(e).__name__}: {e}），请分析原因并调整操作。"
        return str(result)

    def run(self, task: str) -> str:
        messages: List[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        last_call = None  # (工具名, 参数) 卡死检测
        repeat_count = 0
        for turn in range(1, self.config.max_turns + 1):
            before = len(messages)
            messages = self.context.prepare(messages, self.llm)
            if len(messages) < before:
                self._emit(
                    turn,
                    "__summary__",
                    {"压缩前消息数": before, "压缩后消息数": len(messages)},
                    "历史已压缩为摘要",
                )
            resp = self.llm.chat(messages, tools=TOOL_SPECS)
            msg = resp.choices[0].message
            if msg.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                    }
                )
                for tc in msg.tool_calls:
                    result = self._execute(tc)
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {"_raw": tc.function.arguments}
                    self._emit(turn, tc.function.name, args, result)
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result}
                    )
                    # 连续重复同一调用说明模型陷入死循环，插入警告打破循环
                    signature = (tc.function.name, json.dumps(args, sort_keys=True))
                    if signature == last_call:
                        repeat_count += 1
                        if repeat_count == STUCK_WARN_THRESHOLD:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": f"注意：你已连续 {repeat_count} 次调用相同的工具 "
                                    f"{tc.function.name} 且参数未变。请仔细分析工具返回的错误信息，"
                                    "调整策略（修改参数、换一种方式或检查你的假设），不要重复同样的调用。",
                                }
                            )
                    else:
                        last_call = signature
                        repeat_count = 1
                continue
            self.history = messages + [{"role": "assistant", "content": msg.content or ""}]
            return msg.content or ""

        # 达到最大轮数仍未结束：强制要求收尾
        messages.append(
            {
                "role": "user",
                "content": "已达到最大工具调用轮数。请立即停止使用工具，"
                "总结你目前完成了什么、哪些还未完成、以及未完成的原因。",
            }
        )
        resp = self.llm.chat(messages)
        final = resp.choices[0].message.content or ""
        self.history = messages + [{"role": "assistant", "content": final}]
        return final + "\n\n[已达到最大轮数，被强制收尾]"
