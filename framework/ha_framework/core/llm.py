# -*- coding: utf-8 -*-
"""
Hello-Agents

LLM统一调用接口
负责连接大语言模型，支持多提供商自动检测

支持：
- invoke(messages)  非流式调用，返回 str
- chat(messages)    兼容旧接口，等价于 invoke
- 多提供商自动检测：modelscope / openai / zhipu / ollama / vllm / auto
"""

from typing import List, Dict, Optional

from openai import OpenAI

from .config import Config


class HelloAgentsLLM:

    def __init__(
            self,
            model: Optional[str] = None,
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            provider: Optional[str] = "auto",
            temperature: Optional[float] = None,
            **kwargs
    ):
        """
        初始化模型客户端

        Args:
            model: 模型名称，默认取 .env 的 LLM_MODEL_ID
            api_key: API密钥，默认取 .env 的 LLM_API_KEY
            base_url: 服务地址，默认取 .env 的 LLM_BASE_URL
            provider: 服务商（openai/modelscope/zhipu/ollama/vllm/auto）
            temperature: 温度参数
        """
        # 提供商自动检测
        self.provider = provider or "auto"
        if self.provider == "auto":
            self.provider = self._auto_detect_provider(api_key, base_url)

        # 解析凭证
        self.api_key, self.base_url = self._resolve_credentials(
            api_key, base_url
        )
        if not self.api_key:
            raise ValueError(
                "未找到有效的API密钥，请在.env中配置LLM_API_KEY或对应提供商密钥"
            )

        self.model = model or Config.MODEL
        self.temperature = (
            temperature if temperature is not None else Config.TEMPERATURE
        )
        self.max_tokens = kwargs.get("max_tokens")
        self.timeout = kwargs.get("timeout", 60)

        # 创建 OpenAI 兼容客户端
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        # 兼容旧属性名
        self.client = self._client

    # ---------------- 提供商自动检测（文档 7.2.3） ----------------

    def _auto_detect_provider(self, api_key: Optional[str], base_url: Optional[str]) -> str:
        """
        自动检测LLM提供商，优先级：
        1. 特定提供商环境变量
        2. 根据 base_url 域名/端口判断
        3. 根据 API 密钥格式辅助判断
        4. 默认 auto
        """
        import os

        # 1. 特定提供商的环境变量（最高优先级）
        for env_name, provider_name in [
            ("MODELSCOPE_API_KEY", "modelscope"),
            ("OPENAI_API_KEY", "openai"),
            ("ZHIPU_API_KEY", "zhipu"),
            ("DEEPSEEK_API_KEY", "deepseek"),
        ]:
            if os.getenv(env_name):
                return provider_name

        # 2. 根据 base_url 判断
        actual_base_url = base_url or Config.BASE_URL
        url_lower = actual_base_url.lower()
        if "api-inference.modelscope.cn" in url_lower:
            return "modelscope"
        if "api.deepseek.com" in url_lower:
            return "deepseek"
        if "api.openai.com" in url_lower:
            return "openai"
        if "open.bigmodel.cn" in url_lower:
            return "zhipu"
        if "localhost" in url_lower or "127.0.0.1" in url_lower:
            if ":11434" in url_lower:
                return "ollama"
            if ":8000" in url_lower:
                return "vllm"
            return "local"

        # 3. 根据 API 密钥格式辅助判断
        actual_api_key = api_key or Config.LLM_API_KEY
        if actual_api_key and str(actual_api_key).startswith("ms-"):
            return "modelscope"

        # 4. 默认
        return "auto"

    def _resolve_credentials(self, api_key: Optional[str], base_url: Optional[str]):
        """
        根据provider解析API密钥和base_url（文档 7.2.3）
        """
        import os

        providers = {
            "openai": (
                "OPENAI_API_KEY",
                "https://api.openai.com/v1",
            ),
            "modelscope": (
                "MODELSCOPE_API_KEY",
                "https://api-inference.modelscope.cn/v1/",
            ),
            "zhipu": (
                "ZHIPU_API_KEY",
                "https://open.bigmodel.cn/api/paas/v4",
            ),
        }

        if self.provider in providers:
            env_key, default_url = providers[self.provider]
            resolved_api_key = api_key or os.getenv(env_key) or os.getenv("LLM_API_KEY")
            resolved_base_url = base_url or os.getenv("LLM_BASE_URL") or default_url
            return resolved_api_key, resolved_base_url

        # ollama / vllm / local / auto：使用通用 LLM_* 配置
        resolved_api_key = api_key or Config.LLM_API_KEY
        resolved_base_url = base_url or Config.BASE_URL
        return resolved_api_key, resolved_base_url

    # ---------------- 调用接口 ----------------

    def invoke(self, messages, temperature=None, **kwargs) -> str:
        """
        调用大模型（非流式），返回文本

        messages格式:
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."}
        ]
        """
        if temperature is None:
            temperature = self.temperature

        create_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.max_tokens is not None:
            create_kwargs["max_tokens"] = self.max_tokens
        create_kwargs.update(kwargs)

        response = self._client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content

    def chat(self, messages, temperature=None, **kwargs) -> str:
        """兼容旧接口：等价于 invoke"""
        return self.invoke(messages, temperature=temperature, **kwargs)

    def stream_invoke(self, messages, temperature=None, **kwargs):
        """
        流式调用大模型，返回 chunk 迭代器
        """
        if temperature is None:
            temperature = self.temperature

        create_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if self.max_tokens is not None:
            create_kwargs["max_tokens"] = self.max_tokens
        create_kwargs.update(kwargs)

        response = self._client.chat.completions.create(**create_kwargs)
        for chunk in response:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content or ""
            if content:
                yield content

    def think(self, messages, temperature=0, stream=True):
        """
        兼容文档旧示例的 think 方法（流式，返回完整文本或迭代器）
        """
        if stream:
            collected = []
            for chunk in self.stream_invoke(messages, temperature=temperature):
                collected.append(chunk)
            return "".join(collected)
        return self.invoke(messages, temperature=temperature)
