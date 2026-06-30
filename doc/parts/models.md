# 项目模型说明

## 模型概览

| 模型 | 类型 | 负责任务 |
|------|------|----------|
| BGE-M3 | Embedding 模型 | 文本向量化，将文档和查询转换为向量用于相似度检索 |
| BGE-Reranker-Large | 重排序模型 | 对初步检索结果进行精排，提升相关性 |
| nlp_bert_document-segmentation_chinese-base | 文档分割模型 | 智能分割中文文档，识别段落边界 |
| bert_query_classifier | 查询分类器 | 对用户查询进行意图分类，选择检索策略 |
| Qwen-Plus | LLM (通过 DashScope API) | 根据检索到的上下文生成最终回答 |

## RAG 流程

1. 文档处理时用 **文档分割模型** 切分文本
2. 用 **BGE-M3** 生成向量存入 Milvus
3. 查询时先用 **查询分类器** 判断意图
4. 用 **BGE-M3** 向量检索 + **BGE-Reranker** 精排
5. 最后用 **Qwen-Plus** 生成回答

---

## 为什么选择 BGE-M3

BGE-M3 适合本项目的核心原因是：它能用一个模型同时生成 dense 向量和 sparse 向量，兼顾语义召回和关键词召回。

### dense/sparse 双向量优势

- **dense 向量适合语义检索**：用户问题和文档表达方式不完全一致时，仍然可以根据语义相似度召回相关内容。例如用户问“Python 怎么捕获错误”，文档中写的是“try except 异常处理”，dense 向量仍然有机会匹配上。
- **sparse 向量适合关键词检索**：IT 教育资料里有大量课程名、技术名、英文缩写和专有名词，例如 MySQL、Redis、Django、Vue。sparse 向量能保留这类关键词匹配能力，避免只靠语义向量时漏召回。
- **同一个模型统一生成**：不需要额外维护一套 embedding 模型加一套 BM25 检索，BGE-M3 一次编码即可产出 dense/sparse 表示，系统链路更简单。
- **适合 Milvus 混合检索**：项目中的 Milvus 集合同时存储 `dense_vector` 和 `sparse_vector`，正好对应 BGE-M3 的双向量输出。

### 中文和长文本能力

- **中文和中英混合文本友好**：项目资料以中文课程内容为主，同时包含大量英文技术词，BGE-M3 对这类中英混合检索场景比较适合。
- **支持较长输入**：BGE-M3 支持最长 8192 token 的输入。虽然项目里会先做文档切块，但模型本身对较长文本的适应能力更好，适合课程讲义、PDF、技术文档等知识库资料。

### 模型大小和部署成本

- **模型大小适中**：项目本地的 `rag_qa/models/bge-m3` 目录约 2.14GB，主要权重文件 `pytorch_model.bin` 约 2.1GB。相比更大的生成式大模型，BGE-M3 的本地部署成本更低。
- **可本地部署**：文档向量化和查询向量化都可以在本地完成，不需要把知识库内容发送到外部 embedding API，数据安全和调用成本更可控。
- **向量可预计算**：文档入库时先把文档向量算好并存入 Milvus，在线查询时只需要计算用户问题的向量，再做向量检索，因此在线成本比每次让大模型直接阅读大量文档低。
- **与 Reranker 分工明确**：BGE-M3 负责快速召回候选文档，BGE-Reranker 负责精排。这样既保证召回速度，又能通过后处理提高最终上下文质量。

面试中可以总结为：

> 选择 BGE-M3 是因为它一个模型就能同时生成 dense 和 sparse 向量，dense 负责语义相似，sparse 负责关键词和专有名词匹配，非常适合 IT 教育问答这种中文加技术词混合的知识库场景。同时它可以本地部署，模型目录约 2.14GB，文档向量可以预计算后存入 Milvus，部署成本和在线调用成本都比较可控。

---

## 为什么使用 BGE-Reranker-Large

BGE-Reranker-Large 主要用于解决第一阶段向量召回不够精细的问题。BGE-M3 负责从 Milvus 中快速召回候选文档，Reranker 再对候选文档做精排，把最相关的内容排到前面。

### 精排优势

- **相关性判断更准确**：Reranker 是 Cross-Encoder，会把 query 和 document 拼接后一起输入模型，让两者在 Transformer 层内部充分交互，因此比单纯计算向量相似度更能判断文档是否真正回答了用户问题。
- **能捕捉细粒度语义关系**：Bi-Encoder 的 query 和 doc 是分别编码的，主要依赖最终向量距离；Reranker 可以让 query 中的每个 token 直接和文档 token 交互，更适合判断复杂问题、否定表达、限定条件等细节。
- **减少无关上下文进入大模型**：第一阶段向量检索会尽量多召回候选结果，里面可能混入相似但不相关的文档。Reranker 可以把弱相关内容排到后面，减少上下文污染。
- **提升最终回答质量**：进入 LLM 的上下文更准确，模型生成答案时更容易基于正确资料回答，降低答非所问和幻觉风险。
- **适合两阶段检索架构**：先用 BGE-M3 快速召回 top 100，再用 BGE-Reranker 精排 top 5，可以在速度和准确率之间取得平衡。

### 模型大小和部署成本

- **只在查询阶段使用**：Reranker 不参与文档入库，也不需要把结果存成向量，只对召回后的少量候选文档打分，因此部署压力主要集中在在线查询阶段。
- **计算成本高于向量相似度**：它需要对 query 和每个候选文档重新做一次 Cross-Encoder 推理，所以速度比 BGE-M3 向量检索慢，不适合直接对全量文档检索。
- **候选集可控后成本可控**：项目中先用 BGE-M3 缩小候选范围，再让 Reranker 只处理 top 100 这类小规模结果，避免对全量知识库逐条打分。
- **本地部署成本可接受**：项目本地的 `rag_qa/models/bge-reranker-large` 目录约 2.09GB，和 BGE-M3 同属可本地部署模型，不依赖外部重排序 API。

面试中可以总结为：

> BGE-M3 适合快速召回，但它是 Bi-Encoder，query 和文档分别编码，只能通过向量相似度粗略判断相关性。BGE-Reranker-Large 是 Cross-Encoder，会把 query 和候选文档拼接后一起输入模型，让二者在 Transformer 内部充分交互，所以相关性判断更准确。我们用它对 BGE-M3 召回的候选结果做精排，可以减少无关上下文进入大模型，提高最终回答质量。

---

## BGE-M3 vs BGE-Reranker-Large

### 架构对比

| 特性 | BGE-M3 (Bi-Encoder) | BGE-Reranker-Large (Cross-Encoder) |
|------|---------------------|-----------------------------------|
| 输入方式 | Query 和 Doc 分别编码 | Query + Doc 拼接后一起编码 |
| 交互深度 | 仅在最后计算相似度 | 所有 Transformer 层深度交互 |
| 速度 | 快（可预计算向量） | 慢（每对都要重新计算） |
| 精度 | 较低 | 更高 |

### 工作原理

**BGE-M3 (Bi-Encoder)**
```
encode(query) → vec1
encode(doc)   → vec2
cosine(vec1, vec2) → 相似度分数
```
- Query 和 Doc 独立编码，向量可以预先计算并存储
- 相似度计算是纯数学运算（余弦相似度）
- 模型的能力体现在：训练时优化让语义相近的文本向量更近

**BGE-Reranker-Large (Cross-Encoder)**
```
输入: [CLS] query [SEP] document [SEP]
      ↓
24 层 Transformer（query 和 doc 的 token 相互 attention）
      ↓
[CLS] 向量 → 分类头 → 相关性分数
```
- Query 和 Doc 在 Transformer 内部深度交互
- 每个 query token 都能直接 attend 到 doc 的每个 token
- 模型直接输出相关性分数，没有独立的相似度计算步骤

### 为什么 Reranker 更准确

Bi-Encoder 的 query 和 doc 向量是独立生成的，无法捕捉细粒度的词级交互。Cross-Encoder 让每个 query token 都能直接 attend 到 doc 的每个 token，能捕捉更复杂的语义匹配关系。

### 典型使用流程

```
用户查询 → BGE-M3 向量检索 (top 100) → BGE-Reranker 精排 (top 5) → LLM 生成
```

先用快速的向量检索召回候选，再用精确但慢的 Reranker 筛选最相关的结果。这是标准的两阶段检索架构。

### 关于 BGE-M3 的相关度计算

BGE-M3 的"相关度能力"体现在**编码质量**上，而不是相似度公式上：

- **模型的能力**：学习如何把语义相近的文本映射到向量空间中相近的位置
- **相似度计算**：余弦相似度、点积等是纯数学运算，和模型无关

训练阶段：
- 正样本对 (query, relevant_doc) → 优化让向量更近
- 负样本对 (query, irrelevant_doc) → 优化让向量更远

换个差的模型，同样的余弦相似度公式就不管用了。
