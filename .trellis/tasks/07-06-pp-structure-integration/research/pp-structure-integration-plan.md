# PP-Structure 接入调研

## 1. 当前代码链路

当前仓库的文档解析链路是：

`document_processor.py` 选 loader
-> `edu_*loader.py` 提取文本 / OCR
-> LangChain `Document`
-> 父子块切分
-> 向量化 / Milvus 入库

关键接入点：

* `rag_qa/core/document_processor.py`
  * 负责根据扩展名选择 loader，是最外层入口。
* `rag_qa/edu_document_loaders/edu_ocr.py`
  * 当前只暴露 `get_ocr()`，返回 RapidOCR 实例。
* `rag_qa/edu_document_loaders/edu_pdfloader.py`
  * 当前是 `PyMuPDF` 文本提取 + 页面大图 OCR。
* `rag_qa/edu_document_loaders/edu_imgloader.py`
  * 当前整图走 RapidOCR。
* `rag_qa/edu_document_loaders/edu_docloader.py`
  * 当前提取正文、表格、嵌入图片，图片走 RapidOCR。
* `rag_qa/edu_document_loaders/edu_pptloader.py`
  * 当前提取文本框、表格、图片，图片走 RapidOCR。

## 2. 最小可行接入方案

建议先上“混合方案”，不要一步把所有 OCR 都替掉。

### 2.1 首期范围

只改两类：

* PDF
* 图片

原因：

* 当前复杂版式痛点主要集中在扫描 PDF、图文混排 PDF、表格类图片。
* 这两类最能体现 PP-Structure 的版面分析、表格识别和阅读顺序恢复价值。
* 改动面可控，不会一下冲击 Word/PPT 的现有稳定逻辑。

### 2.2 接法

在 `edu_ocr.py` 增加新的结构化引擎工厂，例如：

* `get_rapid_ocr()`
* `get_pp_structure()`

`get_pp_structure()` 建议首期参数：

* `table=True`
* `ocr=True`
* `layout=True`
* `formula=False`
* `show_log=False`

### 2.3 PDF 处理建议

`edu_pdfloader.py` 不要整体推翻，建议改成双路径：

1. 文本型 PDF
   * 保留 `PyMuPDF` 的 `page.get_text("text")`
2. 扫描页 / 复杂图文页
   * 页面转图后交给 PP-Structure

推荐判断方式：

* 当前页直接提取文本过少
* 或页内图片占比高
* 或用户显式指定走结构化解析

这样做的好处是：

* 文本型 PDF 仍然快
* 复杂页再进入重解析链路

### 2.4 图片处理建议

`edu_imgloader.py` 可以直接切到 PP-Structure，因为图片本身就是结构化 OCR 的核心场景。

输出时不要只拼纯文本，建议先保留块级结构，再决定是否：

* 转纯文本
* 转 Markdown
* 表格块转 HTML / Markdown 表格

## 3. Word / PPT 建议

首期不建议整份 Word / PPT 全量交给 PP-Structure。

更稳的方案是：

* 保留当前 `python-docx` / `python-pptx` 的正文、表格文本提取
* 仅把嵌入图片 OCR 从 RapidOCR 替换成 PP-Structure

后续如果确实要统一复杂版式：

* 方案 A：先转 PDF / 图片，再统一交给 PP-Structure
* 方案 B：继续保留原生结构提取，PP-Structure 只处理图片块

对当前仓库来说，方案 B 更务实。

## 4. 数据结构和元数据建议

当前仓库已有元数据：

* `source`
* `file_path`
* `timestamp`
* `parent_id`
* `parent_content`
* `id`

如果接入 PP-Structure，建议至少新增：

* `parse_method`
  * `rapidocr` / `ppstructure`
* `page`
* `block_type`
  * `text` / `table` / `title` / `image`
* `block_bbox`
* `block_order`
* `ocr_confidence`
* `layout_score`
* `table_html`
* `need_review`

其中最重要的是：

* `block_type`
* `ocr_confidence`
* `page`
* `parse_method`

因为这四个字段最直接影响后续质量控制、追溯和面试说法。

## 5. 对切分和入库的影响

当前 `document_processor.py` 默认假设 loader 输出的是一大段 `page_content`。

PP-Structure 接入后，建议分两阶段：

### 阶段一

仍然把结构化结果整理为一段文本后输出给现有切分器。

优点：

* 改动最小
* 后续向量库和检索逻辑几乎不用动

缺点：

* 会损失部分结构化收益

### 阶段二

按块输出，或者先拼成更接近 Markdown 的结构文本，再做切分。

优点：

* 标题、正文、表格、图片说明可以保留更多层次

缺点：

* 切分规则、清洗逻辑、父子块策略都要一起调

对当前项目，建议先做阶段一。

## 6. 安装和环境建议

优先建议 PP-Structure V2 风格接法，原因是更贴近当前代码。

官方文档显示：

* 需要先安装 PaddlePaddle
* 再安装 `paddleocr`
* GPU / CPU 依赖不同

项目层面的实际建议：

* 本地开发先用 CPU 跑通
* 测试 / 生产如果解析量大，再切 GPU
* 不要在在线问答链路临时跑重 OCR，尽量保持离线入库

## 7. 风险

### 7.1 依赖更重

相比 RapidOCR，PP-Structure 需要更多模型和更大的安装体积。

### 7.2 首次模型下载

首跑会下载模型，离线环境和 CI 环境都要提前考虑镜像或缓存。

### 7.3 CPU 性能压力

如果在 CPU 环境下对整页 PDF 全跑 PP-Structure，速度会明显下降。

### 7.4 结果结构变化

现在代码只接受“文本行拼接结果”，PP-Structure 返回的是块级结构化对象，需要加一层转换逻辑。

### 7.5 口径和代码不一致

仓库文档里已经有很多 PP-Structure 的包装说法，但当前真实代码还没接入。若不落地实现，面试时容易被继续追问穿透。

## 8. 推荐实施顺序

### 第一阶段

* 新增 `get_pp_structure()`
* 改 `edu_imgloader.py`
* 改 `edu_pdfloader.py`
* 增加基础元数据

### 第二阶段

* 表格块转文本 / Markdown 规则
* 增加 `ocr_confidence`、`need_review`
* 优化扫描页判断和降级逻辑

### 第三阶段

* 视需要扩展到 Word / PPT
* 评估是否让 loader 输出更强结构化文本

## 9. 结论

当前仓库最合适的路线不是“全量替换 RapidOCR”，而是：

* 先在 PDF 和图片上引入 PP-Structure
* 保留现有 `document_processor.py`、父子块切分和入库主流程
* 把 PP-Structure 当成更强的结构化 OCR 后端
* 先解决复杂 PDF / 表格 / 图文混排痛点，再考虑 Word / PPT 全量统一

这样改动最小，收益也最明确。

## 10. 参考

* PaddleOCR PP-Structure Quick Start  
  https://www.paddleocr.ai/v2.9.1/en/ppstructure/quick_start.html
* PP-StructureV3 Pipeline Tutorial  
  https://paddlepaddle.github.io/PaddleX/latest/en/pipeline_usage/tutorials/ocr_pipelines/PP-StructureV3.html
* PaddlePaddle Installation Guide  
  https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/paddlepaddle_installation.en.md
