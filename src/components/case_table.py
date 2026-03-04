"""
用例表格组件
支持展示、编辑、分页
"""

import streamlit as st
from typing import List
from src.models import TestCase, Priority, TestType
from src.utils.state import StateManager
from src.utils.validators import cell_text, escape_html
from src.config import get_type_tag_style


# 列宽配置
COL_WIDTHS = [0.35, 0.4, 1.2, 0.5, 0.45, 1.0, 0.9, 0.9, 1.0, 0.4, 0.35]
HEADERS = ["序号", "编号", "用例名称", "模块", "类型", "前置条件", "步骤", "测试数据", "预期结果", "优先级", "操作"]


class CaseTable:
    """用例表格组件"""
    
    TYPE_OPTIONS = [t.value for t in TestType]
    PRI_OPTIONS = [p.value for p in Priority]
    
    def __init__(self, cases: List[TestCase], start_idx: int):
        self.cases = cases
        self.start_idx = start_idx
        self.editing_id = StateManager.get_editing_id()
    
    def render(self):
        """渲染完整表格"""
        self._render_header()
        
        for row_idx, case in enumerate(self.cases):
            global_idx = self.start_idx + row_idx
            is_editing = self.editing_id == case.case_id
            
            if is_editing:
                self._render_editing_row(case, global_idx)
            else:
                self._render_display_row(case, global_idx)
    
    def _render_header(self):
        """表头"""
        cols = st.columns(COL_WIDTHS)
        for i, h in enumerate(HEADERS):
            cols[i].markdown(f"**{h}**")
    
    def _render_display_row(self, case: TestCase, global_idx: int):
        """展示模式行"""
        cols = st.columns(COL_WIDTHS)
        
        cols[0].write(global_idx + 1)
        cols[1].write(case.case_id)
        
        # 用例名称（占位符高亮）
        name = f"⚠️ {case.case_name}" if case.is_placeholder else case.case_name
        cols[2].write(name)
        
        cols[3].write(case.module)
        
        # 类型标签（带颜色）
        display_text, tag_cls, _ = get_type_tag_style(case.test_type.value)
        cols[4].markdown(
            f'<span class="type-tag {tag_cls}">{escape_html(display_text)}</span>',
            unsafe_allow_html=True
        )
        
        cols[5].write(cell_text(case.precondition))
        cols[6].write(cell_text(case.steps))
        cols[7].write(cell_text(case.test_data))
        cols[8].write(cell_text(case.expected))
        
        # 优先级标签
        pri_class = self._get_priority_tag_class(case.priority)
        cols[9].markdown(
            f'<span class="priority-tag {pri_class}">{case.priority.value}</span>',
            unsafe_allow_html=True
        )
        
        # 操作按钮
        with cols[10]:
            if st.button("编辑", key=f"edit_{case.case_id}"):
                StateManager.set_editing_id(case.case_id)
                st.rerun()
    
    def _render_editing_row(self, case: TestCase, global_idx: int):
        """编辑模式行"""
        cols = st.columns(COL_WIDTHS)
        
        cols[0].write(global_idx + 1)
        cols[1].write(case.case_id)
        
        # 编辑字段
        new_name = cols[2].text_input(
            "名称", value=case.case_name,
            key=f"e_name_{case.case_id}", label_visibility="collapsed"
        )
        new_module = cols[3].text_input(
            "模块", value=case.module,
            key=f"e_mod_{case.case_id}", label_visibility="collapsed"
        )
        
        # 类型选择
        type_idx = self.TYPE_OPTIONS.index(case.test_type.value) if case.test_type.value in self.TYPE_OPTIONS else 0
        new_type = cols[4].selectbox(
            "类型", self.TYPE_OPTIONS,
            index=type_idx,
            key=f"e_type_{case.case_id}", label_visibility="collapsed"
        )
        
        new_pre = cols[5].text_input(
            "前置", value=case.precondition,
            key=f"e_pre_{case.case_id}", label_visibility="collapsed"
        )
        new_steps = cols[6].text_area(
            "步骤", value=case.steps, height=50,
            key=f"e_step_{case.case_id}", label_visibility="collapsed"
        )
        new_data = cols[7].text_input(
            "数据", value=case.test_data,
            key=f"e_data_{case.case_id}", label_visibility="collapsed"
        )
        new_exp = cols[8].text_area(
            "预期", value=case.expected, height=50,
            key=f"e_exp_{case.case_id}", label_visibility="collapsed"
        )
        
        # 优先级选择
        pri_idx = self.PRI_OPTIONS.index(case.priority.value) if case.priority.value in self.PRI_OPTIONS else 1
        new_pri = cols[9].selectbox(
            "优先级", self.PRI_OPTIONS,
            index=pri_idx,
            key=f"e_pri_{case.case_id}", label_visibility="collapsed"
        )
        
        # 保存/取消
        with cols[10]:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✓", key=f"save_{case.case_id}", help="保存"):
                    success = StateManager.update_case(case.case_id, {
                        "case_name": new_name,
                        "module": new_module,
                        "test_type": new_type,
                        "precondition": new_pre,
                        "steps": new_steps,
                        "test_data": new_data,
                        "expected": new_exp,
                        "priority": new_pri,
                    })
                    if success:
                        StateManager.set_editing_id(None)
                        StateManager.set_saved_message()
                        st.rerun()
            with c2:
                if st.button("✗", key=f"cancel_{case.case_id}", help="取消"):
                    StateManager.set_editing_id(None)
                    st.rerun()
    
    def _get_type_tag_class(self, test_type: TestType) -> str:
        """获取类型标签CSS类"""
        mapping = {
            TestType.FUNCTIONAL: "tag-func",
            TestType.BOUNDARY: "tag-boundary",
            TestType.EXCEPTION: "tag-exception",
            TestType.API: "tag-api",
            TestType.UI: "tag-ui",
            TestType.PERFORMANCE: "tag-performance",
            TestType.SECURITY: "tag-security",
            TestType.COMPATIBILITY: "tag-compatibility",
            TestType.SMOKE: "tag-smoke",
            TestType.REGRESSION: "tag-regression",
        }
        return mapping.get(test_type, "tag-other")
    
    def _get_priority_tag_class(self, priority: Priority) -> str:
        """获取优先级标签CSS类"""
        mapping = {
            Priority.HIGH: "tag-pri-high",
            Priority.MEDIUM: "tag-pri-mid",
            Priority.LOW: "tag-pri-low",
        }
        return mapping.get(priority, "tag-pri-mid")