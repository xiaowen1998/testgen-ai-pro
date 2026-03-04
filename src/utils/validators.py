"""
数据校验工具函数
"""

import re
from typing import Optional, Tuple


def validate_case_id(case_id: str) -> Tuple[bool, str]:
    """校验用例编号格式"""
    if not case_id:
        return False, "用例编号不能为空"
    if not re.match(r"^TC\d{3}$", case_id):
        return False, "用例编号格式应为 TCXXX（如 TC001）"
    return True, ""


def validate_test_point_format(text: str) -> list[Tuple[int, str]]:
    """
    从文本中解析测试点
    返回: [(序号, 描述), ...]
    """
    points = []
    lines = text.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 匹配 "测试点1：xxx" 或 "测试点1: xxx"
        m = re.match(r"测试点\s*(\d+)\s*[：:]\s*(.+)", line, re.I)
        if m:
            num = int(m.group(1))
            desc = m.group(2).strip()
            points.append((num, desc))
            continue
        
        # 匹配 "1. xxx" 或 "1、xxx"
        m = re.match(r"(\d+)[\.．、]\s*(.+)", line)
        if m:
            num = int(m.group(1))
            desc = m.group(2).strip()
            points.append((num, desc))
    
    return points


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除非法字符"""
    # 移除路径分隔符和其他非法字符
    filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
    # 限制长度
    if len(filename) > 200:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:200] + ("." + ext if ext else "")
    return filename


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """截断文本"""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def cell_text(s: Optional[str]) -> str:
    """表格单元格文本处理"""
    if not s:
        return "-"
    return str(s).replace("\n", " ").replace("|", "｜").strip() or "-"


def escape_html(s: Optional[str]) -> str:
    """HTML转义"""
    if not s:
        return ""
    # 使用replace链式调用，避免引号问题
    result = str(s)
    result = result.replace("&", "&#38;")
    result = result.replace("<", "&#60;")
    result = result.replace(">", "&#62;")
    result = result.replace('"', "&#34;")
    return result