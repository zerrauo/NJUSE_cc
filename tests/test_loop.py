"""主循环集成测试：用脚本化 LLM 验证压缩触发、卡死检测、最大轮数收尾、错误回传。"""
import json
from types import SimpleNamespace

from agent.config import Config
from agent.executor import ToolExecutor
from agent.loop import AgentLoop


def make_resp(content=None, tool_calls=None):
    tcs = []
    for name, args in tool_calls or []:
        raw = json.dumps(args, ensure_ascii=False)
        tcs.append(
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name=name, arguments=raw),
                model_dump=lambda n=name, a=args: {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)},
                },
            )
        )
    msg = SimpleNamespace(content=content or "", tool_calls=tcs or None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def tool_resp(name, args):
    return make_resp(tool_calls=[(name, args)])


class ScriptedLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []  # 每次 chat 收到的 messages，供断言
        self.summarize_calls = 0

    def chat(self, messages, tools=None):
        self.calls.append((messages, tools))
        if not self.script:
            return make_resp(content="（默认最终回答）")
        item = self.script.pop(0)
        return item(messages, tools) if callable(item) else item

    def summarize(self, messages):
        self.summarize_calls += 1
        return "（历史摘要）"


def make_agent(tmp_path, llm, **kw):
    defaults = dict(api_key="x", max_turns=10, max_context_tokens=100_000, keep_recent=4)
    defaults.update(kw)
    config = Config(**defaults)
    executor = ToolExecutor(workspace=tmp_path)
    return AgentLoop(config, llm, executor)


def assert_no_orphan_tool(messages):
    for i, m in enumerate(messages):
        if m.get("role") == "tool":
            assert i > 0 and messages[i - 1].get("role") == "assistant", (
                f"孤立 tool 消息：第 {i} 条"
            )


def test_compression_fires_mid_loop(tmp_path):
    # 8 轮写文件把消息数撑大，阈值很低 → 中途触发摘要压缩
    script = [tool_resp("write_file", {"path": f"f{i}.txt", "content": "x" * 80}) for i in range(8)]
    script.append(make_resp(content="任务完成"))
    llm = ScriptedLLM(script)
    agent = make_agent(tmp_path, llm, max_turns=20, max_context_tokens=200, keep_recent=4)

    reply = agent.run("创建多个文件")

    assert reply == "任务完成"
    assert llm.summarize_calls >= 1
    for messages, _ in llm.calls:
        assert_no_orphan_tool(messages)
    # 至少有一次调用时消息被压缩过（比全量历史短）
    assert any(len(msgs) < 10 for msgs, _ in llm.calls)


def test_stuck_loop_gets_warning(tmp_path):
    script = [tool_resp("run_command", {"command": "ls"}) for _ in range(3)]
    script.append(make_resp(content="好的，我换个思路"))
    llm = ScriptedLLM(script)
    agent = make_agent(tmp_path, llm)

    reply = agent.run("列出文件")

    assert "换个思路" in reply
    warned = [
        m
        for msgs, _ in llm.calls
        for m in msgs
        if m.get("role") == "user" and "连续" in (m.get("content") or "")
    ]
    assert warned, "连续重复调用 3 次后应插入警告消息"


def test_max_turns_forced_finish(tmp_path):
    script = [tool_resp("run_command", {"command": "ls"}) for _ in range(3)]
    script.append(make_resp(content="只能总结到这里"))
    llm = ScriptedLLM(script)
    agent = make_agent(tmp_path, llm, max_turns=3)

    reply = agent.run("不断执行命令")

    assert "已达到最大轮数" in reply
    assert "只能总结到这里" in reply
    # 收尾调用不应携带工具
    assert llm.calls[-1][1] is None
    # 收尾前插入了"停止使用工具"的指令
    assert any("停止使用工具" in (m.get("content") or "") for m in llm.calls[-1][0])


def test_bad_json_args_fed_back_to_model(tmp_path):
    agent = make_agent(tmp_path, ScriptedLLM([]))
    bad = SimpleNamespace(
        id="call_x",
        function=SimpleNamespace(name="read_file", arguments="{not json"),
    )
    result = agent._execute(bad)
    assert "不是合法 JSON" in result


def test_unknown_tool_fed_back_to_model(tmp_path):
    agent = make_agent(tmp_path, ScriptedLLM([]))
    unknown = SimpleNamespace(
        id="call_x",
        function=SimpleNamespace(name="delete_everything", arguments="{}"),
    )
    result = agent._execute(unknown)
    assert "未知工具" in result


def test_tool_runtime_error_fed_back_to_model(tmp_path):
    agent = make_agent(tmp_path, ScriptedLLM([]))
    bad_path = SimpleNamespace(
        id="call_x",
        function=SimpleNamespace(name="read_file", arguments=json.dumps({"path": "../../etc/passwd"})),
    )
    result = agent._execute(bad_path)
    assert "越出工作区" in result
