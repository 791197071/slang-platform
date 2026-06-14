import sqlite3
import json
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent
_JSON_PATH = _BASE_DIR / "data" / "slang_dict.json"


def _get_db_path():
    from config import DB_PATH
    return str(_BASE_DIR / DB_PATH)


def _conn():
    c = sqlite3.connect(_get_db_path())
    c.row_factory = sqlite3.Row
    return c


def init_db():
    conn = _conn()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY,
            word TEXT UNIQUE NOT NULL,
            meaning TEXT,
            tags TEXT,
            sentiment TEXT,
            scenarios TEXT,
            related TEXT,
            use_tips TEXT,
            use_count INTEGER DEFAULT 0,
            quality_score REAL DEFAULT 5.0,
            status TEXT DEFAULT 'approved',
            is_ai_generated INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL,
            learned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            feedback INTEGER DEFAULT 0,
            times_reviewed INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS challenge_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme TEXT UNIQUE NOT NULL,
            current_group INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            total_questions INTEGER DEFAULT 0
        );
    """)

    # Safe migration: add columns if not yet exist
    for col_sql in [
        "ALTER TABLE words ADD COLUMN quality_score REAL DEFAULT 5.0",
        "ALTER TABLE words ADD COLUMN status TEXT DEFAULT 'approved'",
        "ALTER TABLE words ADD COLUMN is_ai_generated INTEGER DEFAULT 0",
        "ALTER TABLE words ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]:
        try:
            cur.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    cur.execute("SELECT COUNT(*) FROM words")
    if cur.fetchone()[0] == 0 and _JSON_PATH.exists():
        with open(_JSON_PATH, encoding="utf-8") as f:
            entries = json.load(f)
        for e in entries:
            cur.execute(
                "INSERT OR IGNORE INTO words "
                "(word, meaning, tags, sentiment, scenarios, related, use_tips, quality_score, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 7.0, 'approved')",
                (
                    e["word"], e["meaning"],
                    json.dumps(e.get("tags", []), ensure_ascii=False),
                    e.get("sentiment", "neutral"),
                    json.dumps(e.get("scenarios", []), ensure_ascii=False),
                    json.dumps(e.get("related", []), ensure_ascii=False),
                    e.get("use_tips", ""),
                ),
            )
    conn.commit()
    conn.close()


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["scenarios"] = json.loads(d.get("scenarios") or "[]")
    d["related"] = json.loads(d.get("related") or "[]")
    return d


# ── 查询 ──────────────────────────────────────────────────

def search_word(word: str) -> dict | None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM words WHERE word = ? AND status != 'rejected'", (word.strip(),))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def fuzzy_search(word: str, limit: int = 5) -> list:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM words WHERE (word LIKE ? OR meaning LIKE ?) AND status != 'rejected' LIMIT ?",
        (f"%{word}%", f"%{word}%", limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_words_by_tag(tag: str, exclude: list = None, limit: int = 5) -> list:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM words WHERE tags LIKE ? AND status != 'rejected' "
        "ORDER BY quality_score DESC, RANDOM() LIMIT ?",
        (f"%{tag}%", limit * 3),
    )
    rows = cur.fetchall()
    conn.close()
    words = [_row_to_dict(r) for r in rows]
    if exclude:
        words = [w for w in words if w["word"] not in exclude]
    return words[:limit]


def get_related_words(word_list: list) -> list:
    if not word_list:
        return []
    conn = _conn()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(word_list))
    cur.execute(
        f"SELECT * FROM words WHERE word IN ({placeholders}) AND status != 'rejected'",
        word_list,
    )
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_all_words(limit: int = 200) -> list:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM words WHERE status != 'rejected' LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


# ── AI 生成内容入库 ────────────────────────────────────────

def save_generated_word(word_data: dict):
    """保存 DS 生成的词条，status='pending' 等待人工审核。"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO words
               (word, meaning, tags, sentiment, scenarios, related, use_tips, quality_score, status, is_ai_generated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 1)
           ON CONFLICT(word) DO UPDATE SET
               meaning         = excluded.meaning,
               scenarios       = excluded.scenarios,
               use_tips        = excluded.use_tips,
               is_ai_generated = 1,
               status          = CASE WHEN status = 'approved' THEN 'approved' ELSE 'pending' END
        """,
        (
            word_data["word"],
            word_data.get("meaning", ""),
            json.dumps(word_data.get("tags", []), ensure_ascii=False),
            word_data.get("sentiment", "neutral"),
            json.dumps(word_data.get("scenarios", []), ensure_ascii=False),
            json.dumps(word_data.get("related", []), ensure_ascii=False),
            word_data.get("use_tips", ""),
            word_data.get("quality_score", 7.0),
        ),
    )
    conn.commit()
    conn.close()


# ── 管理面板 CRUD ─────────────────────────────────────────

def get_all_words_admin(search: str = "", status_filter: str = "全部") -> list:
    conn = _conn()
    cur = conn.cursor()
    conditions, params = [], []
    if search:
        conditions.append("(word LIKE ? OR meaning LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if status_filter == "已审核":
        conditions.append("status = 'approved'")
    elif status_filter == "待审核":
        conditions.append("status = 'pending'")
    elif status_filter == "AI生成":
        conditions.append("is_ai_generated = 1")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cur.execute(
        f"SELECT word, status, quality_score, is_ai_generated, use_count "
        f"FROM words {where} ORDER BY is_ai_generated DESC, status DESC, quality_score DESC",
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [list(r) for r in rows]


def get_word_for_edit(word: str) -> dict | None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM words WHERE word = ?", (word,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def update_word_admin(word: str, meaning: str, use_tips: str,
                      scenarios_json: str, status: str) -> tuple[bool, str]:
    try:
        scenarios = json.loads(scenarios_json)
    except json.JSONDecodeError:
        return False, "场景 JSON 格式有误，请检查后重试"
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE words SET meaning=?, use_tips=?, scenarios=?, status=? WHERE word=?",
        (meaning, use_tips, json.dumps(scenarios, ensure_ascii=False), status, word),
    )
    conn.commit()
    conn.close()
    return True, f"「{word}」已保存，状态：{status}"


# ── 质量分更新（反馈驱动学习） ────────────────────────────

def update_quality_score(word: str, delta: float):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE words SET quality_score = MIN(10.0, MAX(1.0, quality_score + ?)) WHERE word = ?",
        (delta, word),
    )
    conn.commit()
    conn.close()


# ── 用户记忆 ──────────────────────────────────────────────

def mark_learned(word: str, feedback: int = 0):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_memory (word, feedback) VALUES (?, ?) "
        "ON CONFLICT(word) DO UPDATE SET times_reviewed = times_reviewed + 1, feedback = ?",
        (word, feedback, feedback),
    )
    cur.execute("UPDATE words SET use_count = use_count + 1 WHERE word = ?", (word,))
    conn.commit()
    conn.close()


def update_feedback(word: str, feedback: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE user_memory SET feedback = ? WHERE word = ?", (feedback, word))
    if cur.rowcount == 0:
        cur.execute("INSERT INTO user_memory (word, feedback) VALUES (?, ?)", (word, feedback))
    conn.commit()
    conn.close()
    update_quality_score(word, 0.5 if feedback == 1 else -0.3)


def get_learned_words() -> list:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT word FROM user_memory")
    words = [r[0] for r in cur.fetchall()]
    conn.close()
    return words


def get_user_stats() -> dict:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_memory")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM user_memory WHERE feedback = 1")
    liked = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM user_memory WHERE feedback = -1")
    disliked = cur.fetchone()[0]
    cur.execute(
        "SELECT word, learned_at, feedback FROM user_memory ORDER BY learned_at DESC LIMIT 10"
    )
    recent = [{"word": r[0], "date": r[1], "feedback": r[2]} for r in cur.fetchall()]
    cur.execute(
        "SELECT theme, current_group, total_correct, total_questions FROM challenge_progress"
    )
    challenges = [
        {"theme": r[0], "group": r[1], "correct": r[2], "total": r[3]}
        for r in cur.fetchall()
    ]
    cur.execute("SELECT COUNT(*) FROM words WHERE is_ai_generated = 1")
    ai_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM words WHERE status = 'pending'")
    pending_count = cur.fetchone()[0]
    conn.close()
    return {
        "total_learned": total,
        "liked": liked,
        "disliked": disliked,
        "like_rate": round(liked / max(total, 1) * 100),
        "recent": recent,
        "challenges": challenges,
        "ai_count": ai_count,
        "pending_count": pending_count,
    }


def save_challenge_progress(theme: str, group: int, correct: int, total: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO challenge_progress (theme, current_group, total_correct, total_questions) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(theme) DO UPDATE SET "
        "current_group = ?, total_correct = total_correct + ?, total_questions = total_questions + ?",
        (theme, group, correct, total, group, correct, total),
    )
    conn.commit()
    conn.close()


def get_challenge_progress(theme: str) -> dict:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT current_group, total_correct, total_questions "
        "FROM challenge_progress WHERE theme = ?",
        (theme,),
    )
    row = cur.fetchone()
    conn.close()
    return {"group": row[0], "correct": row[1], "total": row[2]} if row else {"group": 0, "correct": 0, "total": 0}
