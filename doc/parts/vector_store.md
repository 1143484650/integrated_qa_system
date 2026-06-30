# Milvus 向量库模块笔记

## 模块定位

Milvus 向量库模块位于 `rag_qa/core/vector_store.py`。

它是 RAG 检索阶段的核心执行层，主要负责三件事：

1. 连接 Milvus。
2. 创建或加载 collection。
3. 存储文档向量，并执行混合检索 + Reranker 精排。

它不负责文档解析，也不负责最终答案生成：

```text
document_processor.py  ->  生成文档块和元数据
vector_store.py        ->  存向量、查向量、重排序
new_rag_system.py      ->  组织检索结果并调用大模型生成答案
```

## 初始化流程

`VectorStore` 初始化时会读取配置、加载模型并连接 Milvus：

```text
VectorStore()
    ↓
读取 Milvus 配置
    ↓
加载 BGE-M3 embedding 模型
    ↓
加载 BGE-Reranker-Large
    ↓
连接 Milvus
    ↓
创建或加载 collection
```

核心配置来自 `base/config.py`：

| 配置 | 作用 |
|------|------|
| `MILVUS_HOST` | Milvus 地址 |
| `MILVUS_PORT` | Milvus 端口 |
| `MILVUS_DATABASE_NAME` | Milvus 数据库 |
| `MILVUS_COLLECTION_NAME` | 集合名称 |

模型加载位置：

| 模型 | 代码路径 | 作用 |
|------|----------|------|
| BGE-M3 | `rag_qa/models/bge-m3` | 生成 dense/sparse 双向量 |
| BGE-Reranker-Large | `rag_qa/models/bge-reranker-large` | 对召回结果精排 |

## Collection 字段设计

`vector_store.py` 会创建 Milvus collection，主要字段如下：

| 字段 | 类型 | 作用 |
|------|------|------|
| `id` | VARCHAR | 主键，使用文本 MD5 |
| `text` | VARCHAR | 子块文本 |
| `dense_vector` | FLOAT_VECTOR | BGE-M3 生成的稠密向量 |
| `sparse_vector` | SPARSE_FLOAT_VECTOR | BGE-M3 生成的稀疏向量 |
| `parent_id` | VARCHAR | 父块 ID |
| `parent_content` | VARCHAR | 父块完整内容 |
| `source` | VARCHAR | 学科或来源，如 `ai` |
| `timestamp` | VARCHAR | 入库时间 |

这里最关键的是：

```text
Milvus 存的是子块向量，但同时保存父块内容。
```

这样检索时可以用小粒度子块提高命中精度，再返回更完整的父块作为大模型上下文。

## 索引设计

项目给两个向量字段分别建索引：

| 字段 | 索引 | 中文名 | 作用 |
|------|------|--------|------|
| `dense_vector` | `IVF_FLAT` | 倒排文件平面索引 | 稠密语义检索 |
| `sparse_vector` | `SPARSE_INVERTED_INDEX` | 稀疏倒排索引 | 稀疏关键词检索 |

两个索引的度量方式都是 `IP`。

关键参数：

```python
dense_vector: nlist = 128
dense search: nprobe = 10
sparse_vector: drop_ratio_build = 0.2
```

### IVF_FLAT（倒排文件平面索引）原理

`IVF_FLAT` 用在 `dense_vector` 上，适合稠密向量检索。

中文名可以理解为“倒排文件 + 原始向量精确计算”：

- `IVF`：Inverted File，先把向量按聚类中心分桶。
- `FLAT`：桶内不压缩向量，直接用原始向量计算相似度。

它的核心思路是先把向量空间分成多个簇，再只在部分簇里做精确扫描：

```text
全部 dense 向量
    ↓
聚类成 nlist 个簇
    ↓
查询向量先找到最接近的 nprobe 个簇
    ↓
只在这些簇内做 FLAT 精确距离计算
```

这里：

- `nlist=128`：建索引时把向量空间分成 128 个簇。
- `nprobe=10`：查询时只搜索最相关的 10 个簇。

它的取舍是：

| 参数 | 变大 | 变小 |
|------|------|------|
| `nlist` | 簇更多，单簇更小，索引更细 | 簇更少，单簇更大，搜索更粗 |
| `nprobe` | 召回更全，但查询更慢 | 查询更快，但可能漏召回 |

`IVF_FLAT` 里的 `FLAT` 表示：进入候选簇之后，不再压缩向量，而是用原始向量做精确相似度计算。所以它比压缩索引更稳，但比纯暴力全量扫描更快。

### SPARSE_INVERTED_INDEX（稀疏倒排索引）原理

`SPARSE_INVERTED_INDEX` 用在 `sparse_vector` 上，适合稀疏向量检索。

中文名就是“稀疏倒排索引”，可以类比搜索引擎里的倒排表：不是从文档找词，而是从非零维度反查包含这些特征的文档块。

BGE-M3 生成的 sparse 向量可以理解成“带权重的关键词维度”。大部分维度是 0，只有少量维度有值。倒排索引会记录：

```text
维度 / 关键词特征  ->  出现在哪些文档块里  ->  对应权重是多少
```

查询时，Milvus 不需要扫描所有文档，只需要找到查询 sparse 向量中非零维度对应的倒排列表，再计算这些候选文档的内积得分。

这里：

- `drop_ratio_build=0.2`：建索引时丢弃较小的 20% 稀疏权重。

它的意义是减少索引体积和噪声。稀疏向量中很小的权重通常贡献不大，丢掉后可以让倒排索引更轻，但如果丢得太多，也可能影响关键词召回。

### 为什么两个索引一起用

项目不是只靠一种索引：

| 检索路径 | 解决的问题 |
|----------|------------|
| `dense_vector + IVF_FLAT` | 用户换一种说法，但语义接近时还能召回 |
| `sparse_vector + SPARSE_INVERTED_INDEX` | 课程名、技术名、英文缩写、专有词能精确命中 |

最后通过 RRF 排名融合把两路结果合并。RRF 不直接比较 dense_score 和 sparse_score 的原始大小，而是根据候选块在 dense / sparse 两路结果中的排名计算融合分：

```text
rrf_score = 1 / (k + dense_rank) + 1 / (k + sparse_rank)
```

如果某个候选只出现在一路结果中，就只计算该路排名分。这样可以避免 dense 和 sparse 分数尺度不一致导致某一路天然占优。

`hybrid_search.md` 已经单独说明了稠密和稀疏检索的区别，这里重点是：Milvus collection 中同时建了两套索引，查询时两路一起搜，再融合排序。

## 文档入库流程

入库方法是 `add_documents()`。

流程：

```text
子块 documents
    ↓
提取 page_content
    ↓
BGE-M3 生成 dense + sparse
    ↓
把 sparse 矩阵转成 Milvus 字典格式
    ↓
组装字段：
    id / text / dense_vector / sparse_vector
    parent_id / parent_content / source / timestamp
    ↓
upsert 到 Milvus
```

`id` 使用文本内容的 MD5：

```python
text_hash = hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()
```

这意味着相同文本块会得到相同 ID，`upsert` 时可以覆盖更新。

## 查询流程

核心查询方法是：

```python
hybrid_search_with_rerank(query, k=conf.RETRIEVAL_K, source_filter=None)
```

流程：

```text
用户 query
    ↓
BGE-M3 生成 query 的 dense + sparse
    ↓
构造 dense AnnSearchRequest
    ↓
构造 sparse AnnSearchRequest
    ↓
可选 source_filter 过滤
    ↓
RRF 排名融合两路结果
    ↓
从子块结果还原父块
    ↓
父块去重
    ↓
BGE-Reranker-Large 精排
    ↓
返回 Top-M 父块
```

融合方式：

```text
rrf_score = 1 / (k + dense_rank) + 1 / (k + sparse_rank)
```

含义是：两路都靠前的候选块会被优先保留；只在一路出现的候选也能进入候选集，但分数低于两路共同认可的结果。

## source_filter 过滤

如果传入 `source_filter`，代码会生成 Milvus 过滤表达式：

```python
filter_expr = f"source == '{source_filter}'"
```

例如：

```text
source_filter = "ai"
```

会变成：

```text
source == 'ai'
```

这个表达式会同时传给 dense 和 sparse 两路检索：

```python
dense_request = AnnSearchRequest(..., expr=filter_expr)
sparse_request = AnnSearchRequest(..., expr=filter_expr)
```

注意：这里的过滤只是 Milvus 元数据过滤，不是完整权限系统。

## 和其他模块的关系

```text
document_processor.py
    ↓
生成子块、parent_id、parent_content、source
    ↓
vector_store.py
    ↓
写入 Milvus，并执行 hybrid_search_with_rerank()
    ↓
new_rag_system.py
    ↓
把返回的父块拼成 context
    ↓
RAG Prompt 调用大模型生成答案
```

`source` 字段来自 `document_processor.py`：

```python
source = os.path.basename(directory_path).replace("_data", "")
```

例如目录是 `ai_data`，入库后 `source` 就是 `ai`。

## 当前取舍

| 设计点 | 说明 |
|--------|------|
| 存子块向量，返回父块内容 | 兼顾命中精度和上下文完整性 |
| dense + sparse 双字段 | 同时支持语义召回和关键词召回 |
| RRF 排名融合 | 不依赖 dense/sparse 原始分数尺度，优先保留两路都靠前的候选 |
| `source_filter` | 只过滤 Milvus，不覆盖 MySQL/BM25 分支 |
| `upsert` | 写入简单，但频繁更新时要关注数据版本和清理策略 |

一句话总结：

> Milvus 模块是项目的向量存储和检索执行层，负责保存 BGE-M3 生成的 dense/sparse 双向量，并通过混合检索、RRF 排名融合、父块回溯和 Reranker 精排，为 RAG 生成阶段提供高质量上下文。
