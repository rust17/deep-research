import os
import json
import logging
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")  # Optional
        if not api_key:
            logger.warning("OPENAI_API_KEY not found in environment variables.")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        # 默认模型，可配置
        self.model = os.getenv("MODEL_NAME", "gpt-4o")

    def query(self, prompt: str) -> str:
        """普通文本查询"""
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM Query Failed: {e}")
            raise

    def query_json(self, prompt: str) -> Dict[str, Any]:
        """强制 JSON 输出查询"""
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.5
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
            logger.error(f"Failed to decode JSON from LLM response: {content}")
            # 简单的重试或回退逻辑可以在这里添加，目前直接抛出
            raise
        except Exception as e:
            logger.error(f"LLM JSON Query Failed: {e}")
            raise
