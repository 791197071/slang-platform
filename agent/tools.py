"""
工具函数层：词库查找、AI 调用、渲染、Mock 生成
"""
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import database as db

SENTIMENT_LABEL = {
    "positive": "正向 😊",
    "negative": "负向 😔",
    "neutral":  "中性 😐",
}

THEME_TAG_MAP = {
    "职场黑话": "职场",
    "恋爱俚语": "恋爱",
    "饭圈用语": "饭圈",
    "情绪表达": "情绪",
    "日常搞笑": "搞笑",
}


# ── 词条检索 ──────────────────────────────────────────────

def retrieve_word(word: str) -> dict | None:
    result = db.search_word(word)
    if result:
        return result
    candidates = db.fuzzy_search(word, limit=1)
    return candidates[0] if candidates else None


def get_recommendations(related_list: list, exclude: str = "") -> list:
    filtered = [w for w in related_list if w != exclude][:4]
    return db.get_related_words(filtered)


# ── HTML 渲染 ─────────────────────────────────────────────

def render_word_card(word_data: dict) -> str:
    word     = word_data["word"]
    meaning  = word_data["meaning"]
    sentiment = SENTIMENT_LABEL.get(word_data.get("sentiment", "neutral"), "中性 😐")
    use_tips  = word_data.get("use_tips", "")
    scenarios = word_data.get("scenarios", [])
    related   = word_data.get("related", [])
    is_ai     = word_data.get("is_ai_generated", 0)
    quality   = word_data.get("quality_score", 5.0)

    ai_badge = ""
    if is_ai:
        status = word_data.get("status", "pending")
        label  = "⏳ AI生成·待审核" if status == "pending" else "✅ AI生成·已审核"
        ai_badge = f'<span class="ai-source-badge">{label}</span>'

    scenario_html = ""
    for s in scenarios:
        lines = ""
        for d in s.get("dialogue", []):
            cls = "self-msg" if d["speaker"] == "我" else "other-msg"
            lines += (
                f'<div class="msg {cls}">'
                f'<span class="speaker">{d["speaker"]}：</span>{d["text"]}</div>'
            )
        scenario_html += f"""
<div class="scenario-card">
  <div class="scene-header">{s.get('emoji','🎬')} 场景{s.get('id','A')} · {s.get('title','')}</div>
  <div class="scene-context">📍 {s.get('context','')}</div>
  <div class="dialogue-box">{lines}</div>
</div>"""

    related_tags = "".join(
        f'<span class="tag-btn">{w}</span>' for w in related
    )

    tips_html = f'<div class="tips-box">💡 {use_tips}</div>' if use_tips else ""
    rel_html  = (
        f'<div class="related-section"><span class="related-label">相关词：</span>{related_tags}</div>'
        if related else ""
    )
    score_html = f'<div class="quality-score">质量分 {quality:.1f}/10</div>'

    return f"""
<div class="word-card">
  <div class="word-card-header">
    <div class="word-title">{word}</div>
    <div style="display:flex;gap:8px;align-items:center">{ai_badge}{score_html}</div>
  </div>
  <div class="sentiment-badge">{sentiment}</div>
  <div class="word-meaning">📖 {meaning}</div>
  {scenario_html}
  {tips_html}
  {rel_html}
</div>"""


def render_not_found(word: str) -> str:
    return f"""
<div class="display-placeholder">
  <div class="placeholder-icon">🔍</div>
  <div class="placeholder-title">「{word}」暂未收录</div>
  <div class="placeholder-desc">
    {'开启 AI 模式后可实时生成～填入 DeepSeek API Key 即可' if True else ''}
  </div>
  <div class="placeholder-examples">试试：破防了 · 内卷 · YYDS · 社死 · 塌房</div>
</div>"""


def render_ai_text(word: str, text: str) -> str:
    """将 DS 返回的 Markdown 文本包装成卡片（JSON 解析失败时的兜底）。"""
    return f"""
<div class="word-card">
  <div class="word-card-header">
    <div class="word-title">{word}</div>
    <span class="ai-source-badge">🤖 AI 生成</span>
  </div>
  <div class="word-meaning" style="white-space:pre-wrap;line-height:1.8">{text}</div>
</div>"""


def render_initial_display() -> str:
    return """
<div class="display-placeholder">
  <div class="placeholder-icon">👩‍🏫</div>
  <div class="placeholder-title">在左侧输入网络用语</div>
  <div class="placeholder-desc">词条解释和对话场景会展示在这里</div>
  <div class="placeholder-examples">试试：破防了 · 内卷 · YYDS · 社死 · 塌房 · 摆烂</div>
</div>"""


# ── Mock 生成（无 API Key） ───────────────────────────────

def mock_generate(word: str) -> dict | None:
    candidates = db.fuzzy_search(word, limit=3)
    if candidates:
        base = candidates[0].copy()
        base["word"] = word
        base["meaning"] = f"（Mock）「{word}」是一个网络用语，具体含义正在收录中。"
        base["is_ai_generated"] = 0
        return base
    return None


# ── 真实 AI 调用 ──────────────────────────────────────────

def ai_lookup_structured(word: str) -> dict | None:
    """调用 DS-V3，返回结构化 dict；JSON 解析失败则返回 None。"""
    from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MAIN_MODEL
    from agent.prompts import LOOKUP_PROMPT_JSON
    from openai import OpenAI

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    prompt = LOOKUP_PROMPT_JSON.format(word=word)
    resp = client.chat.completions.create(
        model=MAIN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        stream=False,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
        data["word"] = word
        data["is_ai_generated"] = 1
        return data
    except json.JSONDecodeError:
        return None


def ai_lookup(word: str) -> str:
    """调用 DS-V3，返回 Markdown 文本（结构化解析失败时的兜底）。"""
    from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MAIN_MODEL
    from agent.prompts import LOOKUP_PROMPT
    from openai import OpenAI

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    prompt = LOOKUP_PROMPT.format(word=word)
    resp = client.chat.completions.create(
        model=MAIN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        stream=False,
    )
    return resp.choices[0].message.content


def ai_reflect(content: str) -> float:
    """调用 DS-R1 对内容评分，返回 1-10。"""
    from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, REFLECT_MODEL
    from agent.prompts import REFLECT_PROMPT
    from openai import OpenAI

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    prompt = REFLECT_PROMPT.format(content=content)
    resp = client.chat.completions.create(
        model=REFLECT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        stream=False,
    )
    try:
        return float(resp.choices[0].message.content.strip())
    except ValueError:
        return 8.0


# ── 闯关题目构建 ──────────────────────────────────────────

def build_challenge_question(word_data: dict, all_theme_words: list) -> dict:
    word = word_data["word"]
    scenarios = word_data.get("scenarios", [])
    if not scenarios:
        scene_text = f"[使用「{word}」的场景]"
    else:
        scene = scenarios[0]
        lines = "\n".join(
            f"{d['speaker']}：{d['text']}" for d in scene.get("dialogue", [])
        )
        scene_text = f"📍 {scene.get('context','')}\n{lines}"

    distractors = [w["word"] for w in all_theme_words if w["word"] != word]
    random.shuffle(distractors)
    distractors = distractors[:3]
    while len(distractors) < 3:
        distractors.append("躺平" if word != "躺平" else "内卷")

    options = [word] + distractors
    random.shuffle(options)
    answer_idx = options.index(word)
    labels = ["A", "B", "C", "D"]

    return {
        "question": f"以下对话中，横线处最合适填入哪个网络用语？\n\n{scene_text.replace(word, '___')}",
        "options": {labels[i]: options[i] for i in range(4)},
        "answer": labels[answer_idx],
        "word": word,
        "explanation": f"「{word}」——{word_data['meaning'][:40]}...",
    }
