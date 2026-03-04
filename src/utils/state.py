"""
Streamlit 状态管理封装
统一管理 session_state，避免魔法字符串
"""

from typing import List, Optional, Any, Callable
import streamlit as st
from src.models import TestCase, TestPoint


class StateKeys:
    """状态键名常量"""
    TEST_CASES = "test_cases"
    TEST_POINTS = "test_points"
    CURRENT_PAGE = "current_page"
    PER_PAGE = "per_page"
    EDITING_CASE_ID = "editing_case_id"
    INPUT_SOURCE = "input_source"
    REQUIREMENT_TEXT = "requirement_text"
    GENERATION_STATUS = "generation_status"  # idle/generating/completed/error
    LAST_IMAGE_NAME = "last_image_name"
    SAVED_MESSAGE = "saved_message"


class StateManager:
    """Streamlit 状态管理器"""
    
    @staticmethod
    def init():
        """初始化所有状态"""
        defaults = {
            StateKeys.TEST_CASES: [],
            StateKeys.TEST_POINTS: [],
            StateKeys.CURRENT_PAGE: 1,
            StateKeys.PER_PAGE: 15,
            StateKeys.EDITING_CASE_ID: None,
            StateKeys.INPUT_SOURCE: "text",
            StateKeys.REQUIREMENT_TEXT: "",
            StateKeys.GENERATION_STATUS: "idle",
            StateKeys.LAST_IMAGE_NAME: "",
            StateKeys.SAVED_MESSAGE: False,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    # ========== 用例相关 ==========
    @classmethod
    def get_cases(cls) -> List[TestCase]:
        """获取所有用例"""
        raw = st.session_state.get(StateKeys.TEST_CASES, [])
        cases = []
        for item in raw:
            if isinstance(item, dict):
                # 从字典恢复，需要提取 test_point_id
                item_copy = item.copy()
                # 处理 test_point 字段转换为 test_point_id
                if "test_point" in item_copy and "test_point_id" not in item_copy:
                    tp = item_copy.pop("test_point", "")
                    import re
                    m = re.search(r"测试点\s*(\d+)", str(tp))
                    if m:
                        item_copy["test_point_id"] = int(m.group(1))
                    else:
                        item_copy["test_point_id"] = 1
                try:
                    cases.append(TestCase.model_validate(item_copy))
                except Exception:
                    continue
            elif isinstance(item, TestCase):
                cases.append(item)
        return cases
    
    @classmethod
    def set_cases(cls, cases: List[TestCase]):
        """设置用例列表"""
        st.session_state[StateKeys.TEST_CASES] = [c.model_dump() for c in cases]
        # 重置到第一页
        st.session_state[StateKeys.CURRENT_PAGE] = 1
    
    @classmethod
    def update_case(cls, case_id: str, updates: dict):
        """更新单个用例"""
        cases = cls.get_cases()
        for i, case in enumerate(cases):
            if case.case_id == case_id:
                # 创建更新后的数据
                data = case.model_dump()
                
                # 特殊字段处理
                if "test_point" in updates:
                    # 将 "测试点N" 转换为 test_point_id
                    import re
                    m = re.search(r"测试点\s*(\d+)", str(updates["test_point"]))
                    if m:
                        data["test_point_id"] = int(m.group(1))
                    del updates["test_point"]
                
                data.update(updates)
                
                try:
                    cases[i] = TestCase.model_validate(data)
                except Exception as e:
                    st.error(f"更新用例失败: {e}")
                    return False
                break
        
        cls.set_cases(cases)
        return True
    
    @classmethod
    def append_cases(cls, cases: List[TestCase]):
        """追加用例"""
        existing = cls.get_cases()
        existing.extend(cases)
        cls.set_cases(existing)
    
    # ========== 测试点相关 ==========
    @classmethod
    def get_points(cls) -> List[TestPoint]:
        """获取测试点列表"""
        raw = st.session_state.get(StateKeys.TEST_POINTS, [])
        points = []
        for item in raw:
            if isinstance(item, dict):
                try:
                    points.append(TestPoint.model_validate(item))
                except Exception:
                    continue
            elif isinstance(item, TestPoint):
                points.append(item)
        return points
    
    @classmethod
    def set_points(cls, points: List[TestPoint]):
        """设置测试点列表"""
        st.session_state[StateKeys.TEST_POINTS] = [p.model_dump() for p in points]
    
    # ========== 分页相关 ==========
    @classmethod
    def get_current_page(cls) -> int:
        """获取当前页"""
        return st.session_state.get(StateKeys.CURRENT_PAGE, 1)
    
    @classmethod
    def set_current_page(cls, page: int):
        """设置当前页"""
        st.session_state[StateKeys.CURRENT_PAGE] = max(1, page)
        cls.set_editing_id(None)  # 切换页面时取消编辑
    
    @classmethod
    def get_per_page(cls) -> int:
        """获取每页条数"""
        from src.config import PER_PAGE_DEFAULT, PER_PAGE_OPTIONS
        per_page = st.session_state.get(StateKeys.PER_PAGE, PER_PAGE_DEFAULT)
        return per_page if per_page in PER_PAGE_OPTIONS else PER_PAGE_DEFAULT
    
    @classmethod
    def set_per_page(cls, per_page: int):
        """设置每页条数"""
        st.session_state[StateKeys.PER_PAGE] = per_page
        st.session_state[StateKeys.CURRENT_PAGE] = 1
        cls.set_editing_id(None)
    
    @classmethod
    def next_page(cls):
        """下一页"""
        current = cls.get_current_page()
        cls.set_current_page(current + 1)
    
    @classmethod
    def prev_page(cls):
        """上一页"""
        current = cls.get_current_page()
        cls.set_current_page(max(1, current - 1))
    
    @classmethod
    def goto_page(cls, page: int):
        """跳转到指定页"""
        cls.set_current_page(page)
    
    # ========== 编辑状态 ==========
    @classmethod
    def get_editing_id(cls) -> Optional[str]:
        """获取正在编辑的用例ID"""
        return st.session_state.get(StateKeys.EDITING_CASE_ID)
    
    @classmethod
    def set_editing_id(cls, case_id: Optional[str]):
        """设置正在编辑的用例ID"""
        st.session_state[StateKeys.EDITING_CASE_ID] = case_id
    
    @classmethod
    def is_editing(cls, case_id: str) -> bool:
        """判断是否正在编辑指定用例"""
        return cls.get_editing_id() == case_id
    
    # ========== 输入源相关 ==========
    @classmethod
    def get_input_source(cls) -> str:
        """获取输入源类型"""
        return st.session_state.get(StateKeys.INPUT_SOURCE, "text")
    
    @classmethod
    def set_input_source(cls, source: str):
        """设置输入源类型"""
        st.session_state[StateKeys.INPUT_SOURCE] = source
    
    @classmethod
    def get_requirement_text(cls) -> str:
        """获取需求文本"""
        return st.session_state.get(StateKeys.REQUIREMENT_TEXT, "")
    
    @classmethod
    def set_requirement_text(cls, text: str):
        """设置需求文本"""
        st.session_state[StateKeys.REQUIREMENT_TEXT] = text
    
    # ========== 生成状态 ==========
    @classmethod
    def get_generation_status(cls) -> str:
        """获取生成状态"""
        return st.session_state.get(StateKeys.GENERATION_STATUS, "idle")
    
    @classmethod
    def set_generation_status(cls, status: str):
        """设置生成状态"""
        st.session_state[StateKeys.GENERATION_STATUS] = status
    
    # ========== 图片上传状态 ==========
    @classmethod
    def get_last_image_name(cls) -> str:
        """获取最后上传的图片名"""
        return st.session_state.get(StateKeys.LAST_IMAGE_NAME, "")
    
    @classmethod
    def set_last_image_name(cls, name: str):
        """设置最后上传的图片名"""
        st.session_state[StateKeys.LAST_IMAGE_NAME] = name
    
    # ========== 提示消息 ==========
    @classmethod
    def get_and_clear_saved_message(cls) -> bool:
        """获取并清除保存消息标志"""
        if st.session_state.get(StateKeys.SAVED_MESSAGE, False):
            st.session_state[StateKeys.SAVED_MESSAGE] = False
            return True
        return False
    
    @classmethod
    def set_saved_message(cls):
        """设置保存消息标志"""
        st.session_state[StateKeys.SAVED_MESSAGE] = True