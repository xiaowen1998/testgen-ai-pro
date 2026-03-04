"""
输入选项卡组件
支持文本、文档、URL、图片四种输入方式
"""

import base64
import streamlit as st
from typing import Optional, Callable
from src.utils.state import StateManager


class InputTabs:
    """四种输入方式的选项卡组件"""
    
    def __init__(self):
        self.source = "text"
    
    def render(self) -> str:
        """渲染输入选项卡，返回获取到的需求文本"""
        # 创建选项卡
        tab1, tab2, tab3, tab4 = st.tabs([
            "📝 文本输入", 
            "📎 文档上传", 
            "🔗 网页链接", 
            "🖼️ 图片识别"
        ])
        
        requirement = ""
        
        with tab1:
            requirement = self._render_text_input()
        
        with tab2:
            req_doc = self._render_document_upload()
            if req_doc:
                requirement = req_doc
        
        with tab3:
            req_url = self._render_url_input()
            if req_url:
                requirement = req_url
        
        with tab4:
            req_img = self._render_image_upload()
            if req_img:
                requirement = req_img
        
        # 汇总所有来源的需求文本
        final_req = self._collect_requirement(requirement)
        return final_req
    
    def _render_text_input(self) -> str:
        """文本输入"""
        text = st.text_area(
            "需求描述",
            value=StateManager.get_requirement_text(),
            height=200,
            placeholder="请输入需求描述…",
            key="req_text_area"
        )
        if text:
            StateManager.set_input_source("text")
            StateManager.set_requirement_text(text)
        return text
    
    def _render_document_upload(self) -> Optional[str]:
        """文档上传"""
        from src.services.document_parser import DocumentParser
        
        uploaded = st.file_uploader(
            "支持 PDF、Word(.docx)、TXT、Markdown、XMind(.xmind)、ZIP 压缩包",
            type=["pdf", "docx", "txt", "md", "xmind", "zip"],
            key="file_upload"
        )
        
        if uploaded:
            try:
                parser = DocumentParser()
                text = parser.parse(uploaded)
                StateManager.set_input_source("document")
                StateManager.set_requirement_text(text)
                
                # 显示解析后的文本（可编辑）
                edited = st.text_area(
                    "解析后的文本（可编辑）",
                    value=text,
                    height=200,
                    key="req_upload_text"
                )
                return edited
            except Exception as e:
                st.error(f"文档解析失败: {str(e)}")
        
        return None
    
    def _render_url_input(self) -> Optional[str]:
        """网页链接"""
        from src.services.document_parser import DocumentParser
        
        url = st.text_input(
            "输入网页 URL",
            placeholder="https://...",
            key="url_input"
        )
        
        if st.button("抓取", key="fetch_btn"):
            if not url or not url.strip():
                st.warning("请输入有效 URL")
                return None
            
            with st.spinner("正在抓取…"):
                try:
                    parser = DocumentParser()
                    text = parser.parse_url(url.strip())
                    StateManager.set_input_source("url")
                    StateManager.set_requirement_text(text)
                    
                    # 显示抓取到的文本（可编辑）
                    edited = st.text_area(
                        "抓取到的正文（可编辑）",
                        value=text,
                        height=200,
                        key="req_url_text"
                    )
                    return edited
                except Exception as e:
                    st.error(str(e))
        
        # 返回已保存的URL内容
        return StateManager.get_requirement_text() if StateManager.get_input_source() == "url" else None
    
    def _render_image_upload(self) -> Optional[str]:
        """图片识别"""
        from src.services.document_parser import DocumentParser
        
        uploaded_image = st.file_uploader(
            "选择图片",
            type=["png", "jpg", "jpeg", "webp"],
            key="image_upload"
        )
        
        if uploaded_image:
            last_name = StateManager.get_last_image_name()
            
            # 新图片上传，自动识别
            if last_name != uploaded_image.name:
                with st.spinner("🤖 正在识别图片中的文字和需求…"):
                    try:
                        parser = DocumentParser()
                        text = parser.parse_image(uploaded_image)
                        StateManager.set_input_source("image")
                        StateManager.set_requirement_text(text)
                        StateManager.set_last_image_name(uploaded_image.name)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
                        StateManager.set_last_image_name("")
            
            # 显示识别的文本（可编辑）
            if StateManager.get_input_source() == "image":
                edited = st.text_area(
                    "识别的文本（可编辑）",
                    value=StateManager.get_requirement_text(),
                    height=200,
                    key="req_image_text"
                )
                return edited
        
        return None
    
    def _collect_requirement(self, current: str) -> str:
        """汇总所有来源的需求文本"""
        # 优先级：当前传入 > 各来源存储的
        if current and current.strip():
            return current.strip()
        
        # 按优先级获取
        sources = ["req_text", "req_upload_text", "req_url_text", "req_image_text"]
        for key in sources:
            text = st.session_state.get(key, "")
            if text and text.strip():
                return text.strip()
        
        # 最后尝试全局存储
        return StateManager.get_requirement_text()