"""API 路由：返回 HTML 片段供 htmx 交换"""
from __future__ import annotations

import html
import json
import random
import importlib
import sys
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import database as db
from agent.graph import run_agent
from agent.tools import build_challenge_question

router = APIRouter(prefix="/api")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

CHALLENGE_SIZE = 5
SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

_SENT_LABEL = {"positive": "正向 😊", "negative": "负向 😔", "neutral": "中性 😐"}
_SENT_TAG  = {"positive": "ant-tag-green", "negative": "ant-tag-red", "neutral": "ant-tag-blue"}
_SENT_ICON = {"positive": "😊", "negative": "😔", "neutral": "😐"}

# ══════════════════════════════════════════════
# 模板渲染辅助
# ══════════════════════════════════════════════

def _render(template: str, ctx: dict | None = None) -> HTMLResponse:
    """渲染一个 partial 模板（不依赖 request，只传最小上下文）"""
    return templates.TemplateResponse(template, {"request": EmptyRequest(), **(ctx or {})})


class EmptyRequest:
    """Starlette 模板引擎需要 request 对象，提供一个最小模拟。"""
    def get(self, key, default=None): return default
    url = type("U", (), {"path": "/"})()


def _oob(id_: str, html: str) -> str:
    """生成 htmx OOB swap 片段"""
    return f'<div id="{id_}" hx-swap-oob="true">{html}</div>'


# ══════════════════════════════════════════════
# 聊天
# ══════════════════════════════════════════════

@router.post("/chat/lookup", response_class=HTMLResponse)
async def chat_lookup(
    request: Request,
    user_input: str = Form(""),
    last_word: str = Form(""),
):
    word = user_input.strip()
    if not word:
        return HTMLResponse("")

    result = run_agent(word, last_word)
    word_data = result.get("word_data")
    ai_content = result.get("ai_content", "")
    new_last = result.get("last_word", word)

    # 构建响应：主体是左栏内容，OOB 替换右栏 + 清空输入 + 更新 last_word
    parts = []

    # 左栏
    if word_data:
        left_html = _render_scenarios(word_data)
        right_html = _render_details(word_data)
    elif ai_content:
        left_html = _render_ai_text(word, ai_content)
        right_html = _right_placeholder()
    else:
        left_html = _render_not_found_left(word)
        right_html = _render_not_found_right()

    parts.append(left_html)
    parts.append(_oob("word-detail", right_html))
    parts.append(_oob("last-word", f'<input type="hidden" id="last-word" name="last_word" value="{new_last}">'))

    return HTMLResponse("\n".join(parts))


@router.post("/chat/feedback", response_class=HTMLResponse)
async def chat_feedback(
    val: int = Form(0),
    last_word: str = Form(""),
):
    if last_word:
        db.update_feedback(last_word, val)
        if val == 1:
            return HTMLResponse('<span style="color:#389e0d;font-size:13px">👍 已记录，质量分 +0.5</span>')
        return HTMLResponse('<span style="color:#cf1322;font-size:13px">👎 已记录，感谢反馈</span>')
    return HTMLResponse("")


# ══════════════════════════════════════════════
# 闯关
# ══════════════════════════════════════════════

@router.post("/challenge/start", response_class=HTMLResponse)
async def challenge_start():
    all_words = db.get_words_for_challenge(limit=60)
    if len(all_words) < 2:
        return _render("partials/challenge/init.html", {
            "error": "题库词条不足（至少需要 2 个），请在「题库管理」中添加词条"
        })

    random.shuffle(all_words)
    words = all_words[:CHALLENGE_SIZE]
    questions = [build_challenge_question(w, all_words) for w in words]
    state = {"questions": questions, "current": 0, "score": 0}
    state_json = json.dumps(state, ensure_ascii=False)
    state_escaped = html.escape(state_json, quote=True)

    return _render_q(0, questions, 0, state_escaped)


@router.post("/challenge/answer", response_class=HTMLResponse)
async def challenge_answer(
    choice: str = Form(""),
    ch_state: str = Form(""),
):
    if not ch_state:
        return HTMLResponse('<div class="ch-question-card" style="text-align:center;padding:32px;color:rgba(0,0,0,.45)">请先点击「开始闯关」~</div>')

    try:
        # HTML 实体反转义后再解析 JSON
        state = json.loads(html.unescape(ch_state))
    except json.JSONDecodeError:
        return HTMLResponse('<div class="ch-question-card" style="text-align:center;padding:32px;color:rgba(0,0,0,.45)">状态数据异常，请重新开始</div>')

    questions = state.get("questions", [])
    current = state.get("current", 0)
    score = state.get("score", 0)

    if current >= len(questions):
        return _render_challenge_result(score, len(questions))

    q = questions[current]
    correct = choice.upper() == q["answer"]

    if correct:
        score += 1
        fb = f'<div class="ch-feedback ch-fb-ok">✅ 回答正确！{q["explanation"]}</div>'
    else:
        fb = f'<div class="ch-feedback ch-fb-err">❌ 正确答案是 {q["answer"]}。{q["explanation"]}</div>'

    current += 1
    new_state = {"questions": questions, "current": current, "score": score}
    state_json = json.dumps(new_state, ensure_ascii=False)
    state_escaped = html.escape(state_json, quote=True)

    if current >= len(questions):
        db.save_challenge_progress("默认", current, score, len(questions))
        result = _render_challenge_result(score, len(questions))
        return HTMLResponse(fb + result)

    return HTMLResponse(fb + _render_q(current, questions, score, state_escaped))


def _render_q(current: int, questions: list, score: int, state_json: str) -> str:
    total = len(questions)
    if current >= total:
        return _render_challenge_result(score, total)

    q = questions[current]
    bar_w = int(current / total * 100)
    opts_html = ""
    for k, v in q["options"].items():
        opts_html += f'''<div class="ch-opt" hx-post="/api/challenge/answer"
    hx-include="[name='ch_state']"
    hx-vals='{{"choice":"{k}"}}'
    hx-target="#challenge-area"
    hx-swap="innerHTML">
    <span class="ch-opt-key">{k}</span><span>{v}</span></div>'''

    return f'''<div class="ch-question-card">
  <div class="ch-q-header">
    <span class="ch-q-num">第 {current + 1} 题 · 共 {total} 题</span>
    <span style="font-size:12px;color:rgba(0,0,0,.35)">本组得分 {score}</span>
  </div>
  <div class="progress-bar"><div class="progress-fill" style="width:{bar_w}%"></div></div>
  <div class="ch-q-body">{q["question"]}</div>
  <div class="ch-options">{opts_html}</div>
  <input type="hidden" name="ch_state" value="{state_json}">
</div>'''


def _render_challenge_result(score: int, total: int) -> str:
    pct = int(score / total * 100)
    icon = "🎉" if pct >= 80 else "💪"
    grade = "全部答对！太棒了！" if score == total else "挑战完成！"
    return f'''<div class="ch-question-card" style="text-align:center;padding:48px 32px">
  <div style="font-size:52px;margin-bottom:16px">{icon}</div>
  <div style="font-size:18px;font-weight:600;color:rgba(0,0,0,.88);margin-bottom:4px">{grade}</div>
  <div style="font-size:13px;color:rgba(0,0,0,.45);margin-bottom:16px">本组 {total} 题，答对 {score} 题</div>
  <div style="font-size:48px;font-weight:800;color:#1677ff;line-height:1.2">{score}
    <span style="font-size:20px;font-weight:400;color:rgba(0,0,0,.35)">/{total}</span>
  </div>
  <div style="font-size:13px;color:rgba(0,0,0,.45);margin-top:8px">正确率 {pct}%</div>
  <div style="margin-top:24px">
    <button class="ant-btn ant-btn-primary ant-btn-lg"
      hx-post="/api/challenge/start" hx-target="#challenge-area" hx-swap="innerHTML">
      下一组题目 →
    </button>
  </div>
</div>'''


# ══════════════════════════════════════════════
# 进度
# ══════════════════════════════════════════════

@router.get("/progress/data", response_class=HTMLResponse)
async def progress_data():
    s = db.get_user_stats()
    qb = db.get_qbank_stats()

    rec = "".join(
        f'<span class="ant-tag ant-tag-blue" style="margin:3px">{r["word"]}</span>'
        for r in s["recent"]
    ) or '<span style="color:rgba(0,0,0,.35);font-size:13px">还没有学习记录，快去查词吧～</span>'

    stats = [
        (s["total_learned"], "已学词汇"),
        (f"{s['like_rate']}%", "好评率"),
        (s.get("ai_count", 0), "AI 词条"),
        (s.get("pending_count", 0), "待审核"),
    ]
    stats_html = "".join(
        f'<div class="stats-item"><div class="stat-num">{v}</div><div class="stat-label">{l}</div></div>'
        for v, l in stats
    )

    return _render("partials/progress/stats.html", {
        "stats_html": stats_html,
        "recent_html": rec,
        "qb_total": qb["total"],
        "qb_active": qb["active"],
        "qb_inactive": qb["inactive"],
    })


# ══════════════════════════════════════════════
# 词库管理
# ══════════════════════════════════════════════

_SL = {"approved": "✅ 已审核", "pending": "⏳ 待审核", "rejected": "❌ 已拒绝"}
_AL = {0: "内置", 1: "🤖 AI"}


@router.get("/admin/table", response_class=HTMLResponse)
async def admin_table(search: str = "", status_filter: str = "全部"):
    rows = db.get_all_words_admin(search, status_filter)
    data = [[r[0], _SL.get(r[1], r[1]), f"{r[2]:.1f}", _AL.get(r[3], r[3]), r[4]] for r in rows]
    return _render("partials/admin/table.html", {"rows": data})


@router.get("/admin/edit-form", response_class=HTMLResponse)
async def admin_edit_form(word: str = ""):
    """返回预填好的编辑表单 HTML（替换整个表单区域）"""
    data = db.get_word_for_edit(word.strip()) if word.strip() else None
    if not data:
        return _render("partials/admin/edit_form.html", {"word": "", "meaning": "", "tips": "", "scenarios": "[]", "status": "approved"})

    return _render("partials/admin/edit_form.html", {
        "word": data["word"],
        "meaning": data.get("meaning", ""),
        "tips": data.get("use_tips", ""),
        "scenarios": json.dumps(data.get("scenarios", []), ensure_ascii=False, indent=2),
        "status": data.get("status", "approved"),
    })


@router.post("/admin/save", response_class=HTMLResponse)
async def admin_save(
    word: str = Form(""),
    meaning: str = Form(""),
    use_tips: str = Form(""),
    scenarios_json: str = Form(""),
    status: str = Form("approved"),
):
    if not word:
        return HTMLResponse('<div class="alert-err">请先在表格中选择词条</div>')
    ok, msg = db.update_word_admin(word, meaning, use_tips, scenarios_json, status)
    cls = "alert-ok" if ok else "alert-err"
    return HTMLResponse(f'<div class="{cls}">{msg}</div>')


# ══════════════════════════════════════════════
# 题库管理
# ══════════════════════════════════════════════

@router.get("/qbank/table", response_class=HTMLResponse)
async def qbank_table(search: str = "", filter_mode: str = "全部"):
    rows = db.get_qbank_words(search, filter_mode)
    return _render("partials/qbank/table.html", {"rows": rows})


@router.get("/qbank/stats", response_class=HTMLResponse)
async def qbank_stats():
    s = db.get_qbank_stats()
    return _render("partials/qbank/stats.html", {
        "total": s["total"],
        "active": s["active"],
        "inactive": s["inactive"],
    })


@router.post("/qbank/select", response_class=HTMLResponse)
async def qbank_select(word: str = Form("")):
    """选中词条：OOB 更新隐藏的 #qb-word"""
    w = word.strip()
    return HTMLResponse(_oob("qb-word", f'<input type="hidden" id="qb-word" name="word" value="{w}">'))


@router.post("/qbank/add", response_class=HTMLResponse)
async def qbank_add(word: str = Form("")):
    if not word.strip():
        return HTMLResponse('<div class="alert-err">请先在表格中点击选择词条</div>')
    db.toggle_challenge_word(word.strip(), True)
    return HTMLResponse(f'<div class="alert-ok">✅ 「{word.strip()}」已加入题库</div>')


@router.post("/qbank/remove", response_class=HTMLResponse)
async def qbank_remove(word: str = Form("")):
    if not word.strip():
        return HTMLResponse('<div class="alert-err">请先在表格中点击选择词条</div>')
    db.toggle_challenge_word(word.strip(), False)
    return HTMLResponse(f'<div class="alert-ok">✅ 「{word.strip()}」已移出题库</div>')


# ══════════════════════════════════════════════
# 设置
# ══════════════════════════════════════════════

@router.post("/settings/save", response_class=HTMLResponse)
async def settings_save(
    api_key: str = Form(""),
    base_url: str = Form(""),
    main_model: str = Form("deepseek-chat"),
    reflect_model: str = Form("deepseek-reasoner"),
    threshold: float = Form(7.0),
):
    data = {
        "DEEPSEEK_API_KEY": api_key.strip(),
        "DEEPSEEK_BASE_URL": base_url.strip() or "https://api.deepseek.com/v1",
        "MAIN_MODEL": main_model,
        "REFLECT_MODEL": reflect_model,
        "QUALITY_THRESHOLD": float(threshold),
    }
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    import config as cfg; importlib.reload(cfg)
    import agent.graph as g; g._graph = None

    if api_key.strip():
        return HTMLResponse('<div class="alert-ok">✅ 已保存，AI 模式已激活！下次查词将调用 DeepSeek</div>')
    return HTMLResponse('<div class="alert-ok">💡 已保存（未填 Key，使用本地词库模式）</div>')


# ══════════════════════════════════════════════
# 聊天渲染（从 agent/tools.py 迁移至此）
# ══════════════════════════════════════════════

def _render_scenarios(word_data: dict) -> str:
    word = word_data.get("word", "")
    scenarios = word_data.get("scenarios", [])
    if not scenarios:
        return '<div class="placeholder"><div class="placeholder-icon">💬</div><div class="placeholder-title">暂无场景示例</div></div>'

    html = f'<div style="font-size:22px;font-weight:700;color:rgba(0,0,0,.88);margin-bottom:4px">{word}</div>'
    html += f'<div style="font-size:12px;color:rgba(0,0,0,.45);margin-bottom:14px">共 {len(scenarios)} 个使用场景</div>'

    for s in scenarios:
        lines = ""
        for d in s.get("dialogue", []):
            cls = "self-msg" if d["speaker"] == "我" else "other-msg"
            lines += (f'<div class="msg {cls}">'
                      f'<span class="speaker">{d["speaker"]}：</span>{d["text"]}</div>')
        html += f'''<div class="scenario-card">
  <div class="scene-header">{s.get("emoji", "💬")} {s.get("title", "")} <span style="color:rgba(0,0,0,.35);font-weight:400;font-size:12px">场景 {s.get("id", "")}</span></div>
  <div class="scene-context">📍 {s.get("context", "")}</div>
  <div class="dialogue-box">{lines}</div>
</div>'''
    return html


def _render_details(word_data: dict) -> str:
    meaning = word_data["meaning"]
    sent_key = word_data.get("sentiment", "neutral")
    sentiment = _SENT_LABEL.get(sent_key, "中性 😐")
    sent_cls = _SENT_TAG.get(sent_key, "ant-tag-blue")
    quality = word_data.get("quality_score", 5.0)
    is_ai = word_data.get("is_ai_generated", 0)
    use_tips = word_data.get("use_tips", "")
    related = word_data.get("related", [])
    origin_year = word_data.get("origin_year", "")
    origin_platform = word_data.get("origin_platform", "")

    ai_tag = ""
    if is_ai:
        if word_data.get("status") == "pending":
            ai_tag = '<span class="ant-tag ant-tag-gold">⏳ AI · 待审核</span>'
        else:
            ai_tag = '<span class="ant-tag ant-tag-cyan">✅ AI · 已审核</span>'

    q_color = "#52c41a" if quality >= 8 else "#faad14" if quality >= 6 else "#ff4d4f"

    html = f'''<div class="anno-block">
  <div class="anno-hd">📖 词义详解</div>
  <div style="color:rgba(0,0,0,.65);font-size:14px;line-height:1.85">{meaning}</div>
  <div class="meta-row">
    <span class="ant-tag {sent_cls}">{sentiment}</span>
    <span class="ant-tag" style="color:{q_color};border-color:{q_color}20;background:{q_color}10">质量 {quality:.1f}</span>
    {ai_tag}
  </div>
</div>'''

    if origin_year or origin_platform:
        plat = f'<span class="ant-tag ant-tag-blue">📍 {origin_platform}</span>' if origin_platform else ""
        html += f'''<div class="anno-block">
  <div class="anno-hd">📅 网络出现时间</div>
  <div style="display:flex;align-items:center;gap:10px">
    <span class="origin-year">{origin_year}</span>
    {plat}
  </div>
</div>'''

    if use_tips:
        html += f'''<div class="anno-block">
  <div class="anno-hd">💡 使用贴士</div>
  <div class="tips-box">{use_tips}</div>
</div>'''

    if related:
        tags = "".join(
            f'<span class="tag-btn" style="cursor:pointer"'
            f' hx-post="/api/chat/lookup"'
            f' hx-vals=\'{{"user_input":"{w}","last_word":""}}\''
            f' hx-target="#word-result"'
            f' hx-swap="innerHTML"'
            f' hx-indicator="#loading-overlay">{w}</span>'
            for w in related
        )
        html += f'''<div class="anno-block">
  <div class="anno-hd">🔗 相关词汇</div>
  <div style="line-height:2.2;margin-top:2px">{tags}</div>
</div>'''

    return html


def _render_ai_text(word: str, text: str) -> str:
    return f'''<div class="anno-block">
  <div class="anno-hd">🤖 AI 解析</div>
  <div style="white-space:pre-wrap;color:#374151;font-size:14px;line-height:1.85">{text}</div>
</div>'''


def _render_not_found_left(word: str) -> str:
    return f'''<div class="placeholder" style="padding:48px 16px">
  <div class="placeholder-icon">🔍</div>
  <div class="placeholder-title">「{word}」暂未收录</div>
  <div class="placeholder-desc">配置 DeepSeek API Key 后可 AI 实时生成</div>
</div>'''


def _render_not_found_right() -> str:
    return '''<div class="anno-block">
  <div class="anno-hd">🤔 暂未收录</div>
  <div style="color:rgba(0,0,0,.45);font-size:13px;line-height:1.9">
    词库中暂无该词条。<br>配置 DeepSeek API Key 后可实时生成。
  </div>
</div>'''


def _right_placeholder() -> str:
    return '''<div class="placeholder" style="padding:60px 16px">
  <div class="placeholder-icon">📋</div>
  <div class="placeholder-title">词义 · 贴士 · 相关词</div>
  <div class="placeholder-desc" style="text-align:left;max-width:220px;margin:0 auto;color:rgba(0,0,0,.35)">
    查询后这里将展示：<br>
    📖 &nbsp;词义详解<br>
    📅 &nbsp;网络出现时间<br>
    💡 &nbsp;使用贴士<br>
    🔗 &nbsp;相关词汇
  </div>
</div>'''
