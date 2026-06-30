# 策略选择模块笔记

## 模块定位

策略选择模块在 `rag_qa/core/strategy_selector.py`。

它的作用是：当问题需要进入 RAG 知识库检索时，先判断应该用哪种检索增强方式。

注意它不是向量模型，也不是 BERT 分类模型，而是一个 **LLM Router**：

- 输入：用户问题
- 调用：DashScope/Qwen
- 输出：一个策略名称

输出结果会交给 `rag_qa/core/new_rag_system.py`，由 RAG 系统执行对应检索分支。

## 调用链路

整体链路如下：

```text
new_main.py
IntegratedQASystem.query()
    ↓
先走 BM25/MySQL/Redis
    ↓
如果没有可靠答案，回退到 RAG
    ↓
new_rag_system.py
RAGSystem.generate_answer()
    ↓
QueryClassifier 判断问题类型
    ├─ 通用知识：直接调用 LLM
    └─ 专业咨询：进入 StrategySelector
            ↓
        选择检索策略
            ↓
        retrieve_and_merge()
            ↓
        执行具体检索分支
```

所以策略选择不是第一层入口，它只在 RAG fallback 之后、真正检索知识库之前生效。

## 策略选择流程

`StrategySelector` 初始化时会创建 DashScope 客户端：

```python
self.client = OpenAI(
    api_key=Config().DASHSCOPE_API_KEY,
    base_url=Config().DASHSCOPE_BASE_URL
)
```

核心方法是 `select_strategy()`：

```python
strategy = self.call_dashscope(
    self.strategy_prompt_template.format(query=query)
)
return strategy
```

也就是说，策略不是写死规则判断出来的，而是通过 Prompt 让大模型从固定选项中选择。

如果 DashScope 调用失败，默认返回：

```python
"直接检索"
```

这是一个保守兜底：至少还能用原问题去知识库检索。

## 四种检索策略

| 策略 | 做法 | 适合场景 |
|------|------|----------|
| 直接检索 | 原问题直接进入 Milvus 混合检索 | 问题明确，能直接匹配知识库内容 |
| 假设问题检索 | 先让 LLM 生成一个假设答案，再用假设答案检索 | 问题比较抽象，原问题不好直接召回 |
| 子查询检索 | 把复杂问题拆成多个子问题，分别检索后合并 | 涉及多个实体、多个方面的问题 |
| 回溯问题检索 | 把复杂问题简化成更基础的问题，再检索 | 问法复杂，需要先抽出核心概念 |

在 `new_rag_system.py` 中，策略名称决定具体分支：

```python
if strategy == "回溯问题检索":
    ranked_chunks = self._retrieve_with_backtracking(query, source_filter)
elif strategy == "子查询检索":
    ranked_chunks = self._retrieve_with_subqueries(query, source_filter)
elif strategy == "假设问题检索":
    ranked_chunks = self._retrieve_with_hyde(query, source_filter)
else:
    ranked_chunks = self.vector_store.hybrid_search_with_rerank(...)
```

## 和查询分类器的区别

`QueryClassifier` 和 `StrategySelector` 解决的是两层不同问题。

| 模块 | 位置 | 作用 | 输出 |
|------|------|------|------|
| QueryClassifier | `rag_qa/core/query_classifier.py` | 判断问题是否需要查知识库 | 通用知识 / 专业咨询 |
| StrategySelector | `rag_qa/core/strategy_selector.py` | 判断 RAG 应该怎么检索 | 四种检索策略之一 |

简单理解：

```text
QueryClassifier：要不要 RAG？
StrategySelector：如果要 RAG，怎么检索？
```

只有 `QueryClassifier` 判断为 `专业咨询` 时，才会继续调用 `StrategySelector`。

## 当前取舍

优点：

- 策略选择灵活，不需要手写大量规则。
- 能根据问题复杂度选择不同检索方式。
- DashScope 异常时默认直接检索，系统仍可继续工作。

局限：

- 策略名称依赖 LLM 输出，必须和代码里的字符串完全匹配。
- 每次专业咨询都会多一次 LLM 调用，增加延迟和成本。
- 如果 LLM 返回解释性文本，而不是纯策略名称，代码会落到默认的直接检索分支。

项目当前的设计重点是让检索链路更灵活，而不是追求严格可控的规则路由。
