"""
AI 测试用例生成器 V7.0
测试点驱动双阶段 · 精简UI：测试点清单 → 用例表格 → 分页（无筛选/统计）
"""

import io
import os
import json
import re
import difflib
from typing import List, Optional, Any

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

st.set_page_config(
    page_title="TestGen AI V7.0 - 测试用例生成器",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== 常量 ==========
PER_PAGE = 15
TABLE_HEADERS = ["用例编号", "用例名称", "所属需求模块", "测试类型", "前置条件", "测试步骤", "测试数据", "预期结果", "优先级"]
PRIORITY_ORDER = {"高": 0, "中": 1, "低": 2}
TYPE_TAG_CLASS = {
    "功能": "tag-func",
    "边界": "tag-boundary",
    "异常": "tag-exception",
    "兼容性": "tag-other",
    "性能": "tag-other",
    "安全": "tag-other",
}

# V6.0 第1阶段：测试点分析
PROMPT_STAGE1_TEST_POINTS = """你是一位资深测试架构师。请先深度分析以下需求文档，识别所有需要验证的测试点。

需求内容：
{content}

要求：
1. 逐条阅读需求，识别每个功能规则、状态变化、交互逻辑、数据计算、展示规则、异常分支
2. 输出完整的"测试点清单"，每个测试点一句话描述（如："验证温层标签在冷冻商品上的展示"）
3. 只输出测试点清单，不生成用例
4. 确保没有遗漏任何需求点

输出格式（严格按此格式，便于解析）：
测试点1：XXXX
测试点2：XXXX
测试点3：XXXX
..."""

# V6.0 第2阶段：基于测试点生成用例
PROMPT_STAGE2_CASES = """基于以下测试点清单，为每个测试点生成对应的测试用例。

【测试点清单】
{test_points}

【要求】
1. 每个测试点至少生成 1 条验证用例；复杂测试点（涉及计算、多状态组合）生成 2～3 条
2. 用例必须包含：case_id、case_name、module（所属需求模块）、test_point（对应测试点序号或描述）、test_type、precondition、steps、test_data、expected、priority
3. 步骤要详细（具体到按钮名称），数据要具体（给出数值），结果要可验证
4. 不要人为限制数量，需求复杂则用例数量自然增加

【输出】
仅输出一个 JSON 数组，不要 markdown 代码块或其它说明。格式示例：
[{{"case_id":"TC001","case_name":"标题","module":"购物车","test_point":"测试点1","test_type":"功能","precondition":"已登录","steps":"步骤1；步骤2","test_data":"具体数据","expected":"预期表现","priority":"高"}}]"""

SYSTEM_STAGE2 = """你生成测试用例时必须：
1. 基于给定的测试点清单，每个测试点至少有 1 条对应用例
2. 步骤具体到 UI 元素（按钮名、输入框），数据给出具体值（如手机号 13800138000）
3. 结果可断言，前置条件完整
4. 不人为限制条数，复杂需求则用例增多
只输出有效的 JSON 数组。"""


def parse_llm_response(text: str) -> List[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "test_cases" in data:
            return data["test_cases"]
        return [data]
    except json.JSONDecodeError:
        return []


def normalize_case(c: dict) -> dict:
    """统一字段名：module/所属需求模块、test_point 等"""
    out = dict(c)
    if "所属需求模块" in out and "module" not in out:
        out["module"] = out.get("所属需求模块") or ""
    if "module" not in out:
        out["module"] = out.get("所属需求模块") or out.get("test_point") or "-"
    return out


def dedupe_by_title_similarity(cases: List[dict], threshold: float = 0.8) -> List[dict]:
    if not cases:
        return []
    out = []
    for c in cases:
        name = (c.get("case_name") or "").strip()
        is_dup = False
        for o in out:
            oname = (o.get("case_name") or "").strip()
            if name and oname and difflib.SequenceMatcher(None, name, oname).ratio() >= threshold:
                is_dup = True
                break
        if not is_dup:
            out.append(c)
    return out


def sort_by_priority(cases: List[dict]) -> List[dict]:
    def key(c):
        return PRIORITY_ORDER.get((c.get("priority") or "中").strip(), 1)
    return sorted(cases, key=key)


def post_process(cases: List[dict]) -> List[dict]:
    cases = [normalize_case(c) for c in cases]
    cases = dedupe_by_title_similarity(cases, 0.8)
    cases = sort_by_priority(cases)
    for i, c in enumerate(cases, 1):
        c["case_id"] = f"TC{i:03d}"
    return cases


def run_stage1_test_points(client: OpenAI, content: str) -> List[str]:
    """第1阶段：分析需求，返回测试点清单。"""
    prompt = PROMPT_STAGE1_TEST_POINTS.format(content=content[:12000])
    response = client.chat.completions.create(
        model=os.getenv("QWEN_MODEL", "qwen-turbo"),
        messages=[
            {"role": "system", "content": "你只输出测试点清单，格式为 测试点N：描述，不要其他内容。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    text = (response.choices[0].message.content or "").strip()
    points = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 匹配 "测试点1：xxx" 或 "1. xxx"
        m = re.match(r"测试点\s*\d+\s*[：:]\s*(.+)", line, re.I)
        if m:
            points.append(m.group(1).strip())
        elif re.match(r"\d+[\.．、]\s*.+", line):
            points.append(re.sub(r"^\d+[\.．、]\s*", "", line).strip())
    return points


def run_stage2_cases(client: OpenAI, test_points: List[str], content: str) -> List[dict]:
    """第2阶段：基于测试点清单生成用例。"""
    test_points_text = "\n".join(f"测试点{i+1}：{p}" for i, p in enumerate(test_points))
    prompt = PROMPT_STAGE2_CASES.format(test_points=test_points_text)
    response = client.chat.completions.create(
        model=os.getenv("QWEN_MODEL", "qwen-turbo"),
        messages=[
            {"role": "system", "content": SYSTEM_STAGE2},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    text = (response.choices[0].message.content or "").strip()
    cases = parse_llm_response(text)
    if not isinstance(cases, list):
        cases = [cases] if isinstance(cases, dict) else []
    return post_process(cases)


# ========== 文档解析 ==========
def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        parts = [p.extract_text() for p in reader.pages if p.extract_text()]
        return "\n\n".join(parts).strip() if parts else ""
    except Exception as e:
        raise RuntimeError(f"PDF 解析失败: {e}") from e


def extract_docx_text(file_bytes: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
    except Exception as e:
        raise RuntimeError(f"Word 解析失败: {e}") from e


def extract_txt_or_md(file_bytes: bytes, _filename: str = "") -> str:
    for enc in ("utf-8", "gbk", "gb2312"):
        try:
            return file_bytes.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    raise RuntimeError("无法识别文件编码。")


def extract_text_from_upload(uploaded_file) -> str:
    name = (uploaded_file.name or "").lower()
    raw = uploaded_file.read()
    if name.endswith(".pdf"):
        return extract_pdf_text(raw)
    if name.endswith(".docx"):
        return extract_docx_text(raw)
    if name.endswith(".txt") or name.endswith(".md") or name.endswith(".markdown"):
        return extract_txt_or_md(raw, name)
    raise ValueError("仅支持 PDF、Word(.docx)、TXT、Markdown。")


# 抓取到疑似“未登录”页面时的提示（引导用户复制文本或上传文档）
MSG_LOGIN_REQUIRED = (
    "页面未登录，无法通过 URL 自动登录。请复制页面正文到「文本输入」中生成，或使用「文档上传」上传文档。"
)
# 抓取结果为“需启用 JavaScript”等无效内容时的提示
MSG_JS_NO_CONTENT = (
    "该页面需在浏览器中执行 JavaScript 后才显示正文，当前无法抓取到有效内容。请将页面正文复制到「文本输入」中，或使用「文档上传」上传文档。"
)


def _is_login_required_page(text: str) -> bool:
    """根据抓取结果判断是否为需登录页面（内容过短且含登录相关关键词）。"""
    if not text or len(text) > 800:
        return False
    t = text.strip().lower()
    keywords = ("登录", "请登录", "未登录", "login", "sign in", "登录以继续", "去登录", "立即登录")
    return any(kw.lower() in t or kw in text for kw in keywords)


def _is_js_placeholder_content(text: str) -> bool:
    """抓取结果是否为“需启用 JavaScript”等无效占位内容（需给出提示而非静默填入）。"""
    if not text or len(text) > 600:
        return False
    t = text.strip().lower()
    return "enable javascript" in t or "you need to enable javascript" in t or "请启用 javascript" in t


def _extract_text_from_html(html: str) -> str:
    """从 HTML 中提取正文，去掉 script/style 等。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    body = soup.find("body") or soup
    text = body.get_text(separator="\n", strip=True) if body else ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _fetch_url_with_playwright(url: str) -> str:
    """使用 Playwright 抓取需要 JavaScript 渲染的页面。"""
    from playwright.sync_api import sync_playwright
    url = url.strip()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            # 使用 load 而非 networkidle，避免 SPA/长轮询页面一直不满足 networkidle 导致超时
            page.goto(url, wait_until="load", timeout=25000)
            page.wait_for_timeout(4000)
            html = page.content()
            return _extract_text_from_html(html)
        finally:
            browser.close()


def fetch_url_text(url: str) -> str:
    """抓取网页正文；若为 JS 渲染页面则自动尝试 Playwright。"""
    try:
        import requests
        r = requests.get(
            url.strip(),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
            timeout=15,
        )
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        text = _extract_text_from_html(r.text)
        if not text or len(text) < 80 or "enable javascript" in text.lower() or "enable JavaScript" in text:
            try:
                text = _fetch_url_with_playwright(url)
            except ImportError:
                raise RuntimeError(
                    "该页面需执行 JavaScript 才能显示内容。请安装 Playwright 后重试："
                    " pip install playwright && playwright install chromium"
                    "；或直接将页面正文复制到「文本输入」中。"
                ) from None
            except Exception as e:
                err_msg = str(e).strip()
                if "timeout" in err_msg.lower() or "Timeout" in err_msg:
                    raise RuntimeError(
                        "页面加载超时（该链接可能需登录或加载较慢）。请将正文复制到「文本输入」中生成，或使用「文档上传」上传文档。"
                    ) from e
                raise RuntimeError(f"Playwright 抓取失败: {e}") from e
        if _is_login_required_page(text):
            raise RuntimeError(MSG_LOGIN_REQUIRED)
        if _is_js_placeholder_content(text):
            raise RuntimeError(MSG_JS_NO_CONTENT)
        return text
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"抓取失败: {e}") from e


def get_qwen_client() -> Optional[OpenAI]:
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")


# ========== 表格与导出 ==========
def _cell_text(s: str) -> str:
    if not s:
        return "-"
    return str(s).replace("\n", " ").replace("|", "｜").strip() or "-"


def _get_module(c: dict) -> str:
    return _cell_text(c.get("module") or c.get("所属需求模块"))


def cases_to_rows(cases: List[dict]) -> List[List[str]]:
    return [
        [
            _cell_text(c.get("case_id")),
            _cell_text(c.get("case_name")),
            _get_module(c),
            _cell_text(c.get("test_type")),
            _cell_text(c.get("precondition")),
            _cell_text(c.get("steps")),
            _cell_text(c.get("test_data")),
            _cell_text(c.get("expected")),
            _cell_text(c.get("priority")),
        ]
        for c in cases
    ]


def to_markdown(cases: List[dict]) -> str:
    if not cases:
        return ""
    header_line = "| " + " | ".join(TABLE_HEADERS) + " |"
    sep = "| " + " | ".join(["---"] * len(TABLE_HEADERS)) + " |"
    rows = cases_to_rows(cases)
    body = "\n".join("| " + " | ".join(cell for cell in row) + " |" for row in rows)
    return "\n".join([header_line, sep, body])


def _html_esc(s: str) -> str:
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def to_html_table_with_type_colors(cases: List[dict], low_quality_ids: Optional[set] = None) -> str:
    low_quality_ids = low_quality_ids or set()
    if not cases:
        return ""
    sb = ['<table class="cases-table"><thead><tr><th>序号</th>']
    for h in TABLE_HEADERS:
        sb.append(f"<th>{_html_esc(h)}</th>")
    sb.append("</tr></thead><tbody>")
    for idx, c in enumerate(cases, 1):
        cid = _cell_text(c.get("case_id"))
        row_cls = ' class="row-low-quality"' if cid in low_quality_ids else ""
        sb.append(f"<tr{row_cls}>")
        sb.append(f"<td>{idx}</td>")
        sb.append(f"<td>{_html_esc(cid)}</td>")
        sb.append(f"<td>{_html_esc(_cell_text(c.get('case_name')))}</td>")
        sb.append(f"<td>{_html_esc(_get_module(c))}</td>")
        t = _cell_text(c.get("test_type"))
        cls = TYPE_TAG_CLASS.get(t, "tag-other")
        sb.append(f'<td><span class="type-tag {cls}">{_html_esc(t)}</span></td>')
        for key in ("precondition", "steps", "test_data", "expected", "priority"):
            sb.append(f"<td class='cell-wrap'>{_html_esc(_cell_text(c.get(key)))}</td>")
        sb.append("</tr>")
    sb.append("</tbody></table>")
    return "".join(sb)


def to_html_table_v7(cases: List[dict]) -> str:
    """V7: 表格含 操作 列，类型/优先级带颜色标签，支持横向滚动外层."""
    if not cases:
        return ""
    headers = ["序号", "编号", "用例名称", "模块", "类型", "前置条件", "步骤", "测试数据", "预期结果", "优先级", "操作"]
    sb = ['<div class="table-scroll-wrap"><table class="cases-table"><thead><tr>']
    for h in headers:
        sb.append(f"<th>{_html_esc(h)}</th>")
    sb.append("</tr></thead><tbody>")
    for idx, c in enumerate(cases, 1):
        cid = _cell_text(c.get("case_id"))
        sb.append("<tr>")
        sb.append(f"<td>{idx}</td>")
        sb.append(f"<td>{_html_esc(cid)}</td>")
        sb.append(f"<td class='cell-wrap'>{_html_esc(_cell_text(c.get('case_name')))}</td>")
        sb.append(f"<td>{_html_esc(_get_module(c))}</td>")
        t = _cell_text(c.get("test_type"))
        tag_cls = TYPE_TAG_CLASS.get(t, "tag-other")
        sb.append(f'<td><span class="type-tag {tag_cls}">{_html_esc(t)}</span></td>')
        for key in ("precondition", "steps", "test_data", "expected"):
            sb.append(f"<td class='cell-wrap'>{_html_esc(_cell_text(c.get(key)))}</td>")
        p = _cell_text(c.get("priority"))
        pri_cls = "tag-pri-high" if p == "高" else ("tag-pri-mid" if p == "中" else "tag-pri-low")
        sb.append(f'<td><span class="priority-tag {pri_cls}">{_html_esc(p)}</span></td>')
        sb.append("<td>编辑</td>")
        sb.append("</tr>")
    sb.append("</tbody></table></div>")
    return "".join(sb)


def to_excel_bytes(cases: List[dict]) -> bytes:
    import pandas as pd
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill
    df = pd.DataFrame(cases_to_rows(cases), columns=TABLE_HEADERS)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    wb = load_workbook(buf)
    ws = wb.active
    fill_high = PatternFill(start_color="FFCCCB", end_color="FFCCCB", fill_type="solid")
    fill_mid = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")
    fill_low = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
    pri_col = 9
    for row in range(2, ws.max_row + 1):
        val = (ws.cell(row=row, column=pri_col).value or "").strip()
        if val == "高":
            for col in range(1, 10):
                ws.cell(row=row, column=col).fill = fill_high
        elif val == "中":
            for col in range(1, 10):
                ws.cell(row=row, column=col).fill = fill_mid
        elif val == "低":
            for col in range(1, 10):
                ws.cell(row=row, column=col).fill = fill_low
    # 增加筛选：表头行启用自动筛选
    if ws.max_row >= 1:
        ws.auto_filter.ref = f"A1:I{ws.max_row}"
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.read()


def to_word_bytes(cases: List[dict]) -> bytes:
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    doc.add_heading("测试用例", 0)
    doc.add_paragraph("以下为根据需求生成的测试用例列表，可直接用于执行。")
    doc.add_paragraph()
    doc.add_heading("目录", level=1)
    for c in cases:
        doc.add_paragraph(f"{_cell_text(c.get('case_id'))} - {_cell_text(c.get('case_name'))}", style="List Bullet")
    doc.add_page_break()
    for i, c in enumerate(cases):
        if i > 0:
            doc.add_page_break()
        doc.add_heading(f"{_cell_text(c.get('case_id'))} - {_cell_text(c.get('case_name'))}", level=1)
        doc.add_paragraph(f"所属模块：{_get_module(c)}")
        doc.add_paragraph(f"测试类型：{_cell_text(c.get('test_type'))} | 优先级：{_cell_text(c.get('priority'))}")
        doc.add_paragraph(f"前置条件：{_cell_text(c.get('precondition'))}")
        doc.add_paragraph(f"测试步骤：{_cell_text(c.get('steps'))}")
        doc.add_paragraph(f"测试数据：{_cell_text(c.get('test_data'))}")
        doc.add_paragraph(f"预期结果：{_cell_text(c.get('expected'))}")
    for s in doc.sections:
        s.header.is_linked_to_previous = False
        s.footer.is_linked_to_previous = False
        if not s.header.paragraphs:
            s.header.add_paragraph("TestGen AI V5.0 - 测试用例")
        else:
            s.header.paragraphs[0].text = "TestGen AI V5.0 - 测试用例"
        if not s.footer.paragraphs:
            s.footer.add_paragraph("测试用例文档")
        else:
            s.footer.paragraphs[0].text = "测试用例文档"
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def to_pdf_bytes(cases: List[dict]) -> bytes:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=7)
    col_w = 190 / 9
    headers_short = ["ID", "Name", "Module", "Type", "Precond", "Steps", "Data", "Expected", "Priority"]
    for h in headers_short:
        pdf.cell(col_w, 6, h[:10], border=1)
    pdf.ln()
    for c in cases:
        for cell in [
            _cell_text(c.get("case_id"))[:8],
            _cell_text(c.get("case_name"))[:10],
            _get_module(c)[:8],
            _cell_text(c.get("test_type"))[:6],
            _cell_text(c.get("precondition"))[:10],
            _cell_text(c.get("steps"))[:12],
            _cell_text(c.get("test_data"))[:8],
            _cell_text(c.get("expected"))[:12],
            _cell_text(c.get("priority"))[:4],
        ]:
            try:
                pdf.cell(col_w, 5, cell, border=1)
            except Exception:
                pdf.cell(col_w, 5, cell.encode("latin-1", "replace").decode("latin-1"), border=1)
        pdf.ln()
    out = pdf.output()
    return bytes(out) if isinstance(out, bytearray) else out


# ========== AI 评审 ==========
def run_ai_review(client: OpenAI, cases: List[dict], requirement: str) -> dict:
    """返回 {score, suggestions, low_quality_ids}"""
    cases_summary = json.dumps(
        [{"case_id": c.get("case_id"), "case_name": c.get("case_name"), "test_type": c.get("test_type"), "steps": c.get("steps"), "test_data": c.get("test_data"), "expected": c.get("expected")} for c in cases[:50]],
        ensure_ascii=False,
        indent=2,
    )
    prompt = f"""请对以下测试用例集合进行质量评审。

【需求摘要】
{requirement[:1500]}

【用例摘要（部分）】
{cases_summary}

【评审维度】
1. 覆盖度：是否遗漏重要需求点
2. 可执行性：步骤是否具体到可操作
3. 数据完整性：测试数据是否给出具体值
4. 预期可验证性：结果是否可判断通过/失败

请严格按以下 JSON 格式输出，不要其他内容：
{{
  "overall_score": 7,
  "coverage_score": 7,
  "executability_score": 8,
  "data_completeness_score": 6,
  "verifiability_score": 7,
  "suggestions": "优化建议文本，分条列出",
  "low_quality_case_ids": ["TC003", "TC007"]
}}
overall_score 为 1-10 分；low_quality_case_ids 为评分低于 6 分的用例编号列表。"""
    try:
        response = client.chat.completions.create(
            model=os.getenv("QWEN_MODEL", "qwen-turbo"),
            messages=[
                {"role": "system", "content": "你只输出有效的 JSON 对象，不要 markdown 代码块。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        low = data.get("low_quality_case_ids") or []
        return {
            "overall_score": data.get("overall_score", 0),
            "suggestions": data.get("suggestions", ""),
            "low_quality_ids": set(str(x) for x in low),
        }
    except Exception:
        return {"overall_score": 0, "suggestions": "评审解析失败", "low_quality_ids": set()}


# ========== CSS ==========
CUSTOM_CSS = """
<style>
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
    .row-editing-wrap { background: #fef3c7 !important; padding: 8px 12px; border-radius: 8px; margin: 4px 0; border: 1px solid #f59e0b; }
    .type-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 500; }
    .type-tag.tag-func { background: #3b82f6; color: #fff; }
    .type-tag.tag-boundary { background: #f97316; color: #fff; }
    .type-tag.tag-exception { background: #ef4444; color: #fff; }
    .type-tag.tag-other { background: #6b7280; color: #fff; }
    .priority-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 500; }
    .priority-tag.tag-pri-high { background: #fecaca; color: #991b1b; }
    .priority-tag.tag-pri-mid { background: #fef08a; color: #854d0e; }
    .priority-tag.tag-pri-low { background: #bbf7d0; color: #166534; }
    .table-scroll-wrap { overflow-x: auto; margin: 0.5rem 0; }
    .pagination-bar { display: flex; justify-content: flex-end; align-items: center; gap: 0.5rem; flex-wrap: wrap; font-size: 0.875rem; }
    .pagination-bar .stNumberInput { width: 3rem !important; }
</style>
"""


def init_session_state():
    if "test_cases" not in st.session_state:
        st.session_state.test_cases = []
    if "test_points" not in st.session_state:
        st.session_state.test_points = []
    if "result_page" not in st.session_state:
        st.session_state.result_page = 0
    if "test_cases_backup" not in st.session_state:
        st.session_state.test_cases_backup = None
    if "editing_case_id" not in st.session_state:
        st.session_state.editing_case_id = None
    if "saved_message" not in st.session_state:
        st.session_state.saved_message = None


def run():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("""
        <div class="gradient-header">
            <h1>🧪 TestGen AI Testcases </h1>
            <p>基于 AI 自动化生成测试用例。可文本输入、文档上传、网页链接输入等方式，先解析测试点、按测试点生成用例 · 覆盖更全、列表内直接编辑</p>
        </div>
    """, unsafe_allow_html=True)
    init_session_state()

    client = get_qwen_client()
    if not client:
        st.error("未配置 QWEN_API_KEY，请在 .env 中设置。")
        st.info("示例：QWEN_API_KEY=sk-xxx（阿里云百炼/灵积控制台）")
        return

    # 三种输入方式
    tab1, tab2, tab3 = st.tabs(["📝 文本输入", "📎 文档上传", "🔗 网页链接"])
    requirement = ""

    with tab1:
        requirement = st.text_area(
            "需求描述",
            value=st.session_state.get("requirement_text", ""),
            height=200,
            placeholder="请输入需求描述…",
            key="req_text",
        )
        if requirement:
            st.session_state.requirement_text = requirement

    with tab2:
        uploaded = st.file_uploader("支持 PDF、Word(.docx)、TXT、Markdown", type=["pdf", "docx", "txt", "md"], key="file_upload")
        if uploaded:
            try:
                requirement = extract_text_from_upload(uploaded)
                st.session_state.requirement_text = requirement
                st.text_area("解析后的文本（可编辑）", value=requirement, height=200, key="req_upload")
            except Exception as e:
                st.error(str(e))

    with tab3:
        url = st.text_input("输入网页 URL", placeholder="https://...", key="url_input")
        if st.button("抓取", key="fetch_btn"):
            if not url or not url.strip():
                st.warning("请输入有效 URL")
            else:
                with st.spinner("正在抓取…"):
                    try:
                        requirement = fetch_url_text(url)
                        st.session_state.requirement_text = requirement
                        st.session_state.req_url = requirement
                        st.text_area("抓取到的正文（可编辑）", value=requirement, height=200, key="req_url")
                    except Exception as e:
                        st.error(str(e))

    requirement = (
        (st.session_state.get("req_text") or "").strip()
        or (st.session_state.get("req_upload") or "").strip()
        or (st.session_state.get("req_url") or "").strip()
        or (st.session_state.get("requirement_text") or "").strip()
    )

    col_gen, col_regen = st.columns(2)
    with col_gen:
        generate_clicked = st.button("生成测试用例", type="primary", use_container_width=True)
    with col_regen:
        regen_clicked = st.button("重新生成", use_container_width=True, help="保留当前需求，重新执行双阶段生成")

    if generate_clicked or regen_clicked:
        if not requirement or not requirement.strip():
            st.warning("请先通过文本/上传/链接方式提供需求内容。")
            st.stop()
        st.session_state.review_result = None
        content = requirement.strip()
        # 第1阶段：测试点分析
        with st.spinner("第1阶段：分析需求，识别测试点…"):
            try:
                test_points = run_stage1_test_points(client, content)
            except Exception as e:
                st.error(f"测试点分析失败：{str(e)}")
                st.stop()
        if not test_points:
            st.warning("未识别到测试点，请检查需求描述或重试。")
            st.stop()
        st.session_state.test_points = test_points
        # 第2阶段：按测试点生成用例
        with st.spinner(f"第2阶段：基于 {len(test_points)} 个测试点生成用例…"):
            try:
                cases = run_stage2_cases(client, test_points, content)
            except Exception as e:
                st.error(f"用例生成失败：{str(e)}")
                st.stop()
        if not cases:
            st.warning("未能解析出有效测试用例，请重试。")
            st.stop()
        st.session_state.test_cases = cases
        st.session_state.result_page = 0
        st.success(f"共识别 {len(test_points)} 个测试点，生成 {len(cases)} 条用例。")
        st.rerun()

    # 结果区
    cases = st.session_state.get("test_cases", [])
    test_points = st.session_state.get("test_points", [])
    if not cases:
        st.info("在上方输入需求并点击「生成测试用例」后，将先分析测试点再生成用例。")
        st.stop()

    # 已保存提示（显示一次后清除）
    if st.session_state.get("saved_message"):
        st.success("✅ 已保存")
        st.session_state.saved_message = None

    # 测试点清单展示（顶部）
    if test_points:
        with st.expander(f"📋 已识别测试点清单（共 {len(test_points)} 个）", expanded=False):
            for i, p in enumerate(test_points[:80], 1):
                st.markdown(f"{i}. {p}")
            if len(test_points) > 80:
                st.caption(f"… 共 {len(test_points)} 个")

    # 分页与表格（无筛选，直接用全部用例）
    total = len(cases)
    page = st.session_state.get("result_page", 0)
    max_page = max(0, (total - 1) // PER_PAGE)
    page = max(0, min(page, max_page))
    st.session_state.result_page = page
    start = page * PER_PAGE
    end = min(start + PER_PAGE, total)
    page_cases = cases[start:end]
    editing_id = st.session_state.get("editing_case_id")

    # 用例列表表格：逐行渲染；点击编辑则该行变为列表内直接编辑，操作列显示 保存/取消
    TABLE_COL_W = [0.35, 0.4, 1.2, 0.5, 0.45, 1.0, 0.9, 0.9, 1.0, 0.4, 0.35]
    type_opts = ["功能", "边界", "异常", "兼容性", "性能", "安全"]
    pri_opts = ["高", "中", "低"]
    headers = ["序号", "编号", "用例名称", "模块", "类型", "前置条件", "步骤", "测试数据", "预期结果", "优先级", "操作"]
    hcols = st.columns(TABLE_COL_W)
    for hi, h in enumerate(headers):
        hcols[hi].markdown(f"**{h}**")
    st.markdown('<div class="table-scroll-wrap">', unsafe_allow_html=True)
    for i, c in enumerate(page_cases):
        cid = _cell_text(c.get("case_id"))
        idx_show = start + i + 1
        is_editing = editing_id == cid
        rcols = st.columns(TABLE_COL_W)
        rcols[0].write(idx_show)
        rcols[1].write(cid)
        if is_editing:
            # 列表内直接编辑：该行显示输入框，操作列显示 保存、取消
            idx = next((j for j, x in enumerate(cases) if _cell_text(x.get("case_id")) == cid), None)
            if idx is not None:
                ce = cases[idx]
                rcols[2].text_input("用例名称", value=_cell_text(ce.get("case_name")), key=f"inline_name_{cid}", label_visibility="collapsed")
                rcols[3].text_input("模块", value=_get_module(ce), key=f"inline_module_{cid}", label_visibility="collapsed")
                type_val = _cell_text(ce.get("test_type"))
                type_idx = type_opts.index(type_val) if type_val in type_opts else 0
                rcols[4].selectbox("类型", options=type_opts, index=type_idx, key=f"inline_type_{cid}", label_visibility="collapsed")
                rcols[5].text_input("前置条件", value=_cell_text(ce.get("precondition")), key=f"inline_pre_{cid}", label_visibility="collapsed")
                rcols[6].text_area("步骤", value=_cell_text(ce.get("steps")), key=f"inline_steps_{cid}", height=60, label_visibility="collapsed")
                rcols[7].text_input("测试数据", value=_cell_text(ce.get("test_data")), key=f"inline_data_{cid}", label_visibility="collapsed")
                rcols[8].text_area("预期结果", value=_cell_text(ce.get("expected")), key=f"inline_expected_{cid}", height=60, label_visibility="collapsed")
                pri_val = _cell_text(ce.get("priority"))
                pri_idx = pri_opts.index(pri_val) if pri_val in pri_opts else 1
                rcols[9].selectbox("优先级", options=pri_opts, index=pri_idx, key=f"inline_pri_{cid}", label_visibility="collapsed")
                with rcols[10]:
                    if st.button("保存", key=f"save_{cid}_{i}"):
                        st.session_state.test_cases_backup = [dict(x) for x in st.session_state.test_cases]
                        cases[idx].update({
                            "case_name": st.session_state.get(f"inline_name_{cid}", ce.get("case_name") or ""),
                            "module": st.session_state.get(f"inline_module_{cid}", _get_module(ce)),
                            "test_type": st.session_state.get(f"inline_type_{cid}", type_val),
                            "precondition": st.session_state.get(f"inline_pre_{cid}", ce.get("precondition") or ""),
                            "steps": st.session_state.get(f"inline_steps_{cid}", ce.get("steps") or ""),
                            "test_data": st.session_state.get(f"inline_data_{cid}", ce.get("test_data") or ""),
                            "expected": st.session_state.get(f"inline_expected_{cid}", ce.get("expected") or ""),
                            "priority": st.session_state.get(f"inline_pri_{cid}", pri_val),
                        })
                        st.session_state.editing_case_id = None
                        st.session_state.saved_message = True
                        st.rerun()
                    if st.button("取消", key=f"cancel_{cid}_{i}"):
                        st.session_state.editing_case_id = None
                        st.rerun()
        else:
            # 正常展示
            rcols[2].write(_cell_text(c.get("case_name")))
            rcols[3].write(_get_module(c))
            t = _cell_text(c.get("test_type"))
            tag_cls = TYPE_TAG_CLASS.get(t, "tag-other")
            rcols[4].markdown(f'<span class="type-tag {tag_cls}">{_html_esc(t)}</span>', unsafe_allow_html=True)
            rcols[5].write(_cell_text(c.get("precondition")))
            rcols[6].write(_cell_text(c.get("steps")))
            rcols[7].write(_cell_text(c.get("test_data")))
            rcols[8].write(_cell_text(c.get("expected")))
            p = _cell_text(c.get("priority"))
            pri_cls = "tag-pri-high" if p == "高" else ("tag-pri-mid" if p == "中" else "tag-pri-low")
            rcols[9].markdown(f'<span class="priority-tag {pri_cls}">{_html_esc(p)}</span>', unsafe_allow_html=True)
            with rcols[10]:
                if st.button("编辑", key=f"edit_{cid}_{i}"):
                    st.session_state.editing_case_id = cid
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # 底部分页：左下角「共 X 条」，右下角紧凑页签（上一页 1 2 下一页 跳转）
    st.markdown("---")
    pag_left, _, pag_right = st.columns([1, 2, 1])
    with pag_left:
        st.caption(f"共 {total} 条用例")
    with pag_right:
        num_btns = min(max_page + 1, 6)
        pcols = st.columns([0.7] + [0.5] * num_btns + [0.7, 0.5, 0.5])
        with pcols[0]:
            if st.button("‹", disabled=(page <= 0), key="prev_page", help="上一页"):
                st.session_state.result_page = page - 1
                st.session_state.editing_case_id = None
                st.rerun()
        for p in range(num_btns):
            with pcols[1 + p]:
                if p == page:
                    st.caption(f"**{p + 1}**")
                else:
                    if st.button(str(p + 1), key=f"page_{p}"):
                        st.session_state.result_page = p
                        st.session_state.editing_case_id = None
                        st.rerun()
        with pcols[1 + num_btns]:
            if st.button("›", disabled=(page >= max_page), key="next_page", help="下一页"):
                st.session_state.result_page = page + 1
                st.session_state.editing_case_id = None
                st.rerun()
        with pcols[2 + num_btns]:
            jump_page = st.number_input("页", min_value=1, max_value=max(1, max_page + 1), value=page + 1, step=1, key="jump_input", label_visibility="collapsed")
        with pcols[3 + num_btns]:
            if st.button("跳转", key="jump_btn"):
                st.session_state.result_page = int(jump_page) - 1
                st.session_state.editing_case_id = None
                st.rerun()

    # 导出（始终为全部用例）
    st.markdown("---")
    st.markdown("### 导出（全部用例）")
    c1, c2, c3, c4 = st.columns(4)
    full_md = f"# 测试用例\n\n共 {len(cases)} 条。\n\n{to_markdown(cases)}"
    with c1:
        st.download_button("📄 Markdown", data=full_md, file_name="test_cases.md", mime="text/markdown", key="dl_md")
    with c2:
        try:
            st.download_button("📊 Excel", data=to_excel_bytes(cases), file_name="test_cases.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_xlsx")
        except Exception as e:
            st.caption(f"Excel: {e}")
    with c3:
        try:
            st.download_button("📝 Word", data=to_word_bytes(cases), file_name="test_cases.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key="dl_docx")
        except Exception as e:
            st.caption(f"Word: {e}")
    with c4:
        try:
            st.download_button("📕 PDF", data=to_pdf_bytes(cases), file_name="test_cases.pdf", mime="application/pdf", key="dl_pdf")
        except Exception as e:
            st.caption(f"PDF: {e}")


if __name__ == "__main__":
    run()
