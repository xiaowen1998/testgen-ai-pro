"""
配置管理
集中管理所有常量、环境变量和样式
"""

import os
from functools import lru_cache
from typing import List, Tuple


# ========== 分页配置 ==========
PER_PAGE_DEFAULT = 15
PER_PAGE_OPTIONS = [10, 15, 20, 30]


# ========== 生成参数配置 ==========
STAGE1_MAX_CONTENT_CHARS = 12000  # 阶段1需求文本最大长度
STAGE2_MAX_POINTS_PER_BATCH = 15  # 阶段2每批最大测试点数
XMIND_MAX_EXTRACT_CHARS = 20000   # XMind解析最大字符数
API_REQUEST_TIMEOUT = 180         # API请求超时（秒）


# ========== 优先级排序 ==========
PRIORITY_ORDER = {"高": 0, "中": 1, "低": 2}


# ========== 类型标签配置 ==========
TYPE_TAG_CONFIG: dict[tuple[str, ...], tuple[str, str, str]] = {
    ("功能", "功能测试"): ("功能", "tag-func", "#3b82f6"),
    ("边界", "边界值", "边界测试"): ("边界", "tag-boundary", "#f97316"),
    ("异常", "异常测试"): ("异常", "tag-exception", "#ef4444"),
    ("兼容性", "兼容"): ("兼容性", "tag-compatibility", "#6b7280"),
    ("性能", "性能测试"): ("性能", "tag-performance", "#8b5cf6"),
    ("安全", "安全测试"): ("安全", "tag-security", "#374151"),
    ("UI", "UI测试", "界面", "界面测试"): ("UI", "tag-ui", "#06b6d4"),
    ("接口", "API", "接口测试", "API测试"): ("接口", "tag-api", "#10b981"),
    ("冒烟", "冒烟测试"): ("冒烟", "tag-smoke", "#eab308"),
    ("回归", "回归测试"): ("回归", "tag-regression", "#ec4899"),
}


def get_type_tag_style(test_type: str) -> tuple[str, str, str]:
    """
    根据测试类型获取显示标签、CSS类和颜色
    支持别名与模糊匹配
    """
    if not test_type or not str(test_type).strip():
        return ("其他", "tag-other", "#9ca3af")
    
    test_type_lower = str(test_type).strip().lower()
    for aliases, (display, css_class, color) in TYPE_TAG_CONFIG.items():
        for alias in aliases:
            if alias.lower() in test_type_lower or test_type_lower in alias.lower():
                return (display, css_class, color)
    
    return (str(test_type).strip(), "tag-other", "#9ca3af")


# ========== 表格配置 ==========
TABLE_HEADERS = ["用例编号", "用例名称", "所属需求模块", "测试类型", "前置条件", "测试步骤", "测试数据", "预期结果", "优先级"]


# ========== 模型路由配置 ==========
# 格式: {输入源: (阶段1-分析测试点模型, 阶段2-生成用例模型, 显示名称, 描述说明)}
# 图片识别特殊处理：图片识别本身用 qwen-vl-max，但识别后的文本分析用普通文本模型
MODEL_ROUTING = {
    "text": ("qwen-turbo", "qwen-turbo", "⚡ 极速模式", "文本分析，成本低速度快"),
    "document": ("qwen-turbo", "qwen-turbo", "⚡ 极速模式", "文档解析已完成"),
    "url": ("qwen-turbo", "qwen-turbo", "⚡ 极速模式", "网页文本分析"),
    # 图片：识别阶段用 vl-max，但分析测试点和生成用例都用文本模型（因为已经识别成文本了）
    "image": ("qwen-turbo", "qwen-turbo", "🖼️ 视觉模式", "图片已识别为文本，将用文本模型生成测试点与用例"),
}


def get_qwen_model_list() -> List[str]:
    """获取模型列表（用于多模型回退）"""
    # 优先使用 QWEN_MODEL_LIST，其次使用 QWEN_MODEL，最后使用默认值
    raw = (os.getenv("QWEN_MODEL_LIST") or os.getenv("QWEN_MODEL") or "qwen-turbo").strip()
    if "," in raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return [raw] if raw else ["qwen-turbo"]


def get_models_for_input(input_source: str) -> Tuple[str, str, str, str]:
    """根据输入类型返回 (stage1模型, stage2模型, 显示名称, 描述)"""
    return MODEL_ROUTING.get(input_source, ("qwen-turbo", "qwen-turbo", "⚡ 极速模式", ""))


# ========== API配置 ==========
def get_qwen_api_key() -> str:
    """获取API Key"""
    return (os.getenv("QWEN_API_KEY") or "").strip()


# get_qwen_model_list 函数已移至上方


# ========== 加载CSS样式 ==========
def load_css() -> str:
    """从文件加载CSS样式"""
    css_path = os.path.join(os.path.dirname(__file__), "..", "assets", "css", "main.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            return f.read()
    
    # 默认样式（内联备用）
    return DEFAULT_CSS


DEFAULT_CSS = """
.gradient-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #5b21b6 100%);
    padding: 1.5rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(102, 126, 234, 0.35);
}
.gradient-header h1 { color: white !important; font-size: 2rem !important; font-weight: 700 !important; margin: 0 !important; }
.gradient-header p { color: rgba(255,255,255,0.9) !important; font-size: 0.95rem !important; margin: 0.4rem 0 0 0 !important; }
.stApp { background: linear-gradient(180deg, #f5f3ff 0%, #f8fafc 100%); }
.pagination-info { font-size: 0.9rem; color: #64748b; margin-bottom: 0.5rem; }
table.cases-table { border-collapse: collapse; width: 100%; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); table-layout: fixed; }
table.cases-table th, table.cases-table td { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; word-wrap: break-word; }
table.cases-table th { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white !important; font-weight: 600; }
table.cases-table tbody tr:hover td { background: #f8fafc; }
table.cases-table td.cell-wrap { white-space: pre-wrap; word-break: break-word; max-width: 180px; }
table.cases-table tr.row-low-quality { background: #fef2f2 !important; }
table.cases-table tr.row-placeholder { background: #fef3c7 !important; }
.row-editing-wrap { background: #fef3c7 !important; padding: 8px 12px; border-radius: 8px; margin: 4px 0; border: 1px solid #f59e0b; }
.type-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 500; }
.type-tag.tag-func { background: #3b82f6; color: #fff; }
.type-tag.tag-boundary { background: #f97316; color: #fff; }
.type-tag.tag-exception { background: #ef4444; color: #fff; }
.type-tag.tag-other { background: #9ca3af; color: #fff; }
.type-tag.tag-compatibility { background: #6b7280; color: #fff; }
.type-tag.tag-performance { background: #8b5cf6; color: #fff; }
.type-tag.tag-security { background: #374151; color: #fff; }
.type-tag.tag-ui { background: #06b6d4; color: #fff; }
.type-tag.tag-api { background: #10b981; color: #fff; }
.type-tag.tag-smoke { background: #eab308; color: #000; }
.type-tag.tag-regression { background: #ec4899; color: #fff; }
.priority-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 500; }
.priority-tag.tag-pri-high { background: #fecaca; color: #991b1b; }
.priority-tag.tag-pri-mid { background: #fef08a; color: #854d0e; }
.priority-tag.tag-pri-low { background: #bbf7d0; color: #166534; }
.table-scroll-wrap { overflow-x: auto; margin: 0.5rem 0; }
.pagination-bar { display: flex; justify-content: flex-end; align-items: center; gap: 0.5rem; flex-wrap: wrap; font-size: 0.875rem; }
"""
