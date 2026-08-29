"""配置加载：环境变量优先，其次读取项目根目录的 .env（不入库）。"""
import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # 环境变量优先，不覆盖已存在的值
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Config:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_turns: int = 30
    workspace: Path = Path.cwd()

    @classmethod
    def from_env(cls) -> "Config":
        root = Path(__file__).resolve().parent.parent
        load_env_file(root / ".env")
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "未找到 DEEPSEEK_API_KEY。请复制 .env.example 为 .env 并填入 key，"
                "或通过环境变量提供。"
            )
        return cls(
            api_key=api_key,
            base_url=os.environ.get("AGENT_BASE_URL", cls.base_url),
            model=os.environ.get("AGENT_MODEL", cls.model),
        )
