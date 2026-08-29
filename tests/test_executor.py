"""工具执行器测试：危险命令识别与确认流程。"""
from agent.executor import ToolExecutor


def test_is_dangerous_patterns():
    dangerous = [
        "rm -rf /tmp/cache",
        "rm -fr build",
        "rm -r old_dir",
        "git reset --hard HEAD~1",
        "git push origin main --force",
        "git push -f",
        "sudo make install",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=disk.img",
        "shutdown now",
        "reboot",
        ":(){ :|:& };:",
    ]
    for cmd in dangerous:
        assert ToolExecutor.is_dangerous(cmd), f"应识别为危险: {cmd}"

    safe = [
        "rm file.txt",
        "rm -f old.log",
        "echo hello",
        "python3 test.py",
        "git push origin main",
        "git status",
        "pytest tests/",
        "rmdir empty_dir",
    ]
    for cmd in safe:
        assert not ToolExecutor.is_dangerous(cmd), f"不应误报: {cmd}"


def test_dangerous_command_rejected_not_executed(tmp_path):
    ex = ToolExecutor(workspace=tmp_path)
    (tmp_path / "keep.txt").write_text("data")
    calls = []

    def confirm(cmd):
        calls.append(cmd)
        return False

    ex.confirm_command = confirm
    result = ex.run_command("rm -rf keep.txt")
    assert "拒绝" in result
    assert calls == ["rm -rf keep.txt"]
    assert (tmp_path / "keep.txt").exists(), "被拒绝的命令不应真正执行"


def test_dangerous_command_confirmed_executes(tmp_path):
    ex = ToolExecutor(workspace=tmp_path)
    (tmp_path / "gone.txt").write_text("data")
    ex.confirm_command = lambda cmd: True
    result = ex.run_command("rm -r gone.txt")
    assert "退出码: 0" in result
    assert not (tmp_path / "gone.txt").exists()


def test_safe_command_runs_without_confirmation(tmp_path):
    ex = ToolExecutor(workspace=tmp_path)
    ex.confirm_command = lambda cmd: (_ for _ in ()).throw(AssertionError("不应询问"))
    result = ex.run_command("echo ok")
    assert "ok" in result
