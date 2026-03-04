"""
AI服务封装
处理与LLM的交互
"""


import os
import re
import json
import time
import base64
from typing import List, Optional, Tuple, Any
from openai import OpenAI

from src.config import (
    get_qwen_api_key,
    get_qwen_model_list,
    API_REQUEST_TIMEOUT,
    STAGE1_MAX_CONTENT_CHARS,
    STAGE2_MAX_POINTS_PER_BATCH,
)


class AIServiceError(Exception):
    """AI服务异常"""
    pass


class APIKeyError(AIServiceError):
    """API密钥错误"""
    pass


class RateLimitError(AIServiceError):
    """速率限制错误"""
    pass


class AIService:
    """AI服务封装"""
    
    # Prompt模板
    PROMPT_STAGE1 = """你是一位资深测试架构师。请先深度分析以下需求文档，识别所有需要验证的测试点。

需求内容：
{content}

要求：
1. 逐条阅读需求，识别每个功能规则、状态变化、交互逻辑、数据计算、展示规则、异常分支
2. 输出完整的"测试点清单"，每个测试点一句话描述（如："验证温层标签在冷冻商品上的展示"）
3. 只输出测试点清单，不生成用例
4. 确保没有遗漏任何需求点，有多少列多少

输出格式（严格按此格式，便于解析）：
测试点1：XXXX
测试点2：XXXX
测试点3：XXXX
..."""

    PROMPT_STAGE2 = """基于以下测试点清单，为每个测试点生成对应的测试用例。

【测试点清单】
{test_points}

【绝对强制要求】
1. 每个测试点至少生成 1 条用例，复杂测试点可生成 2～3 条（正常流程+边界+异常）
2. 用例总数必须 ≥ 测试点数量（本批共 {N} 个测试点，至少生成 {N} 条用例）
3. 严禁合并、省略或跳过任何一个测试点
4. 复杂测试点（多状态/计算/异常）必须生成多条用例覆盖不同场景
5. test_point 字段必须填写对应序号（如 "测试点1"、"测试点2"）

【输出要求】
- 仅输出一个 JSON 数组，不要 markdown 代码块或其它说明
- 数组长度必须 ≥ {N}；若长度 < {N} 则不合格，需重新生成
- 建议生成数量：{N}～{N2} 条用例

格式示例：
[{{"case_id":"TC001","case_name":"标题","module":"购物车","test_point":"测试点1","test_type":"功能","precondition":"已登录","steps":"步骤1；步骤2","test_data":"具体数据","expected":"预期表现","priority":"高"}}]"""

    SYSTEM_STAGE2 = """你生成测试用例时必须：
1. 每个测试点至少 1 条对应用例，用例总数 ≥ 测试点数量，禁止少生成
2. test_point 填写 "测试点N"（N 为序号），步骤具体到 UI 元素，数据给具体值
3. 结果可断言，前置条件完整；复杂测试点生成 2～3 条
只输出有效的 JSON 数组，不要其他说明。"""

    IMAGE_PROMPT = """请根据图片内容自动判断类型（文本文档、UI 设计图、流程图、手写笔记等），并提取其中所有可用于需求分析的信息：
- 若是文档/截图：识别全部文字，保持格式与结构（标题、段落、列表、表格）。
- 若是 UI 设计图：提取页面模块、控件与文案、交互说明、业务规则与异常提示。
- 若是流程图：提取起止节点、步骤、分支与异常分支。
- 若是手写：尽量辨认字迹并保持段落结构，不确定处用 [?] 标记。
只输出提取后的结构化文本，不要解释图片类型或添加多余说明。"""

    def __init__(self):
        self.client = self._create_client()
        self.model_list = get_qwen_model_list()
    
    def _create_client(self) -> Optional[OpenAI]:
        """创建OpenAI客户端"""
        api_key = get_qwen_api_key()
        if not api_key:
            return None
        
        return OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=float(os.getenv("API_REQUEST_TIMEOUT", API_REQUEST_TIMEOUT)),
        )
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return self.client is not None
    
    def analyze_test_points(self, content: str, model_override: Optional[str] = None) -> str:
        """
        阶段1：分析需求，识别测试点
        """
        if not self.client:
            raise APIKeyError("未配置 QWEN_API_KEY")
        
        # 截断长文本
        content_limited = content[:STAGE1_MAX_CONTENT_CHARS]
        if len(content) > STAGE1_MAX_CONTENT_CHARS:
            content_limited += f"\n\n（需求已截断，仅前 {STAGE1_MAX_CONTENT_CHARS} 字参与分析。）"
        
        prompt = self.PROMPT_STAGE1.format(content=content_limited)
        
        messages = [
            {"role": "system", "content": "你只输出测试点清单，格式为 测试点N：描述，不要其他内容。"},
            {"role": "user", "content": prompt},
        ]
        
        # 如果指定了模型，使用单模型请求
        if model_override:
            response, _ = self._chat_single(model_override, messages, temperature=0.3)
        else:
            response, _ = self._chat_with_fallback(messages, temperature=0.3)
        
        return response.choices[0].message.content or ""
    
    def generate_cases_for_batch(
        self, 
        test_points: List[str], 
        model_override: Optional[str] = None
    ) -> List[dict]:
        """
        阶段2：为一批测试点生成用例
        """
        if not self.client:
            raise APIKeyError("未配置 QWEN_API_KEY")
        
        batch_text = "\n".join(f"测试点{i+1}：{p}" for i, p in enumerate(test_points))
        n = len(test_points)
        
        prompt = self.PROMPT_STAGE2.format(
            test_points=batch_text,
            N=n,
            N2=n * 2
        )
        
        messages = [
            {"role": "system", "content": self.SYSTEM_STAGE2},
            {"role": "user", "content": prompt},
        ]
        
        if model_override:
            response, _ = self._chat_single(model_override, messages, temperature=0.4)
        else:
            response, _ = self._chat_with_fallback(messages, temperature=0.4)
        
        text = response.choices[0].message.content or ""
        return self._parse_json_response(text)
    
    def recognize_image(self, image_bytes: bytes, mime_type: str) -> str:
        """
        图片识别（多模态）
        """
        if not self.client:
            raise APIKeyError("未配置 QWEN_API_KEY")
        
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        messages = [
            {"role": "system", "content": "你是一个专业的需求文档识别助手，擅长从图片中提取结构化信息。"},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                    {"type": "text", "text": self.IMAGE_PROMPT},
                ],
            },
        ]
        
        try:
            response = self.client.chat.completions.create(
                model="qwen-vl-max",
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
                timeout=60,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            err = str(e).lower()
            if "timeout" in err:
                raise AIServiceError("图片识别超时，请尝试压缩图片或稍后重试。")
            if "rate limit" in err or "429" in err:
                raise RateLimitError("视觉模型调用频繁，请稍后重试。")
            raise AIServiceError(f"图片识别失败：{e}")
    
    def _chat_single(
        self,
        model: str,
        messages: list,
        temperature: float = 0.3,
        **kwargs
    ) -> Tuple[Any, str]:
        """单次请求，指定模型"""
        resp = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        return resp, model
    
    def _chat_with_fallback(
        self,
        messages: list,
        temperature: float = 0.3,
        **kwargs
    ) -> Tuple[Any, str]:
        """
        带 fallback 的请求，一个模型失败自动尝试下一个
        """
        last_err = None
        
        for model in self.model_list:
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    **kwargs,
                )
                return resp, model
            except Exception as e:
                last_err = e
                if self._is_api_key_error(e):
                    raise APIKeyError("API 密钥无效（401）")
                if self._is_rate_limit_error(e):
                    continue  # 尝试下一个模型
                raise
        
        if last_err:
            raise last_err
        raise AIServiceError("未配置可用模型列表")
    
    @staticmethod
    def _is_api_key_error(exc: Exception) -> bool:
        """判断是否为API密钥错误"""
        msg = str(exc).lower()
        return "401" in msg or "invalid_api_key" in msg or "incorrect api key" in msg
    
    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        """判断是否为速率限制错误"""
        msg = str(exc).lower()
        if "429" in msg:
            return True
        for k in ("quota", "rate limit", "insufficient", "limit exceeded", "额度", "throttl"):
            if k in msg:
                return True
        return False
    
    @staticmethod
    def _parse_json_response(text: str) -> List[dict]:
        """解析LLM返回的JSON"""
        if not text or not text.strip():
            return []
        
        text = text.strip()
        
        # 去除markdown代码块
        if text.startswith("```"):
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if m:
                text = m.group(1).strip()
        
        try:
            # 清理尾部逗号
            cleaned = text.replace(",]", "]").replace(",}", "}")
            data = json.loads(cleaned)
            
            if isinstance(data, list):
                return [c for c in data if isinstance(c, dict)]
            if isinstance(data, dict):
                if "test_cases" in data:
                    return [c for c in data["test_cases"] if isinstance(c, dict)]
                return [data]
        except json.JSONDecodeError:
            pass
        
        return []