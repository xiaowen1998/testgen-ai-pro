"""
导出面板组件
"""


import streamlit as st
from typing import List
from src.models import TestCase
from src.services.export_service import ExportService


class ExportPanel:
    """导出按钮组组件"""
    
    def __init__(self, cases: List[TestCase]):
        self.cases = cases
        self.service = ExportService()
    
    def render(self):
        """渲染导出面板"""
        st.markdown("---")
        st.markdown("### 导出（全部用例）")
        
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        
        # Markdown 导出
        with c1:
            md_content = self.service.to_markdown(self.cases)
            st.download_button(
                "📄 Markdown",
                data=md_content,
                file_name="test_cases.md",
                mime="text/markdown",
                key="dl_md"
            )
        
        # Excel 导出
        with c2:
            try:
                excel_bytes = self.service.to_excel(self.cases)
                st.download_button(
                    "📊 Excel",
                    data=excel_bytes,
                    file_name="test_cases.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_xlsx"
                )
            except Exception as e:
                st.caption(f"Excel导出异常: {e}")
        
        # Word 导出
        with c3:
            try:
                word_bytes = self.service.to_word(self.cases)
                st.download_button(
                    "📝 Word",
                    data=word_bytes,
                    file_name="test_cases.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="dl_docx"
                )
            except Exception as e:
                st.caption(f"Word导出异常: {e}")
        
        # PDF 导出
        with c4:
            try:
                pdf_bytes = self.service.to_pdf(self.cases)
                st.download_button(
                    "📕 PDF",
                    data=pdf_bytes,
                    file_name="test_cases.pdf",
                    mime="application/pdf",
                    key="dl_pdf"
                )
            except Exception as e:
                st.caption(f"PDF导出异常: {e}")
        
        # XMind 导出
        with c5:
            try:
                xmind_bytes = self.service.to_xmind(self.cases)
                st.download_button(
                    "🧠 XMind",
                    data=xmind_bytes,
                    file_name="test_cases.xmind",
                    mime="application/octet-stream",
                    key="dl_xmind"
                )
                st.caption("若打开时出现修复提示，点「修复并打开」或「关闭」即可正常显示。")
            except Exception as e:
                st.caption(f"XMind导出异常: {e}")
        
        # OPML 导出
        with c6:
            try:
                opml_bytes = self.service.to_opml(self.cases)
                st.download_button(
                    "📋 OPML",
                    data=opml_bytes,
                    file_name="test_cases.opml",
                    mime="text/x-opml+xml",
                    key="dl_opml"
                )
            except Exception as e:
                st.caption(f"OPML导出异常: {e}")