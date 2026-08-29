"""编程智能体入口：REPL 交互。用法：python main.py [初始任务]"""
import sys

from agent.config import Config
from agent.llm import LLMClient, SYSTEM_PROMPT

BANNER = "Mini Coding Agent (DeepSeek) — 输入 exit 退出"


def run_repl(llm: LLMClient) -> None:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(BANNER)
    first = " ".join(sys.argv[1:])
    if first:
        reply = ""
        messages.append({"role": "user", "content": first})
        for piece in llm.chat_stream(messages):
            print(piece, end="", flush=True)
            reply += piece
        print()
        messages.append({"role": "assistant", "content": reply})
        return
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip().lower() in {"exit", "quit"}:
            break
        if not line.strip():
            continue
        messages.append({"role": "user", "content": line})
        try:
            for piece in llm.chat_stream(messages):
                print(piece, end="", flush=True)
            print()
        except Exception as e:  # 网络/API 错误不打断 REPL
            print(f"[错误] {e}")
            messages.pop()


def main() -> None:
    config = Config.from_env()
    llm = LLMClient(config)
    run_repl(llm)


if __name__ == "__main__":
    main()
