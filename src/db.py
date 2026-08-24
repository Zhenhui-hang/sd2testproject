"""资产存储层（SQLite，按剧隔离）。

每个剧一个数据库：projects/<剧>/assets.db
资产表 assets：
  id          INTEGER 主键（自增，全局唯一引用）
  key         TEXT    资产唯一键，用于 @引用（如 小美-正装）
  category    TEXT    character / prop / scene
  name        TEXT    名称（小美）
  state       TEXT    状态/服装（正装），可空
  parent_id   INTEGER 主次关系：子资产挂到主资产 id 下（如 小美-正装.parent_id = 小美.id）
  level       TEXT    primary / secondary
  prompt      TEXT    生图提示词
  image_path  TEXT    图片相对路径，可空（未生图）
  created_at  TEXT    创建时间

提供：建表、批量插入（来自资产拆解结果）、按 id/key 查询、增删改、主次树查询。
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_db(project_dir: str | Path) -> Path:
    """返回该剧的 assets.db 路径，并确保父目录存在。"""
    p = Path(project_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / "assets.db"


def get_assets_dir(project_dir: str | Path) -> Path:
    """返回资产候选图片目录。"""
    return Path(project_dir) / "assets"


def init_db(db_path: str | Path) -> None:
    """建表并为旧项目执行幂等迁移。"""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                category TEXT NOT NULL,
                name TEXT,
                state TEXT,
                parent_id INTEGER,
                level TEXT DEFAULT 'primary',
                prompt TEXT,
                image_path TEXT,
                aliases TEXT DEFAULT '[]',
                episodes TEXT DEFAULT '[]',
                profile TEXT DEFAULT '{}',
                status TEXT DEFAULT 'placeholder',
                negative_prompt TEXT DEFAULT '',
                seedance_asset_id TEXT,
                seedance_asset_name TEXT,
                audio_path TEXT,
                audio_name TEXT,
                created_at TEXT,
                UNIQUE(key)
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
        migrations = {
            "aliases": "TEXT DEFAULT '[]'",
            "episodes": "TEXT DEFAULT '[]'",
            "profile": "TEXT DEFAULT '{}'",
            "status": "TEXT DEFAULT 'placeholder'",
            "negative_prompt": "TEXT DEFAULT ''",
            "seedance_asset_id": "TEXT",
            "seedance_asset_name": "TEXT",
            "audio_path": "TEXT",
            "audio_name": "TEXT",
            "image_url": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE assets ADD COLUMN {column} {definition}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                source TEXT DEFAULT 'generated',
                is_default INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fragment_assets (
                episode INTEGER NOT NULL,
                fragment_index INTEGER NOT NULL,
                asset_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                mapping_text TEXT DEFAULT '',
                created_at TEXT,
                PRIMARY KEY(episode, fragment_index, asset_id),
                FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
            )
            """
        )
        fragment_columns = {row[1] for row in conn.execute("PRAGMA table_info(fragment_assets)").fetchall()}
        if "mapping_text" not in fragment_columns:
            conn.execute("ALTER TABLE fragment_assets ADD COLUMN mapping_text TEXT DEFAULT ''")
        conn.execute("UPDATE assets SET status='ready' WHERE image_path IS NOT NULL AND (status IS NULL OR status='placeholder')")
        conn.execute("UPDATE assets SET status='prompt_ready' WHERE prompt != '' AND image_path IS NULL AND (status IS NULL OR status='placeholder')")
        conn.execute("UPDATE assets SET episodes='[]' WHERE category='character' AND (state IS NULL OR state='')")
        conn.commit()


def _json_list(value) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _row_to_dict(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    return {
        "id": row["id"],
        "key": row["key"],
        "category": row["category"],
        "name": row["name"],
        "state": row["state"],
        "parent_id": row["parent_id"],
        "level": row["level"],
        "prompt": row["prompt"],
        "image_path": row["image_path"],
        "image_url": row["image_url"] if "image_url" in keys else None,
        "aliases": _json_list(row["aliases"]) if "aliases" in keys else [],
        "episodes": _json_list(row["episodes"]) if "episodes" in keys else [],
        "profile": json.loads(row["profile"] or "{}") if "profile" in keys else {},
        "status": (row["status"] if "status" in keys else None) or ("ready" if row["image_path"] else "prompt_ready" if row["prompt"] else "placeholder"),
        "negative_prompt": (row["negative_prompt"] if "negative_prompt" in keys else "") or "",
        "seedance_asset_id": row["seedance_asset_id"] if "seedance_asset_id" in keys else None,
        "seedance_asset_name": row["seedance_asset_name"] if "seedance_asset_name" in keys else None,
        "audio_path": row["audio_path"] if "audio_path" in keys else None,
        "audio_name": row["audio_name"] if "audio_name" in keys else None,
        "created_at": row["created_at"],
    }


def normalize_character_look_name(character_name: str, look_name: str) -> str:
    """人物造型统一使用“人物名-造型名”，兼容已经带前缀的旧数据。"""
    character_name = str(character_name or "").strip()
    look_name = str(look_name or "").strip()
    if not character_name or not look_name or look_name == "主图":
        return look_name
    if look_name == character_name or look_name.startswith(f"{character_name}-"):
        return look_name
    return f"{character_name}-{look_name.lstrip('-')}"


def insert_assets(db_path: str | Path, assets: dict, image_mapping: dict | None = None) -> list[int]:
    """把资产拆解结果批量写入（来自 analyzer 的 assets.json 结构）。
    处理主次关系：同一 name 的多个 state 作为 secondary 挂到首个 primary 下。
    返回所有插入的 id 列表。
    """
    init_db(db_path)
    image_mapping = image_mapping or {}
    ids: list[int] = []
    primary_of_name: dict[tuple[str, str], int] = {}  # (category, name) -> 主资产 id

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        # 先加载已有主资产，确保重新拆解和历史数据也能正确挂接。
        for row in conn.execute(
            "SELECT id,category,name FROM assets WHERE state IS NULL OR state='' ORDER BY id"
        ).fetchall():
            primary_of_name[(row["category"], row["name"])] = row["id"]
        # 分类映射：assets.json 字段 -> 存储类别
        groups = [
            ("character", assets.get("characters", [])),
            ("prop", assets.get("props", [])),
            ("scene", assets.get("scenes", [])),
        ]
        for cat, raw_items in groups:
            # 基础资产必须先于妆造/子空间写入，父子关系不依赖模型返回顺序。
            items = sorted(raw_items, key=lambda item: bool(item.get("state")))
            for it in items:
                name = it.get("name", "")
                state = it.get("state", "")
                if cat == "character" and state:
                    state = normalize_character_look_name(name, state)
                key = re.sub(r"[^\w一-龥-]", "", state if state and state.startswith(f"{name}-") else f"{name}-{state}" if state else name)
                parent_key = (cat, name)
                is_child = bool(state)
                parent_id = primary_of_name.get(parent_key) if is_child else None
                level = "secondary" if is_child and parent_id else "primary"
                episodes = it.get("episodes", it.get("source_locations", []))
                if cat == "character" and not is_child:
                    episodes = []
                cur = conn.execute(
                    "SELECT id FROM assets WHERE key=?", (key,)
                ).fetchone()
                if cur:
                    ids.append(cur["id"])
                    existing = conn.execute("SELECT prompt,image_path,status FROM assets WHERE id=?", (cur["id"],)).fetchone()
                    incoming_prompt = it.get("prompt", it.get("image_prompt", ""))
                    if cat == "character":
                        incoming_prompt = ""
                    merged_status = "ready" if existing["image_path"] else "prompt_ready" if (existing["prompt"] or incoming_prompt) else "placeholder"
                    conn.execute(
                        "UPDATE assets SET name=?,state=?,category=?,parent_id=?,level=?,aliases=?,episodes=?,profile=?,status=?,prompt=CASE WHEN ?='character' THEN '' WHEN prompt IS NULL OR prompt='' THEN ? ELSE prompt END WHERE id=?",
                        (name, state or None, cat, parent_id, level,
                         json.dumps(it.get("aliases", []), ensure_ascii=False),
                         json.dumps(episodes, ensure_ascii=False),
                         json.dumps(it.get("profile", {}), ensure_ascii=False),
                         merged_status, cat, incoming_prompt, cur["id"]),
                    )
                    if not is_child:
                        primary_of_name[parent_key] = cur["id"]
                    continue
                prompt = it.get("prompt", it.get("image_prompt", ""))
                if cat == "character":
                    prompt = ""
                image_path = image_mapping.get(key)
                status = "ready" if image_path else "prompt_ready" if prompt else "placeholder"
                cur = conn.execute(
                    """INSERT INTO assets
                       (key,category,name,state,parent_id,level,prompt,image_path,aliases,episodes,profile,status,negative_prompt,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (key, cat, name, state or None, parent_id, level, prompt, image_path,
                     json.dumps(it.get("aliases", []), ensure_ascii=False),
                     json.dumps(episodes, ensure_ascii=False),
                     json.dumps(it.get("profile", {}), ensure_ascii=False),
                     status, it.get("negative_prompt", ""), _now()),
                )
                new_id = cur.lastrowid
                ids.append(new_id)
                if not is_child:
                    primary_of_name[parent_key] = new_id
        conn.commit()
    return ids


def get_all(db_path: str | Path) -> list[dict]:
    """返回全部资产（含主次的平铺列表）。"""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM assets ORDER BY category, parent_id IS NOT NULL, id"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_assets(db_path: str | Path) -> list[dict]:
    """get_all 的语义化别名。"""
    return get_all(db_path)


def repair_asset_hierarchy(db_path: str | Path) -> None:
    """修复旧资产父子关系，并补全人物造型的人物名前缀。"""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id,key,category,name,state FROM assets ORDER BY id").fetchall()
        for row in rows:
            if row["category"] != "character" or not row["state"]:
                continue
            state = normalize_character_look_name(row["name"], row["state"])
            key = re.sub(r"[^\w一-龥-]", "", state)
            if state != row["state"] or key != row["key"]:
                duplicate = conn.execute("SELECT id FROM assets WHERE key=? AND id<>?", (key, row["id"])).fetchone()
                conn.execute(
                    "UPDATE assets SET state=?,key=? WHERE id=?",
                    (state, key if not duplicate else row["key"], row["id"]),
                )
        rows = conn.execute("SELECT id,category,name,state FROM assets ORDER BY id").fetchall()
        primary = {
            (row["category"], row["name"]): row["id"]
            for row in rows if not row["state"]
        }
        for row in rows:
            if row["state"]:
                parent_id = primary.get((row["category"], row["name"]))
                conn.execute(
                    "UPDATE assets SET parent_id=?,level=? WHERE id=?",
                    (parent_id, "secondary" if parent_id else "primary", row["id"]),
                )
            else:
                conn.execute("UPDATE assets SET parent_id=NULL,level='primary' WHERE id=?", (row["id"],))
        conn.commit()


def get_asset(db_path: str | Path, asset_id: int) -> Optional[dict]:
    """读取单个资产。"""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_tree(db_path: str | Path) -> list[dict]:
    """返回带层级的资产树（主资产下挂子资产）。"""
    items = get_all(db_path)
    by_id = {i["id"]: {**i, "children": []} for i in items}
    roots = []
    for i in by_id.values():
        pid = i["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["children"].append(i)
        else:
            roots.append(i)
    return roots


def get_by_id(db_path: str | Path, asset_id: int) -> Optional[dict]:
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_asset(db_path: str | Path, asset_id: int, **fields) -> bool:
    """更新资产字段（name/state/prompt/image_path/parent_id 等）。"""
    init_db(db_path)
    allowed = {"key", "category", "name", "state", "parent_id", "level", "prompt", "image_path", "image_url", "aliases", "episodes", "profile", "status", "negative_prompt", "seedance_asset_id", "seedance_asset_name"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    current = get_asset(db_path, asset_id)
    category = sets.get("category", (current or {}).get("category"))
    state = sets.get("state", (current or {}).get("state"))
    if category == "character" and not state:
        sets["episodes"] = []
    for key in ("aliases", "episodes", "profile"):
        if key in sets and isinstance(sets[key], (list, dict)):
            sets[key] = json.dumps(sets[key], ensure_ascii=False)
    if not sets:
        return False
    sql = "UPDATE assets SET " + ", ".join(f"{k}=?" for k in sets) + " WHERE id=?"
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(sql, (*sets.values(), asset_id))
        conn.commit()
        return cur.rowcount > 0


def delete_asset(db_path: str | Path, asset_id: int) -> None:
    """删除资产、子资产及其候选图片记录。"""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        child_ids = [row[0] for row in conn.execute("SELECT id FROM assets WHERE parent_id=?", (asset_id,)).fetchall()]
        ids = [asset_id, *child_ids]
        conn.executemany("DELETE FROM asset_images WHERE asset_id=?", [(value,) for value in ids])
        conn.execute("DELETE FROM assets WHERE parent_id=?", (asset_id,))
        conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        conn.commit()


def add_asset(db_path: str | Path, fields: dict) -> int:
    """新增单个资产（前端 CRUD 用）。返回新插入 id。"""
    init_db(db_path)
    allowed = {"key", "category", "name", "state", "parent_id", "level", "prompt", "image_path", "image_url", "aliases", "episodes", "profile", "status", "negative_prompt", "seedance_asset_id", "seedance_asset_name"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not str(sets.get("key") or "").strip():
        raw_key = f"{sets.get('name', '')}-{sets.get('state', '')}".strip("-")
        sets["key"] = re.sub(r"[^\w一-龥-]", "", raw_key) or f"asset-{int(datetime.now().timestamp() * 1000)}"
    if sets.get("category", "prop") == "character" and not sets.get("state"):
        sets["episodes"] = []
    for key in ("aliases", "episodes", "profile"):
        if key in sets and isinstance(sets[key], (list, dict)):
            sets[key] = json.dumps(sets[key], ensure_ascii=False)
    sets.setdefault("category", "prop")
    sets.setdefault("level", "primary")
    sets.setdefault("created_at", _now())
    cols = list(sets.keys())
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(
            "INSERT INTO assets (" + ",".join(cols) + ") VALUES ("
            + ",".join("?" for _ in cols) + ")",
            tuple(sets.values()),
        )
        conn.commit()
        return cur.lastrowid


def add_asset_image(db_path: str | Path, asset_id: int, image_path: str, source: str = "generated", make_default: bool = False) -> int:
    """保存一张资产候选图片；首张图或显式指定时设为默认图。"""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        has_default = conn.execute("SELECT 1 FROM asset_images WHERE asset_id=? AND is_default=1", (asset_id,)).fetchone()
        is_default = 1 if make_default or not has_default else 0
        if is_default:
            conn.execute("UPDATE asset_images SET is_default=0 WHERE asset_id=?", (asset_id,))
        cur = conn.execute(
            "INSERT INTO asset_images(asset_id,image_path,source,is_default,created_at) VALUES(?,?,?,?,?)",
            (asset_id, image_path, source, is_default, _now()),
        )
        if is_default:
            conn.execute("UPDATE assets SET image_path=?,image_url=NULL,status='ready' WHERE id=?", (image_path, asset_id))
        conn.commit()
        return int(cur.lastrowid)


def get_asset_images(db_path: str | Path, asset_id: int) -> list[dict]:
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM asset_images WHERE asset_id=? ORDER BY is_default DESC,id DESC", (asset_id,)).fetchall()
    return [dict(row) for row in rows]


def set_default_asset_image(db_path: str | Path, asset_id: int, image_id: int) -> bool:
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT image_path FROM asset_images WHERE id=? AND asset_id=?", (image_id, asset_id)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE asset_images SET is_default=0 WHERE asset_id=?", (asset_id,))
        conn.execute("UPDATE asset_images SET is_default=1 WHERE id=?", (image_id,))
        conn.execute("UPDATE assets SET image_path=?,image_url=NULL,status='ready' WHERE id=?", (row[0], asset_id))
        conn.commit()
        return True


def delete_asset_image_record(db_path: str | Path, asset_id: int, image_id: int) -> Optional[str]:
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT image_path,is_default FROM asset_images WHERE id=? AND asset_id=?", (image_id, asset_id)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM asset_images WHERE id=?", (image_id,))
        if row[1]:
            fallback = conn.execute("SELECT id,image_path FROM asset_images WHERE asset_id=? ORDER BY id DESC LIMIT 1", (asset_id,)).fetchone()
            if fallback:
                conn.execute("UPDATE asset_images SET is_default=1 WHERE id=?", (fallback[0],))
                conn.execute("UPDATE assets SET image_path=?,status='ready' WHERE id=?", (fallback[1], asset_id))
            else:
                conn.execute("UPDATE assets SET image_path=NULL,status=CASE WHEN prompt!='' THEN 'prompt_ready' ELSE 'placeholder' END WHERE id=?", (asset_id,))
        conn.commit()
        return str(row[0])


def set_fragment_assets(db_path: str | Path, episode: int, fragment_index: int, bindings: list[dict]) -> None:
    """覆盖保存一个片段的资产绑定及其映射说明。"""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DELETE FROM fragment_assets WHERE episode=? AND fragment_index=?", (episode, fragment_index))
        conn.executemany(
            "INSERT INTO fragment_assets(episode,fragment_index,asset_id,role,mapping_text,created_at) VALUES(?,?,?,?,?,?)",
            [
                (
                    episode, fragment_index, int(item["asset_id"]), str(item.get("role") or "prop"),
                    str(item.get("mapping_text") or "").strip(), _now(),
                )
                for item in bindings
            ],
        )
        conn.commit()


def get_fragment_assets(db_path: str | Path, episode: int, fragment_index: int) -> list[dict]:
    """读取片段绑定的资产及默认图片、Seedance 注册信息。"""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT f.role,f.mapping_text,a.* FROM fragment_assets f
               JOIN assets a ON a.id=f.asset_id
               WHERE f.episode=? AND f.fragment_index=?
               ORDER BY CASE f.role WHEN 'scene' THEN 1 WHEN 'character' THEN 2 ELSE 3 END,a.id""",
            (episode, fragment_index),
        ).fetchall()
    result = []
    for row in rows:
        item = _row_to_dict(row)
        item["role"] = row["role"]
        item["mapping_text"] = row["mapping_text"] or ""
        result.append(item)
    return result


def assets_for_prompt(db_path: str | Path) -> str:
    """生成资产匹配步骤用的清单文本（id | key | 类别 | 名称 | 子项）。"""
    items = get_all(db_path)
    lines = ["id | key | 类别 | 名称 | 子项"]
    cat_cn = {"character": "人物", "prop": "道具", "scene": "场景"}
    for it in items:
        category = cat_cn.get(it["category"], it["category"])
        if it["category"] == "character" and (it.get("profile") or {}).get("asset_role") == "extra_character":
            category = "独立路人"
        lines.append(
            f"{it['id']} | {it['key']} | {category} | "
            f"{it['name'] or ''} | {it['state'] or ''}"
        )
    return "\n".join(lines)
