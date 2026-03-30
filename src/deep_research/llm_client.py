import json
import os
import re
from typing import Any

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

from .log import log

# 加载环境变量
load_dotenv()


class LLMClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")  # Optional
        if not api_key:
            log.warning("OPENAI_API_KEY not found in environment variables.")

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

    def query(self, prompt: str | list[dict[str, str]], temperature: float = 0.7) -> str:
        """普通文本查询"""
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature
            )
            if not response.choices:
                log.error(f"LLM returned no choices. Full response: {response}")
                raise ValueError("LLM returned no choices")

            content = response.choices[0].message.content
            if content is None:
                log.error(f"LLM returned None for content. Full response: {response}")
                raise ValueError("LLM returned empty content")

            return content.strip()
        except Exception as e:
            log.error(f"LLM Query Failed ({self.model}): {e}")
            raise

    def query_json(self, prompt: str | list[dict[str, str]]) -> dict[str, Any]:
        """强制 JSON 输出查询"""
        raw_content = ""
        try:
            raw_content = self.query(prompt, temperature=0.5)
            content = raw_content

            # 1. 清洗内容：移除 Markdown 代码块标记
            content = content.strip()
            if content.startswith("```"):
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)

            # 2. 提取主体内容：尝试找到第一个 { 和最后一个 } 之间的内容
            match = re.search(r"(\{.*\})", content, re.DOTALL)
            if match:
                content = match.group(1)
            else:
                # 实在没有 JSON 结构，包装成一个通用的字典，避免直接报错
                if content.strip():
                    return {"thought": content, "action": "none", "parameters": {}}

            try:
                # 尝试标准解析
                return json.loads(content)
            except json.JSONDecodeError:
                try:
                    # 尝试非严格解析（允许换行符等控制字符）
                    return json.loads(content, strict=False)
                except json.JSONDecodeError as e:
                    # 尝试处理未转义的引号
                    def escape_internal_quotes(m):
                        prefix = m.group(1)  # "key": "
                        value = m.group(2)  # value content
                        suffix = m.group(3)  # "
                        # 转义非转义的引号
                        fixed_value = re.sub(r'(?<!\\)"', r"\"", value)
                        return f"{prefix}{fixed_value}{suffix}"

                    # 匹配 "key": "value" 结构，并转义 value 中的内部引号
                    # 注意：后缀需要是结构化字符（逗号、右大括号或右方括号）
                    fixed_content = re.sub(
                        r'("[^"]*"\s*:\s*")(.*?)("(?=\s*[,}\]]))',
                        escape_internal_quotes,
                        content,
                        flags=re.DOTALL,
                    )
                    try:
                        return json.loads(fixed_content, strict=False)
                    except json.JSONDecodeError:
                        # 如果还是不行，记录错误并抛出原始异常
                        log.error(
                            f"Failed to decode JSON even after repair. Raw: {repr(raw_content)}"
                        )
                        raise e
        except Exception as e:
            log.error(f"LLM JSON Query Failed: {e}")
            raise
