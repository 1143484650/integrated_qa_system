# OCR 模块笔记

## 架构

```
OCR 引擎层 (edu_ocr.py)
    ↓
文档加载层 (edu_pdfloader.py / edu_imgloader.py / edu_pptloader.py / edu_docloader.py)
    ↓
文档处理层 (document_processor.py)
```

## OCR 引擎 — edu_ocr.py

使用 RapidOCR（PaddleOCR 模型的轻量封装）：

```python
from rapidocr_paddle import RapidOCR      # GPU 版，底层用 PaddlePaddle 推理
from rapidocr_onnxruntime import RapidOCR  # CPU 版，底层用 ONNX Runtime 推理
```

| 引擎 | 适用场景 | 安装包大小 |
|------|----------|-----------|
| rapidocr_paddle | 有 GPU，追求速度 | ~100MB |
| rapidocr_onnxruntime | 只有 CPU，资源占用低 | ~100MB |

OCR 内部三个模型：
- **det**（检测）：找出图片中文字区域的位置
- **cls**（分类）：判断文字方向（正向/倒置）
- **rec**（识别）：把图像转成文字

## OCR 返回结构

```python
result, _ = ocr(img)
# result 结构：
# [
#   [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], "识别的文字", 置信度],
#   ...
# ]
# line[0] = 四个角坐标（文字框位置）
# line[1] = 识别的文字内容
# line[2] = 置信度分数
```

项目中只取文字内容：
```python
ocr_result = [line[1] for line in result]  # 丢弃位置和置信度
```

## PDF 加载 — edu_pdfloader.py

处理两种 PDF：

**文本型 PDF**：直接提取
```python
text = page.get_text("text")  # PyMuPDF 直接提取
```

**扫描型 PDF**：图片 OCR
```python
img_list = page.get_image_info(xrefs=True)  # 获取页面中的图片
for img in img_list:
    # 只处理大图（宽高超过页面 60%）
    if (bbox[2] - bbox[0]) / page.rect.width < 0.6:
        continue
    pix = fitz.Pixmap(doc, xref)  # 提取图片
    result, _ = ocr(img_array)     # OCR 识别
```

**关键参数**：
```python
PDF_OCR_THRESHOLD = (0.6, 0.6)  # 图片宽高 > 页面 60% 才 OCR
```

**旋转处理**：如果页面有旋转角度，会先旋转图片再 OCR。

## 图片加载 — edu_imgloader.py

最简单，直接 OCR：
```python
def img2text(self):
    ocr = get_ocr()
    result, _ = ocr(self.img_path)
    ocr_result = [line[1] for line in result]
    return "\n".join(ocr_result)
```

## 支持的文件类型

| 扩展名 | 加载器 |
|--------|--------|
| .txt | TextLoader |
| .pdf | OCRPDFLoader |
| .docx | OCRDOCLoader |
| .ppt/.pptx | OCRPPTLoader |
| .jpg/.png | OCRIMGLoader |

## 识别效果

| 场景 | 效果 |
|------|------|
| 印刷体中文/英文 | 优秀，准确率 95%+ |
| 手写体 | 一般 |
| 表格 | 能识别文字，结构丢失 |
| 公式 | 差 |
| 模糊/倾斜图片 | 下降明显 |

## 当前局限

1. **只取文字**：丢弃了位置信息，表格列关系丢失
2. **无版面分析**：多栏排版可能顺序错乱
3. **无特殊处理**：公式、代码块效果差
4. **无预处理**：没有去噪、增强等图像预处理
