# -*- coding: utf-8 -*-
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from base import logger

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - used when langgraph is not installed locally
    END = "__end__"

    class _CompiledGraph:
        def __init__(self, graph):
            self.graph = graph

        def invoke(self, state):
            current = self.graph.entry_point
            while current and current != END:
                node_result = self.graph.nodes[current](state) or {}
                if not isinstance(node_result, dict):
                    raise TypeError(f"graph node {current} must return dict")
                state.update(node_result)

                if current in self.graph.conditional_edges:
                    router = self.graph.conditional_edges[current]
                    current = router(state)
                else:
                    current = self.graph.edges.get(current, END)
            return state

    class StateGraph:
        def __init__(self, state_schema):
            self.state_schema = state_schema
            self.nodes = {}
            self.edges = {}
            self.conditional_edges = {}
            self.entry_point = None

        def add_node(self, name, func):
            self.nodes[name] = func

        def set_entry_point(self, name):
            self.entry_point = name

        def add_edge(self, start, end):
            self.edges[start] = end

        def add_conditional_edges(self, start, router, path_map=None):
            if path_map:
                self.conditional_edges[start] = lambda state: path_map[router(state)]
            else:
                self.conditional_edges[start] = router

        def compile(self):
            return _CompiledGraph(self)


class Citation(BaseModel):
    source: str = ""
    parent_id: str = ""
    timestamp: str = ""
    snippet: str = ""


class FaithfulnessResult(BaseModel):
    passed: bool
    faithfulness_score: float
    unsupported_claims: List[str] = Field(default_factory=list)


class RiskControlResult(BaseModel):
    risk_level: str = "low"
    action: str = "return"
    need_human_review: bool = False
    answer: str = ""


class RAGAnswerResult(BaseModel):
    answer: str
    answer_type: str
    trace_id: str
    citations: List[Citation] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    faithfulness_score: Optional[float] = None
    need_human_review: bool = False
    retrieval_strategy: Optional[str] = None
    rewritten_query: Optional[str] = None
    processing_time: float = 0.0


class QAState(TypedDict, total=False):
    query: str
    session_id: str
    history: List[Dict[str, str]]
    allowed_sources: List[str]
    requested_sources: List[str]
    final_sources: List[str]
    source_filter: Optional[str]
    trace_id: str
    start_time: float
    faq_hit: bool
    faq_answer: Optional[str]
    classification: Optional[str]
    keyword_review: bool
    out_of_scope: bool
    retrieval_strategy: Optional[str]
    rewritten_query: Optional[str]
    retrieved_chunks: List[Any]
    reranked_docs: List[Any]
    context: str
    draft_answer: Optional[str]
    retry_count: int
    faithfulness_result: Optional[FaithfulnessResult]
    risk_result: Optional[RiskControlResult]
    citations: List[Citation]
    sources: List[str]
    final_answer: str
    answer_type: str
    need_human_review: bool
    result: RAGAnswerResult


class QAGraphWorkflow:
    """LangGraph-style workflow for the online QA path."""

    DOMAIN_KEYWORDS = {
        "印刷", "印前", "覆膜", "油墨", "纸张", "纸箱", "色差", "套印", "模切", "胶水", "工艺",
        "质量", "售后", "SOP", "ai", "java", "python", "测试", "运维", "大数据", "课程", "学科",
        "MySQL", "Redis", "Milvus", "Docker", "Linux",
    }
    FOLLOW_UP_MARKERS = {"这个", "那个", "刚才", "上面", "前面", "它", "这", "那", "怎么排查", "还有呢", "为什么"}

    def __init__(self, qa_system):
        self.qa_system = qa_system
        self.config = qa_system.config
        self.bm25_search = qa_system.bm25_search
        self.rag_system = qa_system.rag_system
        self.graph = self._build_graph()

    def run(
        self,
        query: str,
        source_filter: Optional[str] = None,
        session_id: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        allowed_sources: Optional[List[str]] = None,
        requested_sources: Optional[List[str]] = None,
    ) -> RAGAnswerResult:
        state: QAState = {
            "query": query,
            "session_id": session_id or str(uuid.uuid4()),
            "history": history or [],
            "allowed_sources": allowed_sources or list(self.config.VALID_SOURCES),
            "requested_sources": requested_sources or ([source_filter] if source_filter else []),
            "source_filter": source_filter,
            "trace_id": str(uuid.uuid4()),
            "start_time": time.time(),
            "retry_count": 0,
        }
        final_state = self.graph.invoke(state)
        return final_state["result"]

    def debug_retrieval(
        self,
        query: str,
        source_filter: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        allowed_sources: Optional[List[str]] = None,
    ):
        state: QAState = {
            "query": query,
            "session_id": "debug",
            "history": history or [],
            "allowed_sources": allowed_sources or list(self.config.VALID_SOURCES),
            "requested_sources": [source_filter] if source_filter else [],
            "source_filter": source_filter,
            "trace_id": str(uuid.uuid4()),
            "start_time": time.time(),
            "retry_count": 0,
        }
        for node in [
            self.init_state,
            self.load_history,
            self.query_classification,
            self.printing_keyword_review,
        ]:
            state.update(node(state) or {})
        if self.route_after_classification(state) == "out_of_scope":
            return self._debug_payload(state)
        for node in [self.strategy_selector, self.query_rewrite, self.retrieve_docs, self.rerank_docs]:
            state.update(node(state) or {})
        return self._debug_payload(state)

    def _build_graph(self):
        graph = StateGraph(QAState)
        graph.add_node("init_state", self.init_state)
        graph.add_node("load_history", self.load_history)
        graph.add_node("standard_qa_search", self.standard_qa_search)
        graph.add_node("query_classification", self.query_classification)
        graph.add_node("printing_keyword_review", self.printing_keyword_review)
        graph.add_node("out_of_scope", self.out_of_scope)
        graph.add_node("strategy_selector", self.strategy_selector)
        graph.add_node("query_rewrite", self.query_rewrite)
        graph.add_node("retrieve_docs", self.retrieve_docs)
        graph.add_node("rerank_docs", self.rerank_docs)
        graph.add_node("generate_answer", self.generate_answer)
        graph.add_node("retry_generate_answer", self.retry_generate_answer)
        graph.add_node("faithfulness_check", self.faithfulness_check)
        graph.add_node("risk_control", self.risk_control)
        graph.add_node("build_citations", self.build_citations)
        graph.add_node("final_answer", self.final_answer)

        graph.set_entry_point("init_state")
        graph.add_edge("init_state", "load_history")
        graph.add_edge("load_history", "standard_qa_search")
        graph.add_conditional_edges("standard_qa_search", self.route_after_standard_qa)
        graph.add_edge("query_classification", "printing_keyword_review")
        graph.add_conditional_edges("printing_keyword_review", self.route_after_classification)
        graph.add_edge("out_of_scope", "final_answer")
        graph.add_edge("strategy_selector", "query_rewrite")
        graph.add_edge("query_rewrite", "retrieve_docs")
        graph.add_edge("retrieve_docs", "rerank_docs")
        graph.add_edge("rerank_docs", "generate_answer")
        graph.add_edge("generate_answer", "faithfulness_check")
        graph.add_edge("retry_generate_answer", "faithfulness_check")
        graph.add_conditional_edges("faithfulness_check", self.route_after_faithfulness)
        graph.add_edge("build_citations", "final_answer")
        graph.add_edge("risk_control", "final_answer")
        graph.add_edge("final_answer", END)
        return graph.compile()

    def init_state(self, state: QAState):
        allowed_sources = state.get("allowed_sources") or []
        requested_sources = state.get("requested_sources") or []
        if requested_sources:
            final_sources = [source for source in requested_sources if source in allowed_sources]
        else:
            final_sources = allowed_sources
        return {
            "final_sources": final_sources,
            "faq_hit": False,
            "faq_answer": None,
            "keyword_review": False,
            "out_of_scope": False,
            "retrieved_chunks": [],
            "reranked_docs": [],
            "citations": [],
            "sources": [],
            "need_human_review": False,
        }

    def load_history(self, state: QAState):
        history = state.get("history") or []
        return {"history": history[-5:]}

    def standard_qa_search(self, state: QAState):
        answer, need_rag = self.bm25_search.search(state["query"], threshold=0.85)
        if answer:
            return {
                "faq_hit": True,
                "faq_answer": answer,
                "final_answer": answer,
                "answer_type": "faq",
                "need_rag": need_rag,
            }
        return {"faq_hit": False, "need_rag": need_rag}

    def route_after_standard_qa(self, state: QAState):
        return "final_answer" if state.get("faq_hit") else "query_classification"

    def query_classification(self, state: QAState):
        classification = self.rag_system.query_classifier.predict_category(state["query"])
        logger.info(f"Graph query classification: {classification}")
        return {"classification": classification}

    def printing_keyword_review(self, state: QAState):
        query = state["query"]
        keyword_hit = any(keyword.lower() in query.lower() for keyword in self.DOMAIN_KEYWORDS)
        return {"keyword_review": keyword_hit}

    def route_after_classification(self, state: QAState):
        if not state.get("final_sources"):
            return "out_of_scope"
        if state.get("classification") == "专业咨询" or state.get("keyword_review"):
            return "strategy_selector"
        return "out_of_scope"

    def out_of_scope(self, state: QAState):
        answer = "当前问题超出企业知识库可回答范围，建议换成知识库相关问题或联系人工确认。"
        return {
            "final_answer": answer,
            "answer_type": "out_of_scope",
            "need_human_review": False,
        }

    def strategy_selector(self, state: QAState):
        query = state["query"]
        history = state.get("history") or []
        if history and self._looks_like_follow_up(query):
            strategy = "回溯问题检索"
        else:
            strategy = self.rag_system.strategy_selector.select_strategy(query)
        return {"retrieval_strategy": strategy}

    def query_rewrite(self, state: QAState):
        query = state["query"]
        if state.get("retrieval_strategy") != "回溯问题检索" or not state.get("history"):
            return {"rewritten_query": query}

        history_context = self._format_history(state.get("history") or [])
        prompt = f"""
请结合历史对话，把当前追问改写成一个完整、独立、适合检索的问题。

历史对话：
{history_context}

当前问题：
{query}

只输出改写后的问题，不要解释。
"""
        rewritten_query = self._call_llm_text(prompt).strip() or query
        return {"rewritten_query": rewritten_query}

    def retrieve_docs(self, state: QAState):
        strategy = state.get("retrieval_strategy") or "直接检索"
        retrieval_query = state.get("rewritten_query") or state["query"]
        source_filter = self._active_source_filter(state)
        if strategy == "回溯问题检索":
            docs = self.rag_system.vector_store.hybrid_search_with_rerank(
                retrieval_query,
                k=self.config.RETRIEVAL_K,
                source_filter=source_filter,
            )
        else:
            docs = self.rag_system.retrieve_and_merge(
                retrieval_query,
                source_filter=source_filter,
                strategy=strategy,
            )
        return {"retrieved_chunks": docs}

    def rerank_docs(self, state: QAState):
        docs = state.get("retrieved_chunks") or []
        context = "\n\n".join([doc.page_content for doc in docs])
        return {"reranked_docs": docs, "context": context}

    def generate_answer(self, state: QAState):
        prompt = self.rag_system.rag_prompt.format(
            context=state.get("context", ""),
            question=state["query"],
            history=self._format_history(state.get("history") or []),
            phone=self.config.CUSTOMER_SERVICE_PHONE,
        )
        draft_answer = self._call_llm_text(prompt)
        return {"draft_answer": draft_answer, "answer_type": "rag"}

    def retry_generate_answer(self, state: QAState):
        unsupported = "\n".join((state.get("faithfulness_result") or FaithfulnessResult(passed=False, faithfulness_score=0)).unsupported_claims)
        prompt = f"""
请只基于下面的检索上下文重新回答问题。删除无法被上下文支持的内容。

问题：
{state["query"]}

检索上下文：
{state.get("context", "")}

上次未被支持的内容：
{unsupported}

回答：
"""
        draft_answer = self._call_llm_text(prompt)
        return {"draft_answer": draft_answer, "retry_count": state.get("retry_count", 0) + 1}

    def faithfulness_check(self, state: QAState):
        answer = state.get("draft_answer") or ""
        context = state.get("context") or ""
        if not answer.strip():
            result = FaithfulnessResult(passed=False, faithfulness_score=0.0, unsupported_claims=["答案为空"])
            return {"faithfulness_result": result}
        if self._is_refusal(answer):
            result = FaithfulnessResult(passed=True, faithfulness_score=1.0)
            return {"faithfulness_result": result}
        if not context.strip():
            result = FaithfulnessResult(passed=False, faithfulness_score=0.0, unsupported_claims=[answer[:120]])
            return {"faithfulness_result": result}

        score = self._text_support_score(answer, context)
        unsupported_claims = [] if score >= 0.35 else self._split_claims(answer)[:3]
        result = FaithfulnessResult(
            passed=score >= 0.35,
            faithfulness_score=round(score, 3),
            unsupported_claims=unsupported_claims,
        )
        return {"faithfulness_result": result}

    def route_after_faithfulness(self, state: QAState):
        result = state.get("faithfulness_result")
        if result and result.passed:
            return "build_citations"
        if state.get("retry_count", 0) < 3 and state.get("context"):
            return "retry_generate_answer"
        return "risk_control"

    def risk_control(self, state: QAState):
        result = state.get("faithfulness_result")
        answer = "当前资料未明确说明该问题，建议联系人工确认后再处理。"
        risk_result = RiskControlResult(
            risk_level="high" if result and result.faithfulness_score < 0.2 else "medium",
            action="no_evidence_answer",
            need_human_review=True,
            answer=answer,
        )
        return {
            "risk_result": risk_result,
            "final_answer": answer,
            "answer_type": "no_evidence",
            "need_human_review": True,
        }

    def build_citations(self, state: QAState):
        citations = []
        sources = []
        for doc in state.get("reranked_docs") or []:
            metadata = getattr(doc, "metadata", {}) or {}
            source = metadata.get("source", "")
            if source and source not in sources:
                sources.append(source)
            citations.append(
                Citation(
                    source=source,
                    parent_id=metadata.get("parent_id", ""),
                    timestamp=metadata.get("timestamp", ""),
                    snippet=(getattr(doc, "page_content", "") or "")[:180],
                )
            )
        return {
            "citations": citations,
            "sources": sources,
            "final_answer": state.get("draft_answer") or "",
            "need_human_review": False,
        }

    def final_answer(self, state: QAState):
        faithfulness = state.get("faithfulness_result")
        result = RAGAnswerResult(
            answer=state.get("final_answer") or state.get("draft_answer") or "",
            answer_type=state.get("answer_type", "rag"),
            trace_id=state["trace_id"],
            citations=state.get("citations") or [],
            sources=state.get("sources") or [],
            faithfulness_score=faithfulness.faithfulness_score if faithfulness else None,
            need_human_review=state.get("need_human_review", False),
            retrieval_strategy=state.get("retrieval_strategy"),
            rewritten_query=state.get("rewritten_query"),
            processing_time=time.time() - state["start_time"],
        )
        return {"result": result}

    def _active_source_filter(self, state: QAState):
        requested_sources = state.get("requested_sources") or []
        final_sources = state.get("final_sources") or []
        if len(requested_sources) == 1 and requested_sources[0] in final_sources:
            return requested_sources[0]
        return None

    def _debug_payload(self, state: QAState):
        docs = state.get("reranked_docs") or state.get("retrieved_chunks") or []
        return {
            "trace_id": state.get("trace_id"),
            "query": state.get("query"),
            "classification": state.get("classification"),
            "keyword_review": state.get("keyword_review", False),
            "final_sources": state.get("final_sources", []),
            "retrieval_strategy": state.get("retrieval_strategy"),
            "rewritten_query": state.get("rewritten_query"),
            "doc_count": len(docs),
            "context_preview": (state.get("context") or "")[:800],
            "documents": [
                {
                    "source": (getattr(doc, "metadata", {}) or {}).get("source", ""),
                    "parent_id": (getattr(doc, "metadata", {}) or {}).get("parent_id", ""),
                    "timestamp": (getattr(doc, "metadata", {}) or {}).get("timestamp", ""),
                    "snippet": (getattr(doc, "page_content", "") or "")[:180],
                }
                for doc in docs
            ],
        }

    def _looks_like_follow_up(self, query: str):
        stripped = query.strip()
        return len(stripped) <= 12 or any(marker in stripped for marker in self.FOLLOW_UP_MARKERS)

    def _format_history(self, history: List[Dict[str, str]]):
        return "\n".join([f"Q:{item.get('question', '')}\nA:{item.get('answer', '')}" for item in history[-5:]])

    def _call_llm_text(self, prompt: str):
        try:
            result = self.rag_system.llm(prompt)
            if isinstance(result, str):
                return result
            return "".join([chunk for chunk in result if chunk])
        except Exception as exc:
            logger.error(f"Graph LLM call failed: {exc}")
            return ""

    def _is_refusal(self, answer: str):
        return any(text in answer for text in ["信息不足", "无法回答", "未明确说明", "联系人工"])

    def _split_claims(self, answer: str):
        return [claim.strip() for claim in re.split(r"[。！？!?\n]", answer) if claim.strip()]

    def _text_support_score(self, answer: str, context: str):
        answer_terms = self._extract_terms(answer)
        context_terms = self._extract_terms(context)
        if not answer_terms:
            return 0.0
        overlap = answer_terms & context_terms
        return len(overlap) / max(len(answer_terms), 1)

    def _extract_terms(self, text: str):
        text = text.lower()
        words = set(re.findall(r"[a-z0-9_+-]{2,}", text))
        chars = {char for char in text if "\u4e00" <= char <= "\u9fff"}
        stop_chars = set("的是了和在与或及对有为中当前根据提供文档可以需要建议问题")
        return words | (chars - stop_chars)
