"""
TestGen AI Testcases V8.0 - 重构版
基于 Streamlit 的测试用例生成器
"""


import streamlit as st
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from src.config import load_css, get_models_for_input
from src.models import TestCase, TestPoint
from src.utils.state import StateManager
from src.components.input_tabs import InputTabs
from src.components.case_table import CaseTable
from src.components.pagination import Pagination
from src.components.export_panel import ExportPanel
from src.services.case_generator import CaseGenerator, CaseGeneratorError
from src.services.ai_service import AIService, APIKeyError


# 页面配置
st.set_page_config(
    page_title="TestGen AI Testcases",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    """主入口"""
    # 初始化状态
    StateManager.init()
    
    # 加载CSS
    css = load_css()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    
    # 渲染头部
    render_header()
    
    # 检查API配置
    ai_service = AIService()
    if not ai_service.is_configured():
        st.error("未配置 QWEN_API_KEY，请在 .env 中设置。")
        st.info("示例：QWEN_API_KEY=sk-xxx（阿里云百炼/灵积控制台）")
        return
    
    # 渲染输入区
    input_tabs = InputTabs()
    requirement = input_tabs.render()
    
    # 生成按钮
    render_generate_buttons(requirement)
    
    # 渲染结果区
    render_results()


def render_header():
    """渲染页面头部"""
    st.markdown("""
        <div class="gradient-header">
            <h1>🧪 TestGen AI Testcases</h1>
            <p>基于 AI 自动化生成测试用例。支持文本输入、文档上传、网页链接、图片识别等方式，
            先解析测试点、按测试点生成用例，覆盖更全、列表内直接编辑保存、导出各种格式文档。</p>
        </div>
    """, unsafe_allow_html=True)


def render_generate_buttons(requirement: str):
    """渲染生成按钮"""
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("生成测试用例", type="primary", use_container_width=True):
            handle_generate(requirement)
    
    with col2:
        if st.button("重新生成", use_container_width=True, help="保留当前需求，重新执行双阶段生成"):
            handle_generate(requirement)


def handle_generate(requirement: str):
    """处理生成逻辑"""
    if not requirement or not requirement.strip():
        st.warning("请先通过文本/上传/链接/图片方式提供需求内容。")
        return
    
    # 获取输入源类型，用于模型路由
    input_source = StateManager.get_input_source()
    generator = CaseGenerator(input_source=input_source)
    
    try:
        with st.status("正在生成测试用例...", expanded=True) as status:
            # 使用新的统一生成方法
            def progress_cb(message):
                status.write(message)
            
            result = generator.generate(requirement.strip(), progress_cb)
            
            if not result.is_valid:
                st.error(result.error_message)
                return
            
            StateManager.set_points(result.test_points)
            StateManager.set_cases(result.cases)
            
            # 计算总耗时
            total_elapsed = result.elapsed_stage1 + result.elapsed_stage2
            
            status.update(
                label=f"✅ 完成！共识别 {len(result.test_points)} 个测试点，生成 {len(result.cases)} 条用例（耗时 {total_elapsed:.1f}s）",
                state="complete"
            )
        
        st.rerun()
        
    except APIKeyError as e:
        st.error(f"API密钥错误: {e}")
    except CaseGeneratorError as e:
        st.error(f"生成失败: {e}")
    except Exception as e:
        st.error(f"生成过程出错: {e}")


def render_results():
    """渲染结果区"""
    cases = StateManager.get_cases()
    points = StateManager.get_points()
    
    if not cases:
        st.info("在上方输入需求并点击「生成测试用例」后，将先分析测试点再生成用例。")
        return
    
    # 显示保存成功提示
    if StateManager.get_and_clear_saved_message():
        st.success("✅ 已保存")
    
    # 测试点清单（可折叠）
    if points:
        with st.expander(f"📋 已识别测试点清单（共 {len(points)} 个）", expanded=False):
            for i, p in enumerate(points[:80], 1):
                st.markdown(f"{i}. {p.title}")
            if len(points) > 80:
                st.caption(f"... 共 {len(points)} 个")
    
    # 分页计算
    total = len(cases)
    per_page = StateManager.get_per_page()
    current_page = StateManager.get_current_page()
    max_page = max(1, (total + per_page - 1) // per_page)
    current_page = max(1, min(current_page, max_page))
    
    # 更新当前页（如果超出范围）
    if current_page != StateManager.get_current_page():
        StateManager.set_current_page(current_page)
    
    start = (current_page - 1) * per_page
    page_cases = cases[start:start + per_page]
    
    # 渲染表格
    table = CaseTable(page_cases, start)
    table.render()
    
    # 渲染分页
    Pagination(total, current_page, per_page).render()
    
    # 渲染导出面板
    ExportPanel(cases).render()


if __name__ == "__main__":
    main()