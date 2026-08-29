"""LLM 客户端封装：基于 openai SDK 对接任意 OpenAI 兼容网关（默认 DeepSeek）。"""
from openai import OpenAI

from .config import Config

# 后续会扩展为完整的 coding agent 系统提示词，现在先占位
SYSTEM_PROMPT = "你是一个编程助手，用简洁的中文回答问题。"


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    def chat(self, messages: list[dict]) -> str:
        resp = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            stream=False,
        )
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages: list[dict]):
        stream = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
