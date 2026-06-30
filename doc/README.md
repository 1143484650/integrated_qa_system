# integrated_qa_system 文档入口

## 顶层文档

| 文档                        | 说明                     |
| ------------------------- | ---------------------- |
| `architecture.md`         | 查询流程、文档入库流程、核心模型和目录结构。 |
| `technical_challenges.md` | 技术难点、工程取舍、风险点和后续优化方向。  |

## 模块文档

`parts/` 目录按模块拆开说明，适合查具体代码职责。

| 文档 | 说明 |
| --- | --- |
| `parts/query_flow.md` | 一次用户查询从接口到答案返回的完整链路。 |
| `parts/api_interface.md` | `app.py`、`api.py`、`use_api.py` 的接口职责。 |
| `parts/mysql_bm25_redis.md` | MySQL 标准问答、Redis 缓存和 BM25 检索。 |
| `parts/rag_generation.md` | `new_rag_system.py` 中的 RAG 答案生成流程。 |
| `parts/strategy_selection.md` | 专业咨询问题如何选择检索策略。 |
| `parts/vector_store.md` | Milvus 集合、向量字段、过滤和重排。 |
| `parts/hybrid_search.md` | dense/sparse 混合检索的作用。 |
| `parts/parent_child_chunking.md` | 父子块切分为什么这样设计。 |
| `parts/models.md` | 项目中用到的模型和职责边界。 |
| `parts/ocr.md` | PDF、PPT、Word、图片等资料的 OCR 入库。 |
| `parts/ocr_alternatives.md` | OCR 方案对比和替代选择。 |

## 其他目录

| 目录 | 说明 |
| --- | --- |
| `面试/` | 面试题、项目包装、业务讲解材料。 |
| `拓展/` | 高并发等扩展主题。 |

## 快速定位

- 想知道“用户提问后系统怎么跑”：看 `parts/query_flow.md`。
- 想知道“为什么先查 MySQL”：看 `parts/mysql_bm25_redis.md`。
- 想知道“RAG 最后怎么生成答案”：看 `parts/rag_generation.md`。
- 想知道“Milvus 存了什么”：看 `parts/vector_store.md`。
- 想知道“接口怎么调用”：看 `parts/api_interface.md`。
- 想准备答辩：看 `technical_challenges.md` 和 `面试/`。
