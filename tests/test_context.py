"""上下文管理单元测试：token 估算与压缩切口的合法性。"""
from agent.config import Config
from agent.context import ContextManager, estimate_tokens


class FailingLLM:
    def summarize(self, msgs):
        raise RuntimeError("模拟摘要失败")


class OkLLM:
    def summarize(self, msgs):
        return "（摘要）"


def make_cfg(**kw):
    defaults = dict(api_key="x", max_context_tokens=1, keep_recent=3)
    defaults.update(kw)
    return Config(**defaults)


def assert_valid_structure(messages):
    for i, m in enumerate(messages):
        if m["role"] == "tool":
            # tool 消息必须紧跟请求它的 assistant(tool_calls)
            assert i > 0 and messages[i - 1]["role"] == "assistant"
    assert messages[0]["role"] == "system"
    return [m["role"] for m in messages]


def test_estimate_tokens():
    assert estimate_tokens("hello world") == 2  # 11 字符 // 4
    assert estimate_tokens("你好世界") == 4  # CJK 每字 1 token
    assert estimate_tokens("") == 0


def test_estimate_messages_counts_toolcall_arguments():
    from agent.context import estimate_messages

    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"arguments": "x" * 400}}  # 100 tokens
        ]},
        {"role": "tool", "content": "short"},
    ]
    # 若漏算 tool_calls 参数，估算值会明显偏小
    assert estimate_messages(msgs) >= 100


def test_compress_cut_on_assistant_with_toolcalls():
    cm = ContextManager(make_cfg(keep_recent=3))
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": "r1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "2"}]},
        {"role": "tool", "tool_call_id": "2", "content": "r2"},
        {"role": "assistant", "content": "doing"},
    ]
    out = cm._compress(msgs, FailingLLM())
    roles = assert_valid_structure(out)
    assert roles[-1] == "assistant" and out[-1]["content"] == "doing"


def test_compress_cut_shifts_past_tool_message():
    cm = ContextManager(make_cfg(keep_recent=2))
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": "r1"},
        {"role": "assistant", "content": "done"},
    ]
    out = cm._compress(msgs, OkLLM())
    roles = assert_valid_structure(out)
    assert roles == ["system", "user", "assistant"]
    assert "（摘要）" in out[1]["content"]


def test_compress_noop_when_under_limit():
    cm = ContextManager(make_cfg(max_context_tokens=10_000, keep_recent=3))
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert cm.prepare(msgs, OkLLM()) is msgs
