import json
import os
from typing import Any, List, Dict

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

from .logs import console

# 加载环境变量
load_dotenv()


class LLMClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")  # Optional
        if not api_key:
            console.warning("OPENAI_API_KEY not found in environment variables.")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.large_model = os.getenv("LARGE_MODEL_NAME", "gpt-4o")
        self.small_model = os.getenv("SMALL_MODEL_NAME", "gpt-4o-mini")
        self.large_limit = int(os.getenv("LARGE_MODEL_CONTEXT_LIMIT", "128000"))

        # Initialize encoders
        try:
            self.large_encoding = tiktoken.encoding_for_model(self.large_model)
        except KeyError:
            self.large_encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        return len(self.large_encoding.encode(text))

    def get_context_limit(self) -> int:
        """Returns the context limit for the specified model type."""
        return self.large_limit

    def query(self, prompt: str | List[Dict[str, str]], model_type: str = "large") -> str:
        """普通文本查询"""
        model = self.large_model if model_type == "large" else self.small_model
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        try:
            response = self.client.chat.completions.create(
                model=model, messages=messages, temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            console.error(f"LLM Query Failed ({model}): {e}")
            raise

    def query_json(
        self, prompt: str | List[Dict[str, str]], model_type: str = "large"
    ) -> dict[str, Any]:
        """强制 JSON 输出查询"""
        model = self.large_model if model_type == "large" else self.small_model
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        try:
            response = self.client.chat.completions.create(
                model=model, messages=messages, temperature=0.5
            )
            content = response.choices[0].message.content.strip()

            # 清洗内容：移除 Markdown 代码块标记
            if content.startswith("```"):
                # 找到第一个换行符和最后一个 ``` 的位置
                first_newline = content.find("\n")
                last_backticks = content.rfind("```")
                if first_newline != -1 and last_backticks != -1:
                    content = content[first_newline + 1 : last_backticks].strip()

            return json.loads(content)
        except json.JSONDecodeError:
            console.error(f"Failed to decode JSON from LLM response: {response}")
            raise
        except Exception as e:
            console.error(f"LLM JSON Query Failed: {e}")
            raise
