"""
分页组件 - 统一宽度紧凑样式
"""


import streamlit as st
from src.utils.state import StateManager
from src.config import PER_PAGE_OPTIONS


class Pagination:
    """分页组件 - 统一宽度紧凑样式"""
    
    def __init__(self, total: int, current_page: int, per_page: int):
        self.total = total
        self.current_page = current_page
        self.per_page = per_page
        self.max_page = max(1, (total + per_page - 1) // per_page)
    
    def render(self):
        """渲染分页栏 - 统一宽度"""
        if self.total <= 0:
            return
        
        st.markdown("---")
        
        # 统一宽度列
        left, right = st.columns([5, 5])
        
        with right:
            # 所有元素使用相同宽度
            # 共X条 | < | 1 | 2 | 3 | > | 15条/页 | 跳至 | __ | 页
            #  10列，每列宽度相同
            cols = st.columns([1, 1, 1, 1, 1, 1, 1.5, 1, 1, 1])
            
            # 共X条
            with cols[0]:
                st.caption(f"共{self.total}条")
            
            # 上一页
            with cols[1]:
                disabled = self.current_page <= 1
                if st.button("◀", key="page_prev", disabled=disabled, 
                            use_container_width=True, help="上一页"):
                    StateManager.set_editing_id(None)
                    StateManager.prev_page()
                    st.rerun()
            
            # 页码（3个）
            pages = self._get_compact_pages()
            for i, page in enumerate(pages[:3]):
                with cols[2 + i]:
                    if page == "...":
                        st.caption("…")
                    else:
                        is_current = page == self.current_page
                        btn_type = "primary" if is_current else "secondary"
                        if st.button(str(page), key=f"page_{page}", type=btn_type, 
                                    use_container_width=True):
                            if not is_current:
                                StateManager.set_editing_id(None)
                                StateManager.goto_page(page)
                                st.rerun()
            
            # 下一页
            with cols[5]:
                disabled = self.current_page >= self.max_page
                if st.button("▶", key="page_next", disabled=disabled,
                            use_container_width=True, help="下一页"):
                    StateManager.set_editing_id(None)
                    StateManager.next_page()
                    st.rerun()
            
            # 每页条数
            with cols[6]:
                cur_idx = PER_PAGE_OPTIONS.index(self.per_page) \
                          if self.per_page in PER_PAGE_OPTIONS else 1
                
                new_per = st.selectbox(
                    "",
                    options=PER_PAGE_OPTIONS,
                    index=cur_idx,
                    format_func=lambda x: f"{x}条/页",
                    label_visibility="collapsed",
                    key="per_page_select"
                )
                
                if new_per != self.per_page:
                    StateManager.set_per_page(new_per)
                    st.rerun()
            
            # 跳至
            with cols[7]:
                st.caption("跳至")
            
            # 输入框
            with cols[8]:
                jump_page = st.number_input(
                    "",
                    min_value=1,
                    max_value=self.max_page,
                    value=self.current_page,
                    step=1,
                    label_visibility="collapsed",
                    key="jump_page_input"
                )
            
            # 页按钮
            with cols[9]:
                if st.button("页", key="jump_btn", use_container_width=True):
                    if jump_page != self.current_page:
                        StateManager.set_editing_id(None)
                        StateManager.goto_page(int(jump_page))
                        st.rerun()
    
    def _get_compact_pages(self):
        """获取紧凑的页码列表（最多3个）"""
        if self.max_page <= 3:
            return list(range(1, self.max_page + 1))
        
        current = self.current_page
        
        if current <= 2:
            return [1, 2, 3]
        elif current >= self.max_page - 1:
            return [self.max_page - 2, self.max_page - 1, self.max_page]
        else:
            return [current - 1, current, current + 1]