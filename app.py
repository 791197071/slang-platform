"""
网络用语智能学习平台 · 主入口
"""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gradio as gr
from db import database as db
from agent.graph import run_agent
from agent.tools import (
    build_challenge_question, render_word_card,
    render_initial_display, THEME_TAG_MAP,
)

db.init_db()
THEMES         = list(THEME_TAG_MAP.keys())
CHALLENGE_SIZE = 5
SETTINGS_FILE  = Path(__file__).parent / "settings.json"

# ══════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════
CSS = """
/* ── 全局 ──────────────────────────────────────────── */
html, body {
  overflow: hidden !important;
  height: 100vh !important;
  margin: 0 !important; padding: 0 !important;
  font-family: 'PingFang SC','Microsoft YaHei',system-ui,sans-serif !important;
  background: #ECEAFF !important;
}
footer, .footer, #footer,
a[href*="gradio.app"], .built-with, .show-api { display: none !important; }

/* ── Gradio 容器：缩到 0，不占空间 ────────────────── */
.gradio-container {
  max-width: 100% !important;
  height: 0 !important;
  overflow: visible !important;
  padding: 0 !important; margin: 0 !important;
  background: transparent !important;
}

/* ══════════════════════════════════════════════════
   主布局行：position:fixed 锚定视口
   完全绕开 Gradio 内部 div 层级，不依赖 height 传递
   ══════════════════════════════════════════════════ */
.app-row {
  position: fixed !important;
  inset: 0 !important;          /* top:0 right:0 bottom:0 left:0 */
  z-index: 10 !important;
  display: flex !important;
  flex-direction: row !important;
  align-items: stretch !important;
  flex-wrap: nowrap !important;
  overflow: hidden !important;
  background: #ECEAFF !important;
}

/* ── 侧边栏 ───────────────────────────────────────── */
.sidebar-col {
  flex: 0 0 210px !important;
  width: 210px !important;
  height: 100% !important;
  overflow: hidden !important;
  background: linear-gradient(180deg,#1B1254 0%,#2D1875 55%,#3D2098 100%) !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 0 !important;
}
.sidebar-col .block {
  background: transparent !important;
  border: none !important; box-shadow: none !important;
  padding: 0 !important; border-radius: 0 !important;
}
.sb-logo {
  padding: 26px 18px 20px !important;
  border-bottom: 1px solid rgba(255,255,255,.1) !important;
  margin-bottom: 8px !important; flex-shrink: 0 !important;
}
.sb-icon  { font-size:2rem; display:block; line-height:1; margin-bottom:8px; }
.sb-title { font-size:1.1rem; font-weight:800; color:#fff; letter-spacing:-.2px; }
.sb-sub   { font-size:.7rem; color:rgba(255,255,255,.38); margin-top:4px; }
/* 导航按钮 */
.sidebar-col button {
  all: unset !important;
  display: flex !important; align-items: center !important;
  width: 100% !important; padding: 12px 18px !important;
  font-size: .88rem !important; font-weight: 500 !important;
  color: rgba(255,255,255,.5) !important;
  cursor: pointer !important; transition: all .15s !important;
  box-sizing: border-box !important;
  border-left: 3px solid transparent !important;
}
.sidebar-col button:hover {
  background: rgba(255,255,255,.07) !important;
  color: rgba(255,255,255,.88) !important;
}
.sidebar-col button.primary {
  background: rgba(255,255,255,.13) !important;
  color: #fff !important; font-weight: 700 !important;
  border-left-color: #A78BFA !important;
}

/* ── 内容区 ───────────────────────────────────────── */
.content-col {
  flex: 1 !important;
  min-width: 0 !important;
  height: 100% !important;
  overflow: hidden !important;
  padding: 16px 20px !important;
  box-sizing: border-box !important;
  display: flex !important;
  flex-direction: column !important;
}
/* Gradio 在 Column 里插入的所有 block 包装全部透传 */
.content-col .block {
  background: transparent !important;
  border: none !important; box-shadow: none !important; padding: 0 !important;
}

/* ── Tabs（隐藏导航栏，填满内容区） ───────────────── */
.main-tabs {
  flex: 1 !important;
  min-height: 0 !important;
  overflow: hidden !important;
}
.main-tabs > div { height: 100% !important; overflow: hidden !important; }
.main-tabs [role="tablist"],
.main-tabs .tab-nav { display: none !important; }
/* 只设高度和样式，不覆盖 display——让 Gradio 自己控制 tab 显示/隐藏 */
.main-tabs .tabitem {
  height: 100% !important;
  overflow: hidden !important;
  padding: 0 !important; border: none !important;
  background: transparent !important;
  box-sizing: border-box !important;
}

/* ── 可滚动页面包装（闯关/进度/管理/设置） ──────── */
.page-scroll {
  height: 100% !important;
  overflow-y: auto !important; overflow-x: hidden !important;
  scrollbar-width: none !important;
  box-sizing: border-box !important;
  padding-bottom: 24px !important;
}
.page-scroll::-webkit-scrollbar { display: none !important; }
.page-scroll .block {
  background: transparent !important;
  border: none !important; box-shadow: none !important; padding: 0 !important;
}

/* ── 聊天页布局 ───────────────────────────────────── */
.chat-row {
  height: 100% !important; overflow: hidden !important;
  gap: 16px !important; align-items: stretch !important;
  flex-wrap: nowrap !important;
}
.chat-left {
  height: 100% !important; overflow: hidden !important;
  display: flex !important; flex-direction: column !important;
  gap: 8px !important;
}
.chat-left .block {
  background: transparent !important;
  border: none !important; box-shadow: none !important; padding: 0 !important;
}
/* 词条展示右栏（薄滚动条） */
.word-panel {
  height: 100% !important;
  overflow-y: auto !important; overflow-x: hidden !important;
  scrollbar-width: thin !important;
  scrollbar-color: #C4B5FD #ECEAFF !important;
}
.word-panel::-webkit-scrollbar { width: 5px !important; }
.word-panel::-webkit-scrollbar-thumb { background:#C4B5FD !important; border-radius:3px !important; }
.word-panel .block {
  background: transparent !important;
  border: none !important; box-shadow: none !important; padding: 0 !important;
}

/* ── 节标题 ─────────────────────────────────────── */
.sec-lbl {
  font-size: .74rem; color: #A0A0BE;
  letter-spacing: .08em; text-transform: uppercase;
  margin: 0 0 8px; padding: 0;
}

/* ── 输入框 & 发送 ─────────────────────────────── */
#word-input textarea {
  border-radius: 12px !important; border: 1.5px solid #DDD6FE !important;
  font-size: .92rem !important; resize: none !important;
  transition: border-color .2s, box-shadow .2s !important;
}
#word-input textarea:focus {
  border-color: #7C3AED !important;
  box-shadow: 0 0 0 3px rgba(124,58,237,.1) !important; outline: none !important;
}
#send-btn {
  background: linear-gradient(135deg,#7C3AED,#A855F7) !important;
  color: #fff !important; border: none !important; border-radius: 12px !important;
  font-weight: 700 !important; box-shadow: 0 2px 10px rgba(124,58,237,.28) !important;
  transition: opacity .18s !important; white-space: nowrap !important;
}
#send-btn:hover { opacity: .85 !important; }

/* ── 词条卡片 ─────────────────────────────────── */
.word-card {
  background: #fff; border-radius: 18px;
  padding: 24px 26px; margin-bottom: 14px;
  box-shadow: 0 2px 16px rgba(66,32,144,.07);
  border: 1px solid #EDE9FE;
}
.word-card-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px; }
.word-title  { font-size:1.85rem; font-weight:800; color:#1A1550; line-height:1.15; }
.word-meaning{ color:#374151; font-size:.96rem; line-height:1.8; margin:10px 0 14px; }
.sentiment-badge { display:inline-block; padding:3px 12px; border-radius:20px; font-size:.81rem; background:#EDE9FE; color:#5B21B6; margin-bottom:12px; }
.quality-score { font-size:.7rem; color:#A0A0BE; padding:2px 8px; background:#F9F9FC; border-radius:8px; border:1px solid #E5E7EB; flex-shrink:0; }
.ai-source-badge { font-size:.7rem; padding:2px 8px; border-radius:8px; background:#FFFBEB; color:#92400E; border:1px solid #FDE68A; flex-shrink:0; }
/* 场景 */
.scenario-card { background:#F8F8FD; border-radius:12px; padding:14px 18px; margin:8px 0; border:1px solid #EBEBF5; }
.scene-header  { font-weight:700; color:#1A1550; margin-bottom:3px; font-size:.91rem; }
.scene-context { color:#A0A0BE; font-size:.79rem; margin-bottom:10px; }
.dialogue-box  { display:flex; flex-direction:column; gap:7px; }
.msg      { padding:8px 13px; border-radius:12px; font-size:.9rem; max-width:82%; line-height:1.55; }
.other-msg{ background:#EFEFF6; color:#1F2937; align-self:flex-start; border-bottom-left-radius:3px; }
.self-msg { background:#EDE9FE; color:#4C1D95; align-self:flex-end; border-bottom-right-radius:3px; }
.speaker  { font-weight:700; color:#6D28D9; margin-right:3px; }
/* 贴士 & 标签 */
.tips-box { background:#FFFBEB; border-radius:10px; padding:10px 14px; color:#92400E; font-size:.87rem; margin-top:10px; border:1px solid rgba(251,191,36,.2); }
.related-section { margin-top:12px; }
.related-label { color:#A0A0BE; font-size:.82rem; }
.tag-btn  { display:inline-block; padding:3px 11px; background:#EDE9FE; color:#5B21B6; border-radius:18px; font-size:.81rem; margin:2px 3px; border:1px solid #C4B5FD; }
.rec-header { font-size:.96rem; font-weight:700; color:#1A1550; margin:0 0 10px; }
/* 占位 */
.display-placeholder { text-align:center; padding:60px 24px; color:#A0A0BE; }
.placeholder-icon  { font-size:3rem; margin-bottom:14px; }
.placeholder-title { font-size:1.1rem; font-weight:600; color:#6B7280; margin-bottom:8px; }
.placeholder-desc  { font-size:.9rem; margin-bottom:18px; line-height:1.6; }
.placeholder-examples { display:inline-block; padding:7px 18px; background:#F0EEFF; border-radius:18px; font-size:.85rem; color:#5B21B6; border:1px solid #DDD6FE; }

/* ── 闯关 ─────────────────────────────────────── */
.challenge-card {
  background:#fff; border-radius:16px; padding:24px 28px;
  border-left:4px solid #7C3AED;
  box-shadow:0 2px 14px rgba(66,32,144,.06);
  white-space:pre-wrap; font-size:.96rem; line-height:1.75;
  color:#1F2937; margin-bottom:14px;
}
.progress-bar  { height:4px; background:#EDE9FE; border-radius:4px; margin:8px 0 18px; }
.progress-fill { height:100%; background:linear-gradient(90deg,#7C3AED,#A855F7); border-radius:4px; transition:width .4s; }

/* ── 进度统计 ─────────────────────────────────── */
.stats-card { background:#fff; border-radius:16px; padding:20px 24px; margin-bottom:14px; box-shadow:0 1px 12px rgba(66,32,144,.05); border:1px solid #EDE9FE; }
.stat-num   { font-size:2rem; font-weight:800; color:#1A1550; line-height:1.1; }
.stat-label { color:#7C7C9A; font-size:.83rem; margin-top:3px; }

/* ── 管理面板 ─────────────────────────────────── */
.admin-hint { background:#F5F3FF; border-radius:12px; padding:14px 16px; font-size:.82rem; color:#5B21B6; line-height:1.8; border:1px solid #DDD6FE; }
.save-ok    { background:#D1FAE5; color:#065F46; border-radius:10px; padding:10px 14px; font-size:.9rem; margin-top:8px; }
.save-err   { background:#FEE2E2; color:#991B1B; border-radius:10px; padding:10px 14px; font-size:.9rem; margin-top:8px; }

/* ── 设置页 ───────────────────────────────────── */
.settings-card {
  background:#fff; border-radius:16px; padding:28px 32px;
  box-shadow:0 1px 12px rgba(66,32,144,.06); border:1px solid #EDE9FE;
  margin-bottom:16px;
}
"""


# ══════════════════════════════════════════════════════
# 设置
# ══════════════════════════════════════════════════════

def _read_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_settings(api_key, base_url, main_model, reflect_model, threshold):
    data = {
        "DEEPSEEK_API_KEY":  api_key.strip(),
        "DEEPSEEK_BASE_URL": base_url.strip() or "https://api.deepseek.com/v1",
        "MAIN_MODEL":        main_model,
        "REFLECT_MODEL":     reflect_model,
        "QUALITY_THRESHOLD": float(threshold),
    }
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    import config as cfg; importlib.reload(cfg)
    import agent.graph as g; g._graph = None
    if api_key.strip():
        return '<div class="save-ok">✅ 已保存，AI 模式已激活！下次查词将调用 DeepSeek</div>'
    return '<div class="save-ok">💡 已保存（未填 Key，使用本地词库模式）</div>'


# ══════════════════════════════════════════════════════
# 聊天
# ══════════════════════════════════════════════════════

def do_lookup(user_input: str, last_word: str, history: list):
    if not user_input.strip():
        return history, "", last_word, render_initial_display()
    result   = run_agent(user_input.strip(), last_word)
    html     = result.get("ui_html", render_initial_display())
    word_data= result.get("word_data")
    new_last = result.get("last_word", last_word)
    history  = list(history or [])
    history.append({"role": "user",      "content": user_input.strip()})
    ack = f"✅ 找到「{word_data['word']}」→ 右侧已展示" if word_data \
          else f"🔍 未找到「{user_input.strip()}」"
    history.append({"role": "assistant", "content": ack})
    return history, "", new_last, html


def do_feedback(val: int, last_word: str):
    if last_word:
        db.update_feedback(last_word, val)
        if val == 1:
            return '<span style="color:#065F46;font-size:.84rem">👍 已记录，质量分 +0.5</span>'
        return '<span style="color:#991B1B;font-size:.84rem">👎 已记录，感谢反馈！</span>'
    return ""


# ══════════════════════════════════════════════════════
# 闯关
# ══════════════════════════════════════════════════════

def start_challenge(theme: str, ch_state: dict):
    tag     = THEME_TAG_MAP.get(theme, "日常")
    learned = db.get_learned_words()
    words   = db.get_words_by_tag(tag, exclude=learned, limit=CHALLENGE_SIZE)
    if len(words) < 2:
        words = db.get_words_by_tag(tag, limit=CHALLENGE_SIZE)
    if not words:
        return (ch_state,
                '<div class="challenge-card">该主题暂无题目，先去聊天学几个词吧～</div>',
                gr.update(visible=False), gr.update(visible=False))
    questions = [build_challenge_question(w, words) for w in words]
    ch_state  = {"theme": theme, "questions": questions, "current": 0, "score": 0}
    return ch_state, _render_q(ch_state), gr.update(visible=True), gr.update(visible=True)


def _render_q(s: dict) -> str:
    idx, qs, total = s["current"], s["questions"], len(s["questions"])
    if idx >= total:
        sc  = s["score"]
        icon = "🎉" if sc >= 4 else "💪"
        msg  = "恭喜通关！" if sc >= 4 else "再接再厉！"
        return (f'<div class="challenge-card">{icon} {msg}\n\n'
                f'本组得分：{sc}/{total}\n\n点"下一组"继续挑战！</div>')
    q     = qs[idx]
    opts  = "\n".join(f"{k}. {v}" for k, v in q["options"].items())
    bar_w = int(idx / total * 100)
    return (
        f'<div class="challenge-card">'
        f'<span style="color:#A0A0BE;font-size:.8rem">第 {idx+1}/{total} 题</span>'
        f'<div class="progress-bar"><div class="progress-fill" style="width:{bar_w}%"></div></div>'
        f'{q["question"]}\n\n{opts}</div>'
    )


def answer_challenge(choice: str, ch_state: dict):
    if not ch_state or not ch_state.get("questions"):
        return ch_state, '<div class="challenge-card">请先选择主题开始～</div>'
    idx, qs = ch_state["current"], ch_state["questions"]
    if idx >= len(qs):
        return ch_state, _render_q(ch_state)
    q  = qs[idx]
    ok = choice.upper() == q["answer"]
    if ok:
        ch_state["score"] += 1
        fb = f"✅ 正确！\n{q['explanation']}"
    else:
        fb = f"❌ 答案是 {q['answer']}。\n{q['explanation']}"
    ch_state["current"] += 1
    nxt   = _render_q(ch_state)
    inner = nxt[len('<div class="challenge-card">'):-len("</div>")]
    return ch_state, f'<div class="challenge-card">{fb}\n\n---\n\n{inner}'


# ══════════════════════════════════════════════════════
# 进度
# ══════════════════════════════════════════════════════

def get_progress_html():
    s   = db.get_user_stats()
    rec = "".join(f'<span class="tag-btn">{r["word"]}</span>' for r in s["recent"]) \
          or '<span style="color:#A0A0BE">还没有学习记录，快去查词吧～</span>'
    rows = ""
    for c in s.get("challenges", []):
        pct = int(c["correct"] / max(c["total"], 1) * 100)
        rows += (
            f'<div style="margin:8px 0">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
            f'<span style="color:#374151;font-weight:500">{c["theme"]}</span>'
            f'<span style="color:#A0A0BE;font-size:.82rem">{c["correct"]}/{c["total"]} ({pct}%)</span>'
            f'</div><div class="progress-bar"><div class="progress-fill" style="width:{pct}%"></div></div></div>'
        )
    rows = rows or '<div style="color:#A0A0BE;font-size:.88rem">还没有闯关记录</div>'
    return f"""
<div class="stats-card">
  <div style="display:flex;gap:36px;flex-wrap:wrap;margin-bottom:18px">
    <div><div class="stat-num">{s['total_learned']}</div><div class="stat-label">已学词汇</div></div>
    <div><div class="stat-num">{s['like_rate']}%</div><div class="stat-label">好评率</div></div>
    <div><div class="stat-num">{s.get('ai_count',0)}</div><div class="stat-label">AI 词条</div></div>
    <div><div class="stat-num">{s.get('pending_count',0)}</div><div class="stat-label">待审核</div></div>
  </div>
  <div style="font-weight:700;color:#1A1550;margin-bottom:10px;font-size:.93rem">最近学习</div>
  <div style="line-height:2">{rec}</div>
</div>
<div class="stats-card">
  <div style="font-weight:700;color:#1A1550;margin-bottom:14px;font-size:.93rem">闯关记录</div>
  {rows}
</div>"""


# ══════════════════════════════════════════════════════
# 管理
# ══════════════════════════════════════════════════════

_SL = {"approved": "✅ 已审核", "pending": "⏳ 待审核", "rejected": "❌ 已拒绝"}
_AL = {0: "内置", 1: "🤖 AI"}


def load_admin_table(search="", sf="全部"):
    rows = db.get_all_words_admin(search, sf)
    return [[r[0], _SL.get(r[1], r[1]), f"{r[2]:.1f}", _AL.get(r[3], r[3]), r[4]] for r in rows]


def on_word_select(evt: gr.SelectData):
    word = str(evt.value).strip()
    data = db.get_word_for_edit(word)
    if not data:
        return gr.update(), "", "", "[]", "approved", ""
    scen = json.dumps(data.get("scenarios", []), ensure_ascii=False, indent=2)
    return (
        f"### ✏️ 编辑：{word}",
        data.get("meaning", ""),
        data.get("use_tips", ""),
        scen,
        data.get("status", "approved"),
        word,
    )


def save_word_edits(word, meaning, tips, scen_json, status):
    if not word:
        return '<div class="save-err">请先点击表格中的词语</div>'
    ok, msg = db.update_word_admin(word, meaning, tips, scen_json, status)
    cls = "save-ok" if ok else "save-err"
    return f'<div class="{cls}">{msg}</div>'


# ══════════════════════════════════════════════════════
# UI 构建
# ══════════════════════════════════════════════════════

def build_ui():
    saved = _read_settings()

    with gr.Blocks(title="梗导师 · 网络用语学习") as demo:
        last_word_st = gr.State("")
        ch_st        = gr.State({})
        edit_word_st = gr.State("")

        with gr.Row(elem_classes=["app-row"]):

            # ════ 侧边栏（fixed 210px，CSS 控制宽度） ════
            with gr.Column(scale=0, min_width=210, elem_classes=["sidebar-col"]):
                gr.HTML("""
<div class="sb-logo">
  <span class="sb-icon">🎓</span>
  <div class="sb-title">梗导师</div>
  <div class="sb-sub">网络用语智能学习</div>
</div>
""")
                btn_chat      = gr.Button("💬  聊天学习",   variant="primary")
                btn_challenge = gr.Button("🎯  主题闯关",   variant="secondary")
                btn_progress  = gr.Button("📊  我的进度",   variant="secondary")
                btn_admin     = gr.Button("🔧  知识库管理", variant="secondary")
                btn_settings  = gr.Button("⚙️  系统设置",   variant="secondary")

            # ════ 内容区 ════
            with gr.Column(scale=5, min_width=600, elem_classes=["content-col"]):
                with gr.Tabs(elem_classes=["main-tabs"]) as tabs:

                    # ── Tab 0: 聊天 ──────────────────────────
                    with gr.Tab("chat", id=0):
                        with gr.Row(elem_classes=["chat-row"]):

                            # 左栏：对话 + 输入
                            with gr.Column(scale=4, min_width=280,
                                           elem_classes=["chat-left"]):
                                gr.HTML('<p class="sec-lbl">输入网络用语，学姐带你秒懂</p>')
                                chatbot = gr.Chatbot(
                                    value=[],
                                    height=430,
                                    show_label=False,
                                    render_markdown=True,
                                    sanitize_html=False,
                                    elem_id="main-chatbot",
                                    placeholder="直接输入，比如：破防了、内卷、YYDS…",
                                )
                                with gr.Row():
                                    word_input = gr.Textbox(
                                        placeholder="输入网络用语，按回车或点发送",
                                        show_label=False, scale=5,
                                        lines=1, elem_id="word-input",
                                    )
                                    send_btn = gr.Button(
                                        "发送", scale=1, elem_id="send-btn",
                                    )
                                with gr.Row():
                                    gr.HTML('<span style="color:#A0A0BE;font-size:.82rem;line-height:28px">有帮助吗？</span>')
                                    like_btn    = gr.Button("👍 有帮助", size="sm", scale=1)
                                    dislike_btn = gr.Button("👎 没帮助", size="sm", scale=1)
                                    feedback_msg = gr.HTML(scale=2)

                            # 右栏：词条展示（可滚动）
                            with gr.Column(scale=6, min_width=360,
                                           elem_classes=["word-panel"]):
                                word_display = gr.HTML(value=render_initial_display())

                        send_btn.click(
                            do_lookup,
                            [word_input, last_word_st, chatbot],
                            [chatbot, word_input, last_word_st, word_display],
                        )
                        word_input.submit(
                            do_lookup,
                            [word_input, last_word_st, chatbot],
                            [chatbot, word_input, last_word_st, word_display],
                        )
                        like_btn.click(
                            lambda lw: do_feedback(1, lw), [last_word_st], [feedback_msg]
                        )
                        dislike_btn.click(
                            lambda lw: do_feedback(-1, lw), [last_word_st], [feedback_msg]
                        )

                    # ── Tab 1: 闯关 ──────────────────────────
                    with gr.Tab("challenge", id=1):
                        with gr.Column(elem_classes=["page-scroll"]):
                            gr.HTML('<p class="sec-lbl">主题闯关 · 每组 5 题，答对 4 题通关</p>')
                            with gr.Row():
                                theme_radio = gr.Radio(
                                    choices=THEMES, value=THEMES[0],
                                    label="选择挑战主题", scale=4,
                                )
                                start_btn = gr.Button(
                                    "开始闯关 🚀", variant="primary",
                                    scale=1, min_width=130,
                                )
                            challenge_html = gr.HTML(
                                '<div class="challenge-card">选择主题后点击「开始闯关」开始测验～</div>'
                            )
                            with gr.Row(visible=False) as ans_row:
                                ba = gr.Button("A", scale=1)
                                bb = gr.Button("B", scale=1)
                                bc = gr.Button("C", scale=1)
                                bd = gr.Button("D", scale=1)
                            with gr.Row(visible=False) as next_row:
                                next_btn = gr.Button("下一组题目 →", variant="primary")

                        start_btn.click(
                            start_challenge,
                            [theme_radio, ch_st],
                            [ch_st, challenge_html, ans_row, next_row],
                        )
                        for _b, _c in [(ba, "A"), (bb, "B"), (bc, "C"), (bd, "D")]:
                            _b.click(
                                lambda s, c=_c: answer_challenge(c, s),
                                [ch_st], [ch_st, challenge_html],
                            )
                        next_btn.click(
                            lambda t, _s: start_challenge(t, {}),
                            [theme_radio, ch_st],
                            [ch_st, challenge_html, ans_row, next_row],
                        )

                    # ── Tab 2: 进度 ──────────────────────────
                    with gr.Tab("progress", id=2):
                        with gr.Column(elem_classes=["page-scroll"]):
                            with gr.Row():
                                gr.HTML('<p class="sec-lbl" style="margin:0;line-height:28px">学习统计与成就记录</p>')
                                ref_btn = gr.Button("🔄 刷新", size="sm", scale=0)
                            progress_html = gr.HTML(value=get_progress_html())

                        ref_btn.click(get_progress_html, [], [progress_html])

                    # ── Tab 3: 管理 ──────────────────────────
                    with gr.Tab("admin", id=3):
                        with gr.Column(elem_classes=["page-scroll"]):
                            gr.HTML('<p class="sec-lbl">知识库管理 · AI 词条审核</p>')
                            with gr.Row():
                                adm_search  = gr.Textbox(
                                    placeholder="搜索词语…",
                                    show_label=False, scale=4,
                                )
                                adm_filter  = gr.Dropdown(
                                    ["全部", "已审核", "待审核", "AI生成"],
                                    value="全部", show_label=False, scale=2,
                                )
                                adm_ref_btn = gr.Button("🔄", scale=0, min_width=48)
                            word_table = gr.Dataframe(
                                headers=["词语", "状态", "质量分", "来源", "查询次数"],
                                value=load_admin_table(),
                                interactive=False,
                                label="点击行选择要编辑的词条",
                            )
                            gr.HTML('<p class="sec-lbl" style="margin-top:18px">编辑词条</p>')
                            with gr.Row():
                                with gr.Column(scale=6):
                                    edit_title = gr.Markdown("*← 点击上方表格选择词条*")
                                    edit_meaning   = gr.Textbox(label="📖 词义", lines=2)
                                    edit_tips      = gr.Textbox(label="💡 使用贴士", lines=1)
                                    edit_scenarios = gr.Code(
                                        label="🎬 场景 JSON", language="json", lines=8
                                    )
                                with gr.Column(scale=3):
                                    edit_status   = gr.Dropdown(
                                        ["approved", "pending", "rejected"],
                                        label="审核状态", value="approved",
                                    )
                                    save_edit_btn = gr.Button("💾 保存", variant="primary")
                                    edit_msg      = gr.HTML()
                                    gr.HTML("""<div class="admin-hint">
<b>状态说明</b><br>
✅ approved — 正常展示<br>
⏳ pending — AI 生成待审核<br>
❌ rejected — 不对外展示<br><br>
<b>质量分机制</b><br>
👍 点赞 +0.5 分<br>
👎 踩 −0.3 分<br>
分数影响闯关出题优先级</div>""")

                        def _rt(s, sf): return load_admin_table(s, sf)
                        word_table.select(
                            on_word_select, [],
                            [edit_title, edit_meaning, edit_tips,
                             edit_scenarios, edit_status, edit_word_st],
                        )
                        save_edit_btn.click(
                            save_word_edits,
                            [edit_word_st, edit_meaning, edit_tips,
                             edit_scenarios, edit_status],
                            [edit_msg],
                        )
                        save_edit_btn.click(_rt, [adm_search, adm_filter], [word_table])
                        adm_ref_btn.click(_rt, [adm_search, adm_filter], [word_table])
                        adm_search.submit(_rt, [adm_search, adm_filter], [word_table])
                        adm_filter.change(_rt, [adm_search, adm_filter], [word_table])

                    # ── Tab 4: 设置 ──────────────────────────
                    with gr.Tab("settings", id=4):
                        with gr.Column(elem_classes=["page-scroll"]):
                            gr.HTML('<p class="sec-lbl">API 配置与学习参数</p>')
                            with gr.Column(elem_classes=["settings-card"]):
                                gr.Markdown("#### 🔑 DeepSeek API 配置")
                                api_key_in = gr.Textbox(
                                    label="API Key", type="password",
                                    placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx",
                                    value=saved.get("DEEPSEEK_API_KEY", ""),
                                    info="在 platform.deepseek.com 获取",
                                )
                                base_url_in = gr.Textbox(
                                    label="Base URL",
                                    value=saved.get("DEEPSEEK_BASE_URL",
                                                    "https://api.deepseek.com/v1"),
                                )
                                with gr.Row():
                                    main_model_in = gr.Dropdown(
                                        ["deepseek-chat", "deepseek-v3"],
                                        label="生成模型",
                                        value=saved.get("MAIN_MODEL", "deepseek-chat"),
                                    )
                                    reflect_model_in = gr.Dropdown(
                                        ["deepseek-reasoner", "deepseek-r1"],
                                        label="反思模型",
                                        value=saved.get("REFLECT_MODEL", "deepseek-reasoner"),
                                    )
                                gr.Markdown("#### 📊 学习参数")
                                threshold_in = gr.Slider(
                                    minimum=5.0, maximum=9.5, step=0.5,
                                    label="质量阈值（低于此分时重新生成）",
                                    value=float(saved.get("QUALITY_THRESHOLD", 7.0)),
                                )
                            save_cfg_btn = gr.Button("💾 保存设置", variant="primary")
                            cfg_msg = gr.HTML()

                        save_cfg_btn.click(
                            save_settings,
                            [api_key_in, base_url_in, main_model_in,
                             reflect_model_in, threshold_in],
                            [cfg_msg],
                        )

        # ── 侧边栏导航 ─────────────────────────────────
        _nav_out = [tabs, btn_chat, btn_challenge, btn_progress, btn_admin, btn_settings]

        def _nav(i):
            vs = ["secondary"] * 5
            vs[i] = "primary"
            return (gr.update(selected=i), *[gr.update(variant=v) for v in vs])

        btn_chat.click(      lambda: _nav(0), outputs=_nav_out)
        btn_challenge.click( lambda: _nav(1), outputs=_nav_out)
        btn_progress.click(  lambda: _nav(2), outputs=_nav_out)
        btn_admin.click(     lambda: _nav(3), outputs=_nav_out)
        btn_settings.click(  lambda: _nav(4), outputs=_nav_out)

    return demo


if __name__ == "__main__":
    print("启动中… http://localhost:7860")
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
        css=CSS,
    )
