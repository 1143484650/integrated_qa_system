# Research PP-Structure integration

## Goal

调研当前项目如果要接入 PP-Structure，应该如何以最小风险落地到现有文档解析链路中，并形成一套可执行的分阶段接入方案。

## What I already know

* 当前项目文档解析入口在 `rag_qa/core/document_processor.py`。
* 当前 OCR 引擎在 `rag_qa/edu_document_loaders/edu_ocr.py`，优先使用 `rapidocr_paddle`，降级到 `rapidocr_onnxruntime`。
* 当前 PDF / Word / PPT / 图片分别由 `edu_pdfloader.py`、`edu_docloader.py`、`edu_pptloader.py`、`edu_imgloader.py` 处理。
* 当前文档统一转为 LangChain `Document` 后，再做父子块切分并进入向量化入库。
* 当前项目代码里的真实解析链路是“轻量文本提取 + OCR 补充”，还没有接入 PP-Structure。
* 仓库文档里已经有 PP-Structure 相关包装和替代方案笔记，但实际代码尚未落地。

## Assumptions

* 本次目标是先形成方案，不直接改业务代码。
* 首期接入优先覆盖 PDF 和图片，不一次性重做全部格式。
* 项目更适合先接 PP-Structure V2 风格接口，而不是一步切到更重的 V3 全量流水线。

## Open Questions

* 是否需要在下一步直接进入代码改造。
* 是否希望把 PP-Structure 同时作为面试口径和真实实现方案统一起来。

## Requirements

* 明确当前代码中的接入点和受影响文件。
* 给出最小可行接入方案，优先覆盖 PDF 和图片。
* 说明 Word / PPT 的建议处理方式。
* 说明新增元数据字段和后续向量入库影响。
* 说明安装、性能、兼容性和工程风险。

## Acceptance Criteria

* [ ] 给出基于当前仓库的 PP-Structure 接入路径
* [ ] 明确首期最小改动范围
* [ ] 明确后续扩展范围和风险
* [ ] 研究结果写入 `research/` 目录

## Definition of Done

* 研究结论已落盘
* 方案和现有代码结构对齐
* 明确不直接修改生产代码

## Out of Scope

* 本次不直接实现 PP-Structure 接入代码
* 本次不调整向量检索和生成链路
* 本次不处理完整部署自动化

## Technical Notes

* 关键文件：
  * `rag_qa/core/document_processor.py`
  * `rag_qa/edu_document_loaders/edu_ocr.py`
  * `rag_qa/edu_document_loaders/edu_pdfloader.py`
  * `rag_qa/edu_document_loaders/edu_imgloader.py`
  * `rag_qa/edu_document_loaders/edu_docloader.py`
  * `rag_qa/edu_document_loaders/edu_pptloader.py`
* 参考文档：
  * `doc/parts/ocr.md`
  * `doc/parts/ocr_alternatives.md`
  * `doc/面试/项目包装/印刷企业内部知识库问答系统_文档入库细节与质量把控.md`
