# 接口层模块笔记

## 模块定位

接口层负责把后端问答系统暴露给前端或外部调用方。

项目里主要有两套接口写法：

| 文件 | 方式 | 定位 |
|------|------|------|
| `app.py` | FastAPI + WebSocket | 主接口层，适合前端流式问答 |
| `api.py` | FastAPI + SSE | 简化版流式接口示例 |
| `use_api.py` | requests 客户端 | 测试 `api.py` 的 SSE 调用 |

其中 `app.py` 更完整，包含会话、历史记录、问候语、普通查询和 WebSocket 流式查询。

## app.py 核心接口

| 接口 | 方法 | 作用 |
|------|------|------|
| `/` | GET | 返回 `static/index.html` |
| `/api/create_session` | POST | 创建新的 `session_id` |
| `/api/history/{session_id}` | GET | 查询会话历史 |
| `/api/history/{session_id}` | DELETE | 清除会话历史 |
| `/api/query` | POST | 普通非流式查询 |
| `/api/stream` | WebSocket | 流式问答 |
| `/health` | GET | 健康检查 |
| `/api/sources` | GET | 返回有效学科来源 |

`app.py` 启动时会创建全局问答系统：

```python
qa_system = IntegratedQASystem()
```

后续所有接口都通过这个对象调用底层问答能力。

## 请求参数

`/api/query` 使用 `QueryRequest`：

```python
class QueryRequest(BaseModel):
    query: str
    source_filter: Optional[str] = None
    session_id: Optional[str] = None
```

| 参数 | 作用 |
|------|------|
| `query` | 用户问题 |
| `source_filter` | 可选，限制知识库来源，如 `ai` |
| `session_id` | 可选，用于维护多轮对话历史 |

如果前端不传 `session_id`，接口会自动生成 UUID。

## 普通 HTTP 查询流程

`POST /api/query` 适合快速判断是否能直接返回。

流程：

```text
收到 query
    ↓
生成或复用 session_id
    ↓
检查是否为问候语
    ├─ 是：直接返回模板回复
    └─ 否：继续
    ↓
执行 BM25 标准问答检索
    ├─ 命中：返回 MySQL 标准答案
    └─ 未命中：返回 is_streaming=True，提示使用 WebSocket
```

所以 `/api/query` 不负责完整 RAG 流式生成。

当需要 RAG 时，它返回：

```json
{
  "answer": "请使用WebSocket接口获取流式响应",
  "is_streaming": true,
  "session_id": "...",
  "processing_time": 0.1
}
```

前端看到 `is_streaming=True` 后，应切换到 `/api/stream`。

## WebSocket 流式查询流程

`/api/stream` 是 `app.py` 里的完整流式问答入口。

客户端发送 JSON：

```json
{
  "query": "AI 学科的课程内容有什么？",
  "source_filter": "ai",
  "session_id": "..."
}
```

服务端流程：

```text
客户端建立 WebSocket
    ↓
服务端发送 start
    ↓
检查问候语
    ├─ 是：发送 token + end
    └─ 否：调用 qa_system.query()
            ↓
        BM25 命中：一次性发送答案
        RAG 生成：逐 token 发送
    ↓
服务端发送 end
```

服务端发送的数据类型：

| type | 含义 |
|------|------|
| `start` | 本次流式响应开始 |
| `token` | 一个答案片段 |
| `end` | 本次响应结束 |
| `error` | 发生异常 |

WebSocket 内部最终调用：

```python
for token, is_complete in qa_system.query(
    query,
    source_filter=source_filter,
    session_id=session_id
):
```

也就是说，完整问答链路仍然在 `new_main.py` 的 `IntegratedQASystem.query()` 中。

## SSE 版本接口

`api.py` 里还有一个简化版 `/query` 接口。

它使用 `StreamingResponse` 返回 SSE：

```python
return StreamingResponse(
    generate_response(),
    media_type="text/event-stream"
)
```

SSE 返回格式：

```text
data: {"token": "...", "is_complete": false, "session_id": "..."}
```

`use_api.py` 是这个接口的测试客户端：

```python
requests.post(API_URL, json=data, stream=True)
```

它会逐行读取 `data:`，解析 JSON 后打印 token。

## 会话历史

接口层通过 `session_id` 维护多轮对话。

相关接口：

| 接口 | 作用 |
|------|------|
| `/api/create_session` | 创建新会话 |
| `/api/history/{session_id}` | 查询历史 |
| `/api/history/{session_id}` | 清除历史 |
| `/api/query` | 可携带 `session_id` |
| `/api/stream` | 可携带 `session_id` |

真正的历史读写在 `new_main.py` 中完成，接口层只是传递 `session_id`。

## 问候语处理

`app.py` 在接口层处理了简单问候语：

```python
greeting_response = check_greeting(request.query)
```

命中问候语后直接返回模板回复，不进入 BM25，也不进入 RAG。

这样可以避免简单寒暄消耗检索和大模型资源。

## 当前取舍

| 设计点 | 说明 |
|--------|------|
| `app.py` 用 WebSocket | 适合逐 token 推送 RAG 生成结果 |
| `api.py` 用 SSE | 适合简单 HTTP 流式测试 |
| `/api/query` 不完整走 RAG | RAG 场景提示前端使用 WebSocket |
| 问候语在接口层处理 | 简单问题不进入 BM25/RAG |
| CORS 开放 `*` | 开发方便，生产环境应限制来源 |

一句话总结：

> 接口层负责把 `IntegratedQASystem` 包装成可访问的 FastAPI 服务，其中 `app.py` 提供 WebSocket 流式问答主链路，`api.py` 提供 SSE 流式调用示例。
