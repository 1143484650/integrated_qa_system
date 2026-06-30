# 总问答链路笔记

## 模块定位

这篇讲 `new_main.py` 中的 `IntegratedQASystem`。

它是系统总编排层，负责把这些模块串起来：

- MySQL 标准问答
- Redis 缓存
- BM25 相似问题匹配
- Milvus 向量库
- RAGSystem
- DashScope/Qwen
- 会话历史

其他文档讲的是“零件”，这篇讲的是“一次用户提问怎么流转”。

## 初始化流程

`IntegratedQASystem.__init__()` 初始化流程：

```text
IntegratedQASystem()
    ↓
加载 Config
    ↓
初始化 MySQLClient
    ↓
初始化 RedisClient
    ↓
初始化 BM25Search
    ↓
初始化 DashScope/OpenAI client
    ↓
初始化 VectorStore
    ↓
初始化 RAGSystem
    ↓
初始化 conversations 会话历史表
```

对应对象分工：

| 初始化对象 | 作用 |
|------------|------|
| `MySQLClient` | 标准问答和会话历史 |
| `RedisClient` | 缓存问题、分词结果、答案 |
| `BM25Search` | 标准问答相似匹配 |
| `VectorStore` | Milvus 向量检索 |
| `RAGSystem` | RAG 检索与生成 |
| `OpenAI client` | 调用 DashScope/Qwen |

## query 主流程

核心方法：

```python
def query(self, query, source_filter=None, session_id=None):
```

流程：

```text
用户问题 query
    ↓
记录开始时间
    ↓
如果有 session_id，读取最近 5 轮历史
    ↓
BM25Search.search(query, threshold=0.85)
    ↓
判断是否命中标准问答
```

`query()` 本身是一个生成器，会不断 `yield`：

```python
yield token, is_complete
```

其中：

| 返回值 | 含义 |
|--------|------|
| `token` | 当前返回的答案片段 |
| `is_complete` | 当前回答是否结束 |

## 标准问答命中分支

如果 BM25/MySQL 命中标准答案：

```text
answer 有值
    ↓
直接返回 MySQL 标准答案
    ↓
如果有 session_id，写入 conversations
    ↓
yield answer, True
```

特点：

- 不进入 RAG。
- 不调用 Milvus。
- 不调用大模型生成。
- 返回的是完整答案，不是逐 token 生成。

这一支适合高频、稳定、标准化问题。

对应细节见 `mysql_bm25_redis.md`。

## RAG 回退分支

如果 BM25 没有可靠答案：

```text
need_rag=True
    ↓
调用 self.rag_system.generate_answer(...)
    ↓
传入 query / source_filter / history
    ↓
RAGSystem 内部完成：
        QueryClassifier
        StrategySelector
        Milvus hybrid search
        RAG Prompt
        LLM 流式生成
    ↓
query() 逐 token yield
    ↓
收集完整答案
    ↓
写入 conversations
```

这一支对应的子文档：

| 子流程 | 对应文档 |
|--------|----------|
| RAG 生成 | `rag_generation.md` |
| 策略选择 | `strategy_selection.md` |
| Milvus 向量库 | `vector_store.md` |
| 混合检索原理 | `hybrid_search.md` |
| 模型说明 | `models.md` |

## 会话历史

`new_main.py` 会维护 MySQL 表 `conversations`。

字段：

| 字段 | 作用 |
|------|------|
| `session_id` | 会话 ID |
| `question` | 用户问题 |
| `answer` | 系统答案 |
| `timestamp` | 时间 |

相关方法：

| 方法 | 作用 |
|------|------|
| `init_conversation_table()` | 创建历史表 |
| `_fetch_recent_history()` | 获取最近 5 轮历史 |
| `get_session_history()` | 对外查询会话历史 |
| `update_session_history()` | 写入本轮问答，并保留最近 5 轮 |
| `clear_session_history()` | 清空指定会话历史 |

注意：历史最终存在 MySQL，不存在 Redis。

## source_filter 流转

`source_filter` 从接口层传入：

```text
app.py / api.py
    ↓
new_main.py query()
    ↓
RAGSystem.generate_answer()
    ↓
retrieve_and_merge()
    ↓
VectorStore.hybrid_search_with_rerank()
    ↓
Milvus expr: source == 'ai'
```

注意：`source_filter` 只影响 RAG/Milvus 检索，不影响前面的 BM25/MySQL 标准问答分支。

如果要做真正的文档权限控制，不能只改 Milvus 过滤，也要覆盖 MySQL/BM25 分支。

## 整体流程图

```text
接口层收到问题
    ↓
IntegratedQASystem.query()
    ↓
读取会话历史
    ↓
BM25/MySQL/Redis 标准问答
    ├─ 命中
    │   ↓
    │ 返回标准答案
    │   ↓
    │ 写入会话历史
    │
    └─ 未命中
        ↓
      RAGSystem.generate_answer()
        ↓
      QueryClassifier 判断类型
        ↓
      StrategySelector 选择检索策略
        ↓
      Milvus 混合检索 + Reranker
        ↓
      拼接 Prompt
        ↓
      DashScope/Qwen 流式生成
        ↓
      写入会话历史
```

## 当前取舍

| 设计点 | 说明 |
|--------|------|
| 标准问答优先 | 高频固定问题更稳定、更快 |
| RAG 兜底 | 覆盖复杂、开放、需要文档上下文的问题 |
| 流式输出 | RAG 生成时前端体验更好 |
| 最近 5 轮历史 | 控制上下文长度 |
| `source_filter` 只进 RAG | 标准问答分支不受学科过滤影响 |

一句话总结：

> `IntegratedQASystem` 是项目的总编排层，它先用 MySQL + BM25 处理标准问答，无法可靠命中时再回退到 RAG，通过 Milvus 检索和大模型生成答案，并用 `session_id` 维护最近 5 轮会话历史。
