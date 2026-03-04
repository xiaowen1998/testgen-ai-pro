"""
文档解析服务
支持PDF、Word、TXT、Markdown、XMind、图片、URL
"""


import io
import json
import re
import zipfile
from typing import Optional
from urllib.parse import urlparse


class DocumentParserError(Exception):
    """文档解析异常"""
    pass


class DocumentParser:
    """文档解析器"""
    
    def parse(self, uploaded_file) -> str:
        """
        解析上传的文件
        """
        name = (uploaded_file.name or "").lower()
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        
        if name.endswith(".pdf"):
            return self._parse_pdf(raw)
        if name.endswith(".docx"):
            return self._parse_docx(raw)
        if name.endswith(".txt") or name.endswith(".md") or name.endswith(".markdown"):
            return self._parse_text(raw)
        if name.endswith(".xmind"):
            return self._parse_xmind(raw)
        if name.endswith(".zip"):
            return self._parse_zip(raw)
        
        raise DocumentParserError(f"不支持的文件格式: {name}")
    
    def parse_url(self, url: str) -> str:
        """
        解析网页URL
        """
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            raise DocumentParserError("缺少必要的依赖：requests, beautifulsoup4")
        
        try:
            resp = requests.get(
                url.strip(),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=15,
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            
            text = self._extract_from_html(resp.text)
            
            # 如果内容太短，可能是JS渲染页面
            if not text or len(text) < 80:
                text = self._fetch_with_playwright(url)
            
            # 检查是否需要登录
            if self._is_login_page(text):
                raise DocumentParserError("页面需要登录，无法自动抓取")
            
            return text
            
        except Exception as e:
            raise DocumentParserError(f"抓取失败: {e}")
    
    def parse_image(self, uploaded_image) -> str:
        """
        解析图片（调用多模态AI）
        """
        from src.services.ai_service import AIService
        
        service = AIService()
        image_bytes = uploaded_image.getvalue()
        mime_type = getattr(uploaded_image, "type", None) or "image/jpeg"
        if not mime_type.startswith("image/"):
            mime_type = "image/jpeg"
        
        return service.recognize_image(image_bytes, mime_type)
    
    def _parse_pdf(self, file_bytes: bytes) -> str:
        """解析PDF"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise DocumentParserError("缺少依赖：PyPDF2")
        
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            parts = [p.extract_text() for p in reader.pages if p.extract_text()]
            return "\n\n".join(parts).strip() if parts else ""
        except Exception as e:
            raise DocumentParserError(f"PDF解析失败: {e}")
    
    def _parse_docx(self, file_bytes: bytes) -> str:
        """解析Word文档"""
        try:
            from docx import Document
        except ImportError:
            raise DocumentParserError("缺少依赖：python-docx")
        
        try:
            if not file_bytes or len(file_bytes) < 4:
                raise ValueError("文件为空或过短")
            if file_bytes[:2] != b"PK":
                raise ValueError(
                    "该文件不是有效的 .docx 格式。请确认："
                    "1) 文件为 Office 2007 及以上另存为的 .docx；"
                    "2) 若为旧版 .doc，请用 Word 另存为 .docx 后再上传。"
                )
            
            buf = io.BytesIO(file_bytes)
            buf.seek(0)
            doc = Document(buf)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
        except Exception as e:
            raise DocumentParserError(f"Word解析失败: {e}")
    
    def _parse_text(self, file_bytes: bytes) -> str:
        """解析文本文件"""
        for enc in ("utf-8", "gbk", "gb2312"):
            try:
                return file_bytes.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        raise DocumentParserError("无法识别文件编码")
    
    def _parse_xmind(self, file_bytes: bytes) -> str:
        """解析XMind文件"""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
                # 查找content.json
                content_name = None
                for n in z.namelist():
                    if "content.json" in n:
                        content_name = n
                        break
                
                if not content_name:
                    raise ValueError("未在XMind文件中找到content.json")
                
                with z.open(content_name) as f:
                    data = json.load(f)
            
            parts = []
            if isinstance(data, list):
                for sheet in data:
                    root = sheet.get("rootTopic") if isinstance(sheet, dict) else None
                    if root:
                        self._extract_xmind_topic(root, parts)
            elif isinstance(data, dict) and data.get("rootTopic"):
                self._extract_xmind_topic(data["rootTopic"], parts)
            
            text = "\n".join(parts).strip()
            if not text:
                raise ValueError("XMind中未解析出有效文本")
            
            # 限制长度
            from src.config import XMIND_MAX_EXTRACT_CHARS
            if len(text) > XMIND_MAX_EXTRACT_CHARS:
                text = text[:XMIND_MAX_EXTRACT_CHARS] + \
                       f"\n\n（以上内容已截断，仅保留前 {XMIND_MAX_EXTRACT_CHARS} 字）"
            
            return text
            
        except zipfile.BadZipFile as e:
            raise DocumentParserError(f"不是有效的XMind/ZIP文件: {e}")
        except Exception as e:
            raise DocumentParserError(f"XMind解析失败: {e}")
    
    def _extract_xmind_topic(self, node: dict, parts: list):
        """递归提取XMind节点文本"""
        title = node.get("title") or node.get("text") or ""
        if isinstance(title, str) and title.strip():
            parts.append(title.strip())
        
        children = node.get("children")
        if isinstance(children, dict):
            for key in ("attached", "summary", "floating"):
                arr = children.get(key)
                if isinstance(arr, list):
                    for c in arr:
                        self._extract_xmind_topic(c, parts)
        elif isinstance(children, list):
            for c in children:
                self._extract_xmind_topic(c, parts)
    
    def _parse_zip(self, file_bytes: bytes) -> str:
        """解析ZIP压缩包（内部文档）"""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
                out_parts = []
                for name in z.namelist():
                    # 跳过系统文件
                    if name.startswith("__MACOSX") or "/." in name or name.endswith("/"):
                        continue
                    
                    base = (name.split("/")[-1] or name).lower()
                    try:
                        raw = z.read(name)
                    except Exception:
                        continue
                    
                    if not raw or len(raw) < 2:
                        continue
                    
                    try:
                        if base.endswith(".pdf"):
                            out_parts.append(self._parse_pdf(raw))
                        elif base.endswith(".docx"):
                            out_parts.append(self._parse_docx(raw))
                        elif base.endswith((".txt", ".md", ".markdown")):
                            out_parts.append(self._parse_text(raw))
                        elif base.endswith(".xmind"):
                            out_parts.append(self._parse_xmind(raw))
                    except Exception:
                        continue
                
                text = "\n\n".join(p for p in out_parts if p.strip()).strip()
                if not text:
                    raise ValueError("ZIP内未找到可解析的文档")
                return text
                
        except zipfile.BadZipFile as e:
            raise DocumentParserError(f"不是有效的ZIP文件: {e}")
    
    def _extract_from_html(self, html: str) -> str:
        """从HTML提取正文"""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            # 简单正则提取
            text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
            text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            return re.sub(r"\s+", " ", text).strip()
        
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body = soup.find("body") or soup
        text = body.get_text(separator="\n", strip=True) if body else ""
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    
    def _fetch_with_playwright(self, url: str) -> str:
        """使用Playwright抓取JS渲染页面"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise DocumentParserError(
                "该页面需执行JavaScript才能显示内容。请安装Playwright："
                "pip install playwright && playwright install chromium"
            )
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(url, wait_until="load", timeout=25000)
                    page.wait_for_timeout(4000)
                    html = page.content()
                    return self._extract_from_html(html)
                finally:
                    browser.close()
        except Exception as e:
            raise DocumentParserError(f"Playwright抓取失败: {e}")
    
    def _is_login_page(self, text: str) -> bool:
        """判断是否为登录页面"""
        if not text or len(text) > 800:
            return False
        
        t = text.strip().lower()
        keywords = ("登录", "请登录", "未登录", "login", "sign in", "登录以继续")
        return any(kw in t for kw in keywords)