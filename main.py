"""编程智能体入口。

用法：
  python main.py "任务描述" [--workspace 目录] [--plan]
  python main.py [--workspace 目录] [--plan]   # 交互式逐条输入任务

--plan：先生成执行计划，用户确认后才开始执行工具。
"""
import argparse
import sys
from pathlib import Path
from typing import Optional

from agent.config import Config
from agent.executor import ToolExecutor
from agent.llm import LLMClient
from agent.loop import AgentLoop, generate_plan

BANNER = "Mini Coding Agent — 输入任务开始，exit 退出"


def print_event(turn: int, name: str, args: dict, result: str) -> None:
    if name == "__summary__":
        print(
            f"\n  [上下文压缩] 消息 {args.get('压缩前消息数')} 条 → "
            f"摘要 + 最近 {args.get('压缩后消息数')} 条"
        )
        return
    brief = {k: v for k, v in args.items() if k != "content"}
    print(f"\n  [第 {turn} 轮] {name}({brief})")
    # 工具结果首行用于观察进展，完整结果已回传给模型
    first_line = result.splitlines()[0] if result else ""
    print(f"    -> {first_line}")


def confirm_dangerous(command: str) -> bool:
    print(f"\n  [安全确认] 检测到危险命令: {command}")
    try:
        ans = input("  是否执行？(y/N) ")
    except (EOFError, KeyboardInterrupt):
        return False
    return ans.strip().lower() in {"y", "yes"}


def confirm_plan() -> bool:
    try:
        ans = input("\n计划如上，是否执行？(y/N) ")
    except (EOFError, KeyboardInterrupt):
        return False
    return ans.strip().lower() in {"y", "yes"}


def run_task(config: Config, llm: LLMClient, task: str, plan_mode: bool) -> None:
    executor = ToolExecutor(workspace=config.workspace)
    executor.confirm_command = confirm_dangerous
    loop = AgentLoop(config, llm, executor, on_event=print_event)
    print(f"任务: {task}\n工作区: {config.workspace}")
    plan: Optional[str] = None
    try:
        if plan_mode:
            print("\n[规划阶段] 正在生成执行计划...")
            plan = generate_plan(llm, task)
            print(f"\n{plan}")
            if not confirm_plan():
                print("[已取消]")
                return
        reply = loop.run(task, plan=plan)
    except KeyboardInterrupt:
        print("\n[已中断]")
        return
    except Exception as e:
        print(f"\n[执行失败] {type(e).__name__}: {e}")
        return
    print(f"\n{'=' * 60}\n{reply}")


def run_repl(config: Config, llm: LLMClient, plan_mode: bool) -> None:
    print(BANNER)
    while True:
        try:
            line = input("任务 > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip().lower() in {"exit", "quit"}:
            break
        if not line.strip():
            continue
        run_task(config, llm, line.strip(), plan_mode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mini Coding Agent")
    parser.add_argument("task", nargs="*", help="要完成的任务描述")
    parser.add_argument("--workspace", default=None, help="agent 的工作区目录，默认当前目录")
    parser.add_argument("--plan", action="store_true", help="先生成计划，用户确认后再执行")
    args = parser.parse_args()

    config = Config.from_env()
    if args.workspace:
        config.workspace = Path(args.workspace).resolve()

    llm = LLMClient(config)
    task = " ".join(args.task)
    if task:
        run_task(config, llm, task, args.plan)
    else:
        run_repl(config, llm, args.plan)


if __name__ == "__main__":
    main()
