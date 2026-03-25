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
        self.model = os.getenv("MODEL_NAME", "gpt-4o")
        self.limit = 262144

        # Initialize encoders
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        return len(self.encoding.encode(text))

    def get_context_limit(self) -> int:
        """Returns the context limit for the model."""
        return self.limit

    def query(self, prompt: str | List[Dict[str, str]], temperature: float = 0.7) -> str:
        """普通文本查询"""
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature
            )
            if not response.choices:
                console.error(f"LLM returned no choices. Full response: {response}")
                raise ValueError("LLM returned no choices")

            content = response.choices[0].message.content
            if content is None:
                console.error(f"LLM returned None for content. Full response: {response}")
                raise ValueError("LLM returned empty content")

            return content.strip()
        except Exception as e:
            console.error(f"LLM Query Failed ({self.model}): {e}")
            raise

    def query_json(self, prompt: str | List[Dict[str, str]]) -> dict[str, Any]:
        """强制 JSON 输出查询"""
        raw_content = ""
        try:
            raw_content = self.query(prompt, temperature=0.5)
            content = raw_content

            # 清洗内容：移除 Markdown 代码块标记
            if content.startswith("```"):
                # 找到第一个换行符和最后一个 ``` 的位置
                first_newline = content.find("\n")
                last_backticks = content.rfind("```")
                if first_newline != -1 and last_backticks != -1:
                    content = content[first_newline + 1 : last_backticks].strip()

            return json.loads(content)
        except json.JSONDecodeError:
            console.error(f"Failed to decode JSON. Raw response content: {repr(raw_content)}")
            raise
        except Exception as e:
            console.error(f"LLM JSON Query Failed: {e}")
            raise
