"""
LangGraph 状态机：L3 智能体核心
流程：意图识别 → 三级检索 → AI生成+入库 → 质量反思 → 记忆更新
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages


# ── 状态定义 ───────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_input: str
    intent: str          # lookup | challenge | recommend | feedback | unknown
    current_word: str
    word_data: Optional[dict]
    ai_content: Optional[str]
    quality_score: float
    retry_count: int
    recommendations: list
    challenge_theme: str
    ui_html: str
    last_word: str


# ── 节点：意图识别 ─────────────────────────────────────────
def node_classify_intent(state: AgentState) -> AgentState:
    text = state.get("user_input", "").strip()

    challenge_kws = ["闯关", "测验", "练习题", "考考我", "出题"]
    recommend_kws = ["相关", "类似", "还有什么", "推荐", "更多"]
    feedback_kws  = ["👍", "好", "有帮助", "点赞", "👎", "不好", "没帮助", "赞", "踩"]

    if any(kw in text for kw in challenge_kws):
        intent = "challenge"
    elif any(kw in text for kw in recommend_kws):
        intent = "recommend"
    elif text in feedback_kws:
        intent = "feedback"
    else:
        intent = "lookup"
        text = re.sub(r"^(查|搜|什么是|解释一下|啥是|帮我查|我想了解)\s*", "", text)
        text = text.rstrip("?？。！～~").strip()

    return {**state, "intent": intent, "current_word": text}


# ── 节点：词库查找（精确 → 模糊） ────────────────────────
def node_retrieve_word(state: AgentState) -> AgentState:
    from agent.tools import retrieve_word
    word = state.get("current_word", "")
    result = retrieve_word(word)
    return {**state, "word_data": result}


# ── 节点：AI 生成（有 Key 用 DS，无 Key 用 Mock） ─────────
def node_generate_content(state: AgentState) -> AgentState:
    from config import USE_MOCK
    from agent.tools import ai_lookup_structured, ai_lookup, mock_generate
    from db.database import save_generated_word

    word  = state.get("current_word", "")
    retry = state.get("retry_count", 0)

    if USE_MOCK:
        mock = mock_generate(word)
        return {**state, "word_data": mock, "ai_content": None, "quality_score": 8.0}

    # 优先结构化输出，失败则降级为文本
    data = ai_lookup_structured(word)
    if data:
        save_generated_word(data)   # 入库，status=pending 等待审核
        return {**state, "word_data": data, "ai_content": None, "quality_score": 8.0, "retry_count": retry}

    content = ai_lookup(word)
    return {**state, "ai_content": content, "retry_count": retry}


# ── 节点：质量反思（DS-R1） ──────────────────────────────
def node_reflect_quality(state: AgentState) -> AgentState:
    from config import USE_MOCK
    from agent.tools import ai_reflect

    if USE_MOCK or not state.get("ai_content"):
        return {**state, "quality_score": 9.0}

    score = ai_reflect(state["ai_content"])
    return {**state, "quality_score": score}


# ── 节点：构建响应 ────────────────────────────────────
def node_build_response(state: AgentState) -> AgentState:
    """建立 ui_html 摘要。FastAPI 模式下由 api.py 自行渲染 HTML。"""
    intent = state.get("intent", "lookup")
    word = state.get("current_word", "")

    if intent == "lookup":
        if state.get("word_data"):
            html = f'[OK] {word}'
        elif state.get("ai_content"):
            html = f'[AI] {word}'
        else:
            html = f'[NF] {word}'
    elif intent == "recommend":
        html = f'[REC] {word}'
    elif intent == "challenge":
        html = f'[CH] {word}'
    elif intent == "feedback":
        html = '[FB] ok'
    else:
        html = f'[??] {word}'

    return {**state, "ui_html": html}


# ── 节点：更新用户记忆 ────────────────────────────────────
def node_update_memory(state: AgentState) -> AgentState:
    from db.database import mark_learned

    word_data = state.get("word_data")
    if word_data and state.get("intent") == "lookup":
        mark_learned(word_data["word"])

    return {
        **state,
        "last_word": state.get("current_word", state.get("last_word", "")),
    }


# ── 节点：推荐相关词 ──────────────────────────────────────
def node_get_recommendations(state: AgentState) -> AgentState:
    from agent.tools import get_recommendations
    from db.database import search_word

    last = state.get("last_word", "")
    word_data = search_word(last) if last else None
    recs = []
    if word_data:
        recs = get_recommendations(word_data.get("related", []), exclude=last)

    return {**state, "recommendations": recs}


# ── 条件路由 ──────────────────────────────────────────────
def route_after_classify(state: AgentState) -> str:
    return state.get("intent", "lookup")


def route_after_retrieve(state: AgentState) -> str:
    return "build_response" if state.get("word_data") else "generate"


def route_after_reflect(state: AgentState) -> str:
    from config import QUALITY_THRESHOLD, MAX_RETRIES
    score = state.get("quality_score", 10.0)
    retry = state.get("retry_count", 0)
    if score < QUALITY_THRESHOLD and retry < MAX_RETRIES:
        return "generate"
    return "build_response"


# ── 构建图 ────────────────────────────────────────────────
def build_graph():
    g = StateGraph(AgentState)

    g.add_node("classify",      node_classify_intent)
    g.add_node("retrieve",      node_retrieve_word)
    g.add_node("generate",      node_generate_content)
    g.add_node("reflect",       node_reflect_quality)
    g.add_node("recommend",     node_get_recommendations)
    g.add_node("build_response", node_build_response)
    g.add_node("update_memory", node_update_memory)

    g.set_entry_point("classify")

    g.add_conditional_edges(
        "classify", route_after_classify,
        {"lookup": "retrieve", "recommend": "recommend",
         "challenge": "build_response", "feedback": "build_response", "unknown": "build_response"},
    )
    g.add_conditional_edges(
        "retrieve", route_after_retrieve,
        {"build_response": "build_response", "generate": "generate"},
    )
    g.add_edge("generate", "reflect")
    g.add_conditional_edges(
        "reflect", route_after_reflect,
        {"generate": "generate", "build_response": "build_response"},
    )
    g.add_edge("recommend",     "build_response")
    g.add_edge("build_response", "update_memory")
    g.add_edge("update_memory", END)

    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_agent(user_input: str, last_word: str = "") -> dict:
    graph = get_graph()
    init_state: AgentState = {
        "messages":       [],
        "user_input":     user_input,
        "intent":         "",
        "current_word":   "",
        "word_data":      None,
        "ai_content":     None,
        "quality_score":  0.0,
        "retry_count":    0,
        "recommendations": [],
        "challenge_theme": "",
        "ui_html":        "",
        "last_word":      last_word,
    }
    return graph.invoke(init_state)
