# MySQL 问答系统面试题总结

## 1. cursor 游标的作用

- **connect**: 与数据库的网络连接（TCP），负责认证、会话管理
- **cursor**: 在连接上创建的"执行器"，负责发送 SQL、接收结果集
- 一个 connect 可以创建多个 cursor

---

## 2. softmax 归一化

**为什么用 softmax？**
- 把原始分数转成概率分布（0-1，总和为1）
- 方便用统一阈值（0.85）判断匹配置信度

**`scores - np.max(scores)` 的作用？**
- **数值稳定性**：避免 `exp(大数)` 导致浮点数溢出
- 减去最大值后，所有指数 ≤ 0，结果在 (0, 1] 范围内
- 数学上结果完全等价

---

## 3. 缓存设计模式

**模式名称**: Cache-Aside（旁路缓存）/ Lazy Loading（懒加载）

**潜在问题**:
| 问题 | 描述 |
|------|------|
| 缓存穿透 | 查询不存在的数据，每次都穿透到数据库 |
| 缓存击穿 | 热点 key 过期瞬间，大量并发请求打到数据库 |
| 缓存雪崩 | 大量 key 同时过期，数据库瞬间压力暴增 |
| 数据一致性 | MySQL 更新后，Redis 缓存可能还是旧数据 |

---

## 4. pymysql execute 参数 bug

**错误写法**:
```python
self.cursor.execute('select answer from jpkb where question = %s', question)
```

**正确写法**:
```python
self.cursor.execute('select answer from jpkb where question = %s', (question,))
```

**原因**: execute 第二个参数必须是元组或列表，单参数也要写成 `(question,)`

---

## 5. 资源管理

**问题**: 程序中途抛异常，`close()` 不会被调用，连接泄漏

**解决方案**:

**方式一：try-finally**
```python
client = MySQLClient()
try:
    client.query("...")
finally:
    client.close()  # 无论是否异常都会执行
```

**方式二：上下文管理器（推荐）**
```python
class MySQLClient:
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# 使用
with MySQLClient() as client:
    client.query("...")
```

两种方式都是在**调用处**保证资源释放。

---

## 6. 异常处理问题

**问题一：异常后返回值不明确**

```python
def fetch_questions(self):
    try:
        # ...
        return tuple_questions
    except pymysql.MySQLError as e:
        logger.info(f'查询失败:{e}')
        # 没有 return，隐式返回 None
```

调用方拿到 `None` 无法区分：
- 查询成功但表里没数据 → `None`
- 数据库连接断了 → `None`

**更好做法**：异常时抛出去，或返回不同值让调用方能区分。

---

**问题二：日志级别错误**

错误应该用 `logger.error`，不是 `logger.info`。

| 级别 | 用途 |
|------|------|
| `debug` | 调试信息 |
| `info` | 正常流程记录 |
| `warning` | 潜在问题 |
| `error` | 错误发生 |
| `critical` | 严重故障 |

查询失败是错误，应该用 `logger.error`，方便后续排查问题时过滤日志。

---

## 7. 并发问题与连接池

**问题：多线程共享同一个 cursor 会导致数据混乱**

```
线程 A：execute(查询问题)
线程 B：execute(查询答案)  ← 覆盖了 A 的结果
线程 A：fetchall()         ← 拿到的是 B 的结果
```

**解决方案：连接池**

```
共享 cursor（问题）：
  线程 A ──┐
           ├──→ 同一个 cursor  → 结果互相覆盖
  线程 B ──┘

连接池（解决）：
  线程 A ──→ 连接1 → cursor1   → 各自独立
  线程 B ──→ 连接2 → cursor2   → 互不干扰
```

**为什么不每次新建连接？**
- 建立连接很慢（TCP 握手、认证）
- 连接池复用已建立的连接，省去重复开销

---

**连接池 vs 数据库锁（不同层次的问题）**

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| cursor 结果覆盖 | 多线程共享同一个 cursor | 连接池（程序层面） |
| 数据竞争/丢失更新 | 多线程操作同一行数据 | 数据库锁/事务（数据层面） |

**数据库锁方案**：
- 悲观锁：`SELECT ... FOR UPDATE`
- 乐观锁：version 字段
- 事务隔离级别

---

## 8. 配置管理与单例模式

**问题**：每次 `Config()` 都会重新读取配置文件、创建新对象，浪费资源。

**解决方案：单例模式**

**方式一：模块级全局变量（推荐）**
```python
# config.py
class Config:
    def __init__(self):
        # 读取配置...
        pass

config = Config()  # 模块加载时创建一次
```

**原理**：Python 模块只执行一次，后续 import 从 `sys.modules` 缓存取，整个项目拿到同一个实例。

**方式二：`__new__` 单例**
```python
class Config:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

| 方式 | 优点 | 缺点 |
|------|------|------|
| 模块全局变量 | 简单直接 | 导入时就创建 |
| `__new__` 单例 | 兼容现有 `Config()` 调用 | 稍复杂 |
