# RAG 生成模块笔记

## 模块定位

RAG 生成模块位于 `rag_qa/core/new_rag_system.py`，核心方法是 `generate_answer()`。

它负责把前面检索到的内容组织成 Prompt，然后调用大模型生成最终答案。

这篇只讲生成流程，不重复说明：

- 策略选择细节：见 `strategy_selection.md`
- Milvus 字段和检索细节：见 `vector_store.md`
- dense/sparse 混合检索原理：见 `hybrid_search.md`

## generate_answer 主流程

整体流程：

```text
generate_answer(query, source_filter=None, history=None)
    ↓
处理历史对话
    ↓
QueryClassifier 判断问题类型
    ├─ 通用知识：context 为空，直接让 LLM 回答
    └─ 专业咨询：执行 RAG 检索
            ↓
        StrategySelector 选择检索策略
            ↓
        retrieve_and_merge() 返回上下文文档
            ↓
        拼接 context
    ↓
组装 RAG Prompt
    ↓
调用 LLM 流式生成
    ↓
逐 token yield 给上层
```

## 对话历史处理

`generate_answer()` 支持传入历史对话：

```python
def generate_answer(self, query, source_filter=None, history=None):
```

如果 `history` 不是列表，会被忽略：

```python
if history is not None and not isinstance(history, list):
    history = []
```

如果有历史，只保留最近 5 轮：

```python
history = history[-5:]
```

然后拼成文本：

```python
history_context = "\n".join([
    f"Q:{h['question']}\nA:{h['answer']}"
    for h in history
])
```

这一步的作用是让大模型能理解多轮对话里的上下文。

## 检索上下文构造

系统会先用 `QueryClassifier` 判断问题类型：

```python
query_category = self.query_classifier.predict_category(query)
```

如果是 `通用知识`：

```python
context = ""
```

也就是不查知识库，直接让大模型回答。

如果是 `专业咨询`，才进入 RAG：

```python
strategy = self.strategy_selector.select_strategy(query)
context_docs = self.retrieve_and_merge(
    query,
    source_filter=source_filter,
    strategy=strategy
)
```

检索结果会被拼成上下文：

```python
context = "\n\n".join([doc.page_content for doc in context_docs])
```

如果没有检索到文档，`context` 就是空字符串。

## Prompt 组装

Prompt 模板来自 `rag_qa/core/prompts.py`：

```python
prompt_input = self.rag_prompt.format(
    context=context,
    question=query,
    history=history_context,
    phone=conf.CUSTOMER_SERVICE_PHONE
)
```

传入 Prompt 的核心变量：

| 变量 | 来源 | 作用 |
|------|------|------|
| `context` | RAG 检索结果 | 给大模型参考的知识库内容 |
| `question` | 用户当前问题 | 本轮要回答的问题 |
| `history` | 最近 5 轮对话 | 辅助理解上下文 |
| `phone` | 配置中的客服电话 | 信息不足时兜底 |

Prompt 会要求模型：

- 有上下文时优先基于上下文回答。
- 历史相关时结合历史。
- 信息不足时提示联系人工客服。

## 流式输出

生成阶段使用传入的 `self.llm`：

```python
for token in self.llm(prompt_input):
    yield token
```

这里不是一次性返回完整答案，而是逐 token 往外抛。

上层 `new_main.py` 会继续把这些 token 返回给接口层，实现流式问答效果。

## 当前取舍

| 设计点 | 说明 |
|--------|------|
| 最近 5 轮历史 | 控制上下文长度，避免历史过长 |
| 通用知识不查库 | 减少不必要检索 |
| 专业咨询走 RAG | 优先基于知识库回答业务问题 |
| 空 context 仍调用 LLM | 检索失败时仍可生成兜底回答 |
| 流式 yield | 提升前端响应体验 |

一句话总结：

> RAG 生成模块负责把用户问题、历史对话和检索上下文组装成 Prompt，再调用大模型流式生成最终答案。
