# OCR 开源替代方案

## 推荐项目

| 项目 | 特点 | 适合场景 | GitHub |
|------|------|----------|--------|
| **MinerU** | 上海 AI Lab 出品，PDF→Markdown，版面/表格/公式全支持 | RAG 文档处理首选 | opendatalab/MinerU |
| **Marker** | PDF→Markdown，速度快，效果好 | 大批量 PDF 转换 | VikParuchuri/marker |
| **Unstructured** | 通用文档解析，支持 PDF/Word/PPT/HTML 等 | 多格式统一处理 | Unstructured-IO/unstructured |
| **Pix2Text** | 版面分析 + 文本/表格/公式 OCR 一体化 | 复杂文档 | breezedeus/Pix2Text |
| **PP-StructureV2** | PaddleOCR 官方，版面/表格/公式 | 和现有代码兼容 | PaddlePaddle/PaddleOCR |

## 与当前项目对比

| 功能 | 当前项目 (RapidOCR) | MinerU | PP-StructureV2 |
|------|---------------------|--------|----------------|
| 文本提取 | ✅ | ✅ | ✅ |
| 图片 OCR | ✅ | ✅ | ✅ |
| 表格结构 | ❌ 丢失 | ✅ Markdown 表格 | ✅ HTML 表格 |
| 公式识别 | ❌ | ✅ LaTeX | ✅ LaTeX |
| 版面分析 | ❌ | ✅ | ✅ |
| 阅读顺序 | 部分 | ✅ 智能排序 | ✅ |
| 安装大小 | ~100MB | ~2GB | ~1.5-2GB |

## MinerU 使用示例

```python
from magic_pdf.pipe.UNIPipe import UNIPipe

# PDF → 结构化 Markdown
pipe = UNIPipe(pdf_bytes)
pipe.pipe_classify()
pipe.pipe_parse()
md_content = pipe.pipe_mk_markdown()
```

## PP-StructureV2 使用示例

```python
from paddleocr import PPStructure

engine = PPStructure(
    table=True,           # 表格识别
    ocr=True,             # 文字识别
    layout=True,          # 版面分析
    recovery=True,        # 版面恢复
    lang='ch',
    use_gpu=True
)

result = engine("document.pdf")
# 自动识别：文本、表格、图片、标题、列表、公式等
```

不加载公式模型可省 500MB：
```python
engine = PPStructure(formula=False)
```

## Pix2Text 使用示例

```python
from pix2text import Pix2Text

p2t = Pix2Text()
result = p2t.recognize_pdf("document.pdf")  # 自动处理文本/表格/公式
```

## 迁移建议

1. **最小改动**：用 PP-StructureV2 替换 RapidOCR，API 类似，和 PaddleOCR 生态兼容
2. **最佳效果**：用 MinerU，专为 RAG 设计，输出直接是 Markdown
3. **轻量方案**：用 Marker，速度快，依赖少
