"""
工具函数层：词库查找、AI 调用、Mock 生成、闯关题目构建
"""
from __future__ import annotations
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import database as db


# ── 词条检索 ──────────────────────────────────────────────

def retrieve_word(word: str) -> dict | None:
    return db.search_word(word)


def get_recommendations(related_list: list, exclude: str = "") -> list:
    filtered = [w for w in related_list if w != exclude][:4]
    return db.get_related_words(filtered)

def mock_generate(word: str) -> dict | None:
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
