# MySQL + Redis + BM25 模块笔记

## 模块定位

这个模块是项目的 **标准问答优先层**。

它负责处理高频、稳定、答案固定的问题，例如：

- 学费是多少
- 课程大纲是什么
- 报名流程是什么
- 某个固定知识点的标准解释

系统不会一上来就直接走 RAG。它会先用 BM25 在 MySQL 标准问答库里找相似问题，如果置信度足够高，就直接返回 MySQL 中维护的标准答案。

如果没有可靠命中，才回退到 RAG。

## 调用链路

入口在 `new_main.py`：

```text
IntegratedQASystem.query()
    ↓
BM25Search.search(query, threshold=0.85)
    ↓
命中：返回 MySQL 标准答案
未命中：need_rag=True，进入 RAG 流程
```

核心代码位置：

| 文件 | 作用 |
|------|------|
| `new_main.py` | 系统主入口，决定先查 BM25 还是回退 RAG |
| `mysql_qa/retrieval/bm25_search.py` | BM25 相似问题检索 |
| `mysql_qa/db/MySQLClient.py` | 读取标准问答表 |
| `mysql_qa/cache/RedisClient.py` | 缓存问题列表、分词结果和答案 |
| `mysql_qa/utils/preprocess.py` | 使用 jieba 对问题分词 |

## 三个组件分工

| 组件 | 作用 |
|------|------|
| MySQL | 保存标准问答数据，核心表是 `jpkb` |
| Redis | 缓存问题列表、分词结果、已命中的答案 |
| BM25 | 计算用户问题和标准问题之间的关键词相似度 |

MySQL 是权威数据源，Redis 是加速层，BM25 是相似问题匹配器。

## 数据加载流程

`BM25Search` 初始化时会先加载标准问题库：

```text
BM25Search 初始化
    ↓
先从 Redis 读取：
    qa_original_questions
    qa_tokenized_questions
    ↓
如果 Redis 没有缓存
    ↓
从 MySQL 的 jpkb 表读取全部 question
    ↓
用 jieba 分词
    ↓
写回 Redis
    ↓
构建 BM25Okapi
```

对应代码：

```python
original_key = "qa_original_questions"
tokenized_key = "qa_tokenized_questions"

self.original_questions = self.redis_client.get_data(original_key)
self.tokenized_questions = self.redis_client.get_data(tokenized_key)
```

如果 Redis 没有数据，就从 MySQL 加载：

```python
self.original_questions = self.mysql_client.fetch_questions()
self.tokenized_questions = [preprocess_text(doc[0]) for doc in self.original_questions]
```

## 查询流程

一次查询的流程如下：

```text
用户问题 query
    ↓
检查 Redis：answer:{query}
    ↓
如果有缓存答案，直接返回
    ↓
如果没有缓存
    ↓
对 query 分词
    ↓
BM25 计算 query 和标准问题的相似度
    ↓
Softmax 归一化
    ↓
取最高分
    ↓
最高分 > 0.85
    ├─ 是：去 MySQL 查标准答案，写入 Redis，返回答案
    └─ 否：返回 need_rag=True
```

关键判断在 `BM25Search.search()`：

```python
answer, need_rag = self.bm25_search.search(query, threshold=0.85)
```

返回含义：

| 返回值 | 含义 |
|--------|------|
| `answer, False` | BM25 高置信命中，直接返回标准答案 |
| `None, True` | 无可靠标准答案，需要进入 RAG |
| `None, False` | 输入无效，不进入 RAG |

## 为什么先走标准问答

标准问答适合高频、确定、口径固定的问题。

优点：

- **稳定**：答案来自 MySQL，不由大模型临场发挥。
- **快速**：命中后不用调用 Milvus、Reranker 和 LLM。
- **成本低**：减少大模型调用次数。
- **可维护**：标准答案可以人工审核和统一更新。

这类问题如果全部交给 RAG，反而可能出现回答不稳定、上下文召回不准、LLM 表达不一致的问题。

## 和 RAG 的关系

```text
MySQL + BM25：解决高频、确定性、标准答案问题
RAG：解决开放、复杂、需要文档上下文的问题
```

两者不是替代关系，而是前后分工：

1. 先用 MySQL + BM25 尝试低成本命中标准答案。
2. 命中失败后，再进入 RAG 做文档检索和生成。

所以这个项目不是纯向量 RAG，而是：

```text
BM25/MySQL/Redis 优先
    ↓
Milvus 混合检索 + Reranker
    ↓
LLM 生成
```

## 当前取舍

| 设计点 | 说明 |
|--------|------|
| `threshold=0.85` | 高置信才返回标准答案，低置信宁可走 RAG |
| `answer:{query}` | 按原始 query 字符串缓存答案 |
| 无 TTL | Redis 缓存没有自动过期策略 |
| Redis 非权威源 | MySQL 更新后，需要考虑清理 Redis 缓存 |
| BM25 偏关键词 | 对课程名、技术名、固定术语友好，对同义改写不如向量检索 |

一句话总结：

> MySQL + Redis + BM25 是项目的标准问答优先层，用低成本、稳定的方式处理高频 FAQ；只有标准问答无法可靠命中时，系统才进入 RAG 文档检索和大模型生成流程。
