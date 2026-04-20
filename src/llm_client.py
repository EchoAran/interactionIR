import os
import json
from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model_name = os.getenv("LLM_MODEL_NAME", "gpt-4o")
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    def generate_structured(self, system_prompt: str, user_prompt: str, response_model: type[BaseModel]) -> BaseModel:
        """
        调用 LLM 返回结构化 Pydantic 模型
        由于部分兼容 API 不支持 response_format 的 json_schema，这里使用 JSON Mode 和 Prompt 工程。
        """
        messages = [
            {"role": "system", "content": system_prompt + "\n\nPlease respond strictly in JSON format matching the requested schema."},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        return response_model.model_validate_json(content)
    
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """
        生成纯文本
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7
        )
        
        return response.choices[0].message.content
