"""
数据模型定义
使用 Pydantic 进行强类型校验
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator


class Priority(str, Enum):
    """优先级枚举"""
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class TestType(str, Enum):
    """测试类型枚举"""
    FUNCTIONAL = "功能"
    BOUNDARY = "边界"
    EXCEPTION = "异常"
    COMPATIBILITY = "兼容性"
    PERFORMANCE = "性能"
    SECURITY = "安全"
    UI = "UI"
    API = "接口"
    SMOKE = "冒烟"
    REGRESSION = "回归"


class TestPoint(BaseModel):
    """测试点模型"""
    id: int = Field(..., description="测试点序号")
    title: str = Field(..., min_length=1, description="测试点描述")
    source_text: str = Field(default="", description="来源原文片段")
    
    class Config:
        frozen = True  # 不可变，线程安全
    
    def __str__(self) -> str:
        return f"测试点{self.id}：{self.title[:50]}"


class TestCase(BaseModel):
    """测试用例模型"""
    case_id: str = Field(..., pattern=r"TC\d{3}", description="用例编号")
    case_name: str = Field(..., min_length=1, max_length=200, description="用例名称")
    module: str = Field(default="未分类", description="所属模块")
    test_type: TestType = Field(default=TestType.FUNCTIONAL, description="测试类型")
    test_point_id: int = Field(..., description="关联测试点ID")
    precondition: str = Field(default="", description="前置条件")
    steps: str = Field(default="", description="测试步骤")
    test_data: str = Field(default="", description="测试数据")
    expected: str = Field(..., min_length=1, description="预期结果")
    priority: Priority = Field(default=Priority.MEDIUM, description="优先级")
    is_placeholder: bool = Field(default=False, description="是否为占位符")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    
    @field_validator('case_id')
    @classmethod
    def validate_case_id(cls, v: str) -> str:
        """确保用例编号格式正确"""
        if not v.startswith("TC"):
            raise ValueError("用例编号必须以TC开头")
        return v
    
    def to_dict(self) -> dict[str, Any]:
        """转换为Streamlit可用的字典格式"""
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "module": self.module,
            "test_type": self.test_type.value,
            "test_point": f"测试点{self.test_point_id}",
            "precondition": self.precondition,
            "steps": self.steps,
            "test_data": self.test_data,
            "expected": self.expected,
            "priority": self.priority.value,
            "_is_placeholder": self.is_placeholder,
        }
    
    @classmethod
    def from_llm_response(cls, data: dict, point_id: int) -> "TestCase":
        """从LLM响应解析创建用例"""
        # 解析测试类型
        test_type_val = data.get("test_type", "功能")
        test_type = cls._parse_test_type(test_type_val)
        
        # 解析优先级
        priority_val = data.get("priority", "中")
        priority = cls._parse_priority(priority_val)
        
        # 获取模块（兼容多种字段名）
        module = data.get("module") or data.get("所属需求模块") or "未分类"
        
        return cls(
            case_id=data.get("case_id", ""),
            case_name=data.get("case_name", ""),
            module=module,
            test_type=test_type,
            test_point_id=point_id,
            precondition=data.get("precondition", ""),
            steps=data.get("steps", ""),
            test_data=data.get("test_data", ""),
            expected=data.get("expected", ""),
            priority=priority,
        )
    
    @staticmethod
    def _parse_test_type(val: str) -> TestType:
        """解析测试类型字符串"""
        if not val:
            return TestType.FUNCTIONAL
        
        val = str(val).strip().lower()
        mapping = {
            "功能": TestType.FUNCTIONAL, "功能测试": TestType.FUNCTIONAL,
            "边界": TestType.BOUNDARY, "边界值": TestType.BOUNDARY, "边界测试": TestType.BOUNDARY,
            "异常": TestType.EXCEPTION, "异常测试": TestType.EXCEPTION,
            "兼容性": TestType.COMPATIBILITY, "兼容": TestType.COMPATIBILITY,
            "性能": TestType.PERFORMANCE, "性能测试": TestType.PERFORMANCE,
            "安全": TestType.SECURITY, "安全测试": TestType.SECURITY,
            "ui": TestType.UI, "ui测试": TestType.UI, "界面": TestType.UI, "界面测试": TestType.UI,
            "接口": TestType.API, "api": TestType.API, "接口测试": TestType.API, "api测试": TestType.API,
            "冒烟": TestType.SMOKE, "冒烟测试": TestType.SMOKE,
            "回归": TestType.REGRESSION, "回归测试": TestType.REGRESSION,
        }
        return mapping.get(val, TestType.FUNCTIONAL)
    
    @staticmethod
    def _parse_priority(val: str) -> Priority:
        """解析优先级字符串"""
        if not val:
            return Priority.MEDIUM
        
        val = str(val).strip()
        mapping = {
            "高": Priority.HIGH, "high": Priority.HIGH,
            "中": Priority.MEDIUM, "medium": Priority.MEDIUM,
            "低": Priority.LOW, "low": Priority.LOW,
        }
        return mapping.get(val, Priority.MEDIUM)
    
    def update_field(self, field: str, value: Any) -> "TestCase":
        """创建更新后的新实例（不可变模式）"""
        data = self.model_dump()
        if field == "test_type":
            value = self._parse_test_type(value)
        elif field == "priority":
            value = self._parse_priority(value)
        data[field] = value
        return TestCase.model_validate(data)


class GenerationProgress(BaseModel):
    """生成进度事件"""
    type: str = Field(..., description="事件类型：progress/complete/error")
    current: int = Field(default=0, description="当前进度")
    total: int = Field(default=0, description="总数量")
    message: str = Field(default="", description="进度消息")
    cases: List[TestCase] = Field(default_factory=list, description="生成的用例")
    
    @classmethod
    def progress(cls, current: int, total: int, message: str = "", cases: List[TestCase] = None):
        return cls(type="progress", current=current, total=total, message=message, cases=cases or [])
    
    @classmethod
    def complete(cls, total: int, cases: List[TestCase]):
        return cls(type="complete", current=total, total=total, message="完成", cases=cases)
    
    @classmethod
    def error(cls, message: str):
        return cls(type="error", message=message, cases=[])


class InputSource(str, Enum):
    """输入来源类型"""
    TEXT = "text"
    DOCUMENT = "document"
    URL = "url"
    IMAGE = "image"