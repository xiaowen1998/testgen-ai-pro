# 🧪 TestGen AI V7.0 - 测试用例生成器

基于 **Python + Streamlit + 通义千问（DashScope）** 的测试用例生成工具。采用 **测试点驱动双阶段生成**，先分析测试点再按点生成用例，覆盖更全；V7.0 精简 UI：测试点清单 → 用例表格 → 分页，支持列表内编辑与多格式导出。

---

## 功能特性

### 输入方式（Tabs 切换）
- **📝 文本输入**：多行文本框直接填写需求描述
- **📎 文档上传**：支持 PDF、Word(.docx)、TXT、Markdown，自动解析并填入需求框
- **🔗 网页链接**：输入 URL，点击「抓取」提取正文并填入需求框

### 双阶段生成（测试点驱动）
- **第 1 阶段**：AI 分析需求，输出「测试点清单」
- **第 2 阶段**：按测试点生成用例（每点至少 1 条，复杂点 2～3 条）
- **测试点清单**：顶部可展开查看「已识别测试点清单（共 X 个）」
- **重新生成**：保留当前需求，一键重新执行双阶段

### V7.0 布局（精简）
- **测试点清单**：顶部 expander，可展开/收起
- **用例列表表格**：编号、用例名称、模块、类型、前置条件、步骤、测试数据、预期结果、优先级、操作；类型与优先级带颜色标签；支持横向滚动
- **操作列**：每行「编辑」；点击后在表格下方展开编辑表单（保存/取消）
- **底部分页**：共 X 条用例；上一页 / 页码 / 下一页；支持跳转到指定页；每页 15 条

### 导出
- **Markdown**：原始 .md 表格
- **Excel**：.xlsx（pandas + openpyxl）
- **Word**：.docx 表格（python-docx）
- **PDF**：.pdf 表格（fpdf2）

### 界面
- 紫蓝色渐变标题区（主题可在 `.streamlit/config.toml` 中配置）
- 三种输入方式用 Tabs 切换
- 现代化卡片式布局

---

## 技术栈

| 类别     | 技术 |
|----------|------|
| 语言/框架 | Python 3.8+、Streamlit |
| AI       | 通义千问（OpenAI 兼容 API / DashScope） |
| 文档解析 | PyPDF2（PDF）、python-docx（Word） |
| 网页抓取 | requests、BeautifulSoup4、Playwright（可选） |
| 导出     | pandas、openpyxl、python-docx、fpdf2 |
| 配置     | python-dotenv |

---

## 快速开始

### 1. 克隆并进入项目

```bash
git clone <你的仓库地址>
cd TestgenAI
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

若需抓取 **需 JavaScript 渲染的页面**（如印象笔记、语雀等），请再执行（仅需一次）：

```bash
playwright install chromium
```

### 4. 配置环境变量

在项目根目录创建 `.env`：

```env
# 必填：千问 API 密钥
QWEN_API_KEY=sk-xxxxxxxx
# 可选，默认 qwen-turbo
QWEN_MODEL=qwen-turbo
```

API Key 获取：[阿里云百炼](https://bailian.console.aliyun.com/) 或 [灵积 DashScope](https://dashscope.console.aliyun.com/)。

### 5. 启动应用

```bash
streamlit run app.py
```

浏览器访问 **http://localhost:8501**。

---

## 使用说明

1. 在 **文本输入 / 文档上传 / 网页链接** 任一 Tab 中提供需求内容。
2. （可选）在「测试类型」中多选需要的类型。
3. 点击 **生成测试用例**，等待 AI 先分析测试点再生成用例。
4. 在分页区域查看结果，使用 **上一页 / 下一页** 或跳转页码浏览。
5. 需要修改某条用例时，点击该行的 **编辑**，在下方表单中修改后 **保存** 或 **取消**。
6. 在「导出」区按需下载 **Markdown / Excel / Word / PDF**。

---

## 项目结构

```
TestgenAI/
├── app.py              # Streamlit 主程序（V7.0）
├── requirements.txt    # Python 依赖
├── .env                # 本地配置（勿提交）
├── .streamlit/
│   └── config.toml     # Streamlit 主题与服务器配置
├── vercel.json         # Vercel 部署配置（可选）
└── README.md           # 说明文档
```

---

## 环境变量

| 变量名           | 必填 | 说明                                  |
|------------------|------|---------------------------------------|
| `QWEN_API_KEY`   | 是   | 千问 API 密钥（阿里云百炼/灵积）     |
| `QWEN_MODEL`     | 否   | 模型，默认 `qwen-turbo`              |

---

## 部署（Vercel）

项目包含 `vercel.json`，可部署到 Vercel。在 Vercel 项目设置中配置环境变量 `QWEN_API_KEY`（及可选的 `QWEN_MODEL`）。

---

## 常见问题

- **无法访问 http://localhost:8501**  
  确认已执行 `streamlit run app.py`，且终端无报错。若提示 `streamlit: command not found`，请先激活虚拟环境并执行 `pip install -r requirements.txt`。

- **生成时报错「未配置 QWEN_API_KEY」**  
  在项目根目录创建 `.env`，填入 `QWEN_API_KEY=sk-xxx`。

- **PDF 中文显示异常**  
  建议优先使用 **Word** 或 **Excel** 导出；PDF 由 fpdf2 生成，对中文支持有限。

---

## 注意事项

- 请勿将 `.env` 或真实 API Key 提交到版本库。
- 千问有免费额度，超出后按量计费。
- 生成内容仅供参考，建议人工审阅后再用于正式测试。

---

## License

MIT
