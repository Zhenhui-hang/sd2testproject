"""FastAPI 后端：剧管理 / 剧本上传 / 提示词设置 / 资产 CRUD / 步骤触发。

存储：projects/<剧名>/ 下保存 script.txt、assets.db、assets/ 图片、shots.json、
seedance_prompts.json。全局提示词模板在 prompts.yaml。

说明：步骤触发（analyze/image/split/compose）为真实 API 调用，会产生费用。
"""
from __future__ import annotations

import base64
import datetime
import json
import logging
import mimetypes
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from src import db as asset_db, doc_parser
from src import analyzer, image_gen, splitter, prompt_composer
from src.ark_client import ArkClient
from web.index import INDEX_HTML

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seedance")

app = FastAPI(title="Seedance 剧本生产工具")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")

PROJECTS_DIR = ROOT / "projects"
SETTINGS_PATH = ROOT / "config.yaml"
PROMPTS_PATH = ROOT / "prompts.yaml"


# ---------------- 工具 ----------------
def load_cfg() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    return yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8")) or {}


def project_dir(name: str) -> Path:
    p = PROJECTS_DIR / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ark_client() -> ArkClient:
    # ArkClient 自身会按 config.yaml + 环境变量 ARK_API_KEY 初始化
    return ArkClient()


def _cfg() -> dict:
    cfg = load_cfg()
    cfg.setdefault("ark", {})
    cfg.setdefault("run", {})
    return cfg


# ---------------- 提示词设置 ----------------
class PromptsModel(BaseModel):
    asset_analysis: str = ""
    shot_split: str = ""
    seedance_prompt: str = ""
    asset_match: str = ""
    smart_asset_match: str = ""
    extra_1: str = ""


@app.get("/api/settings")
def get_settings():
    if not PROMPTS_PATH.exists():
        return {}
    data = yaml.safe_load(PROMPTS_PATH.read_text(encoding="utf-8")) or {}
    return {k: (v or "") for k, v in data.items()}


@app.post("/api/settings")
def save_settings(p: PromptsModel):
    prompts = {k: getattr(p, k) for k in p.__fields__}
    PROMPTS_PATH.write_text(
        yaml.safe_dump(prompts, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return {"ok": True}


# ---------------- 剧管理 ----------------
@app.get("/api/projects")
def list_projects():
    if not PROJECTS_DIR.exists():
        return []
    result = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        import datetime
        created = datetime.datetime.fromtimestamp(d.stat().st_ctime).strftime("%Y-%m-%d %H:%M")
        result.append({
            "name": d.name,
            "has_script": (d / "script.txt").exists(),
            "created": created,
        })
    return result


class ProjectModel(BaseModel):
    name: str


@app.post("/api/projects")
def create_project(p: ProjectModel):
    name = p.name.strip()
    if not name:
        raise HTTPException(400, "剧名不能为空")
    d = project_dir(name)
    asset_db.init_db(asset_db.get_db(d))
    return {"name": name}


@app.delete("/api/projects/{name}")
def delete_project(name: str):
    d = PROJECTS_DIR / name
    if d.exists():
        import shutil
        shutil.rmtree(d)
    return {"ok": True}


def _project_basic_settings(project: Path) -> dict:
    settings = BasicSettingsModel().dict()
    path = project / "basic_settings.json"
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                settings.update({key: value for key, value in saved.items() if key in settings})
        except (OSError, json.JSONDecodeError):
            pass
    return settings


def _visual_style_path(project: Path) -> Path:
    return project / "visual_style.json"


def _load_visual_style(project: Path) -> dict:
    path = _visual_style_path(project)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _require_visual_style(project: Path) -> dict:
    style = _load_visual_style(project)
    if not style.get("unified_prompt"):
        raise HTTPException(400, "项目统一视觉风格尚未生成，请保存基本设定或手动重新分析")
    return style


def _analyze_and_save_visual_style(project: Path, settings: dict) -> dict:
    raw = _ark_client().chat(
        analyzer.build_visual_style_analysis_prompt(settings),
        system="你是影视项目视觉总监，只输出严格 JSON。",
        temperature=0.1,
    )
    style = analyzer.parse_visual_style_analysis(raw)
    style["source_settings"] = settings
    _visual_style_path(project).write_text(
        json.dumps(style, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return style


# ---------------- 剧本上传 ----------------
@app.post("/api/projects/{name}/script")
async def upload_script(name: str, file: UploadFile = File(...)):
    import tempfile
    d = project_dir(name)
    data = await file.read()
    fname = file.filename or "script.txt"
    # 写入临时文件，用 doc_parser 按扩展名解析为纯文本
    suffix = Path(fname).suffix.lower() or ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        text = doc_parser.parse_script(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    (d / "script.txt").write_text(text, encoding="utf-8")
    return {"ok": True, "chars": len(text)}


@app.get("/api/projects/{name}/script")
def get_script(name: str):
    """读取剧本：返回剧名、创建时间、字符数、按集拆分后的内容。"""
    import datetime
    import json
    d = project_dir(name)
    sp = d / "script.txt"
    if not sp.exists():
        raise HTTPException(404, "尚未上传剧本")
    text = sp.read_text(encoding="utf-8")
    title = doc_parser.extract_title(text)
    episodes = doc_parser.split_episodes(text)
    created = datetime.datetime.fromtimestamp(d.stat().st_ctime).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "title": title,
        "created": created,
        "chars": len(text),
        "episodes": episodes,
    }


@app.post("/api/projects/{name}/script/reparse")
def reparse_script(name: str):
    """重新解析剧本并返回分集结果（不修改原文件）。"""
    d = project_dir(name)
    sp = d / "script.txt"
    if not sp.exists():
        raise HTTPException(404, "尚未上传剧本")
    text = sp.read_text(encoding="utf-8")
    title = doc_parser.extract_title(text)
    episodes = doc_parser.split_episodes(text)
    return {
        "title": title,
        "episodes": episodes,
        "chars": len(text),
    }


class EpisodeIn(BaseModel):
    index: int
    title: str = ""
    content: str = ""


@app.post("/api/projects/{name}/script/episodes")
def save_episodes(name: str, episodes: list[EpisodeIn] = Body(...)):
    """将编辑后的各集内容序列化回 script.txt。"""
    d = project_dir(name)
    sp = d / "script.txt"
    if not sp.exists():
        raise HTTPException(404, "尚未上传剧本")
    parts = []
    for ep in episodes:
        title = ep.title or (f"第{ep.index}集" if ep.index > 0 else "前言")
        parts.append(f"{title}\n{ep.content or ''}")
    text = "\n\n".join(parts).strip() + "\n"
    sp.write_text(text, encoding="utf-8")
    return {"ok": True, "chars": len(text), "episodes": len(episodes)}


# ---------------- 资产 CRUD ----------------
@app.get("/api/projects/{name}/assets")
def list_assets(name: str):
    d = project_dir(name)
    db_path = asset_db.get_db(d)
    asset_db.repair_asset_hierarchy(db_path)
    rows = asset_db.get_all(db_path)
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        # 兼容前端 image_prompt 字段名，并显式返回父资产信息。
        r["image_prompt"] = r.get("prompt", "")
        parent = by_id.get(r.get("parent_id"))
        r["parent_name"] = parent.get("name") if parent else None
        r["image_count"] = len(asset_db.get_asset_images(db_path, r["id"]))
        if r.get("image_path"):
            r["image_url"] = f"/api/projects/{name}/assets/{r['id']}/image?v={r['image_count']}"
    return rows


class AssetModel(BaseModel):
    category: str = ""
    name: str = ""
    state: str = ""
    key: str = ""
    prompt: str = ""
    image_prompt: str = ""
    negative_prompt: str = ""
    aliases: list[str] = []
    episodes: list = []
    status: str = ""
    seedance_asset_id: str | None = None
    seedance_asset_name: str | None = None
    level: str = ""
    parent_id: int | None = None
    profile: dict = {}


class AssetPromptBatchModel(BaseModel):
    asset_ids: list[int]


class AssetImageGenerateModel(BaseModel):
    size: str = "1024x1024"
    make_default: bool = False


class AssetRegisterModel(BaseModel):
    seedance_asset_id: str
    seedance_asset_name: str = ""


class FragmentAssetItemModel(BaseModel):
    asset_id: int
    role: str = "prop"
    mapping_text: str = ""


class FragmentAssetBindingModel(BaseModel):
    asset_ids: list[int] = []
    assets: list[FragmentAssetItemModel] = []


class FragmentAssetMatchModel(BaseModel):
    shot_prompt: str


@app.post("/api/projects/{name}/assets")
def add_asset(name: str, a: AssetModel):
    d = project_dir(name)
    category = a.category or "prop"
    state = a.state
    if category == "character" and state and (a.profile or {}).get("asset_role") != "extra_character":
        state = asset_db.normalize_character_look_name(a.name, state)
    asset_key = a.key or (state if category == "character" and state else a.name)
    aid = asset_db.add_asset(
        asset_db.get_db(d),
        fields={
            "category": category,
            "name": a.name, "state": state, "key": asset_key,
            "prompt": a.prompt or a.image_prompt, "negative_prompt": a.negative_prompt,
            "aliases": a.aliases, "episodes": a.episodes,
            "status": a.status or ("prompt_ready" if (a.prompt or a.image_prompt) else "placeholder"),
            "seedance_asset_id": a.seedance_asset_id, "seedance_asset_name": a.seedance_asset_name,
            "level": a.level or "primary", "parent_id": a.parent_id, "profile": a.profile,
        },
    )
    return asset_db.get_asset(asset_db.get_db(d), aid)


@app.put("/api/projects/{name}/assets/{aid}")
def update_asset(name: str, aid: int, a: AssetModel):
    d = project_dir(name)
    state = a.state
    if a.category == "character" and state and (a.profile or {}).get("asset_role") != "extra_character":
        state = asset_db.normalize_character_look_name(a.name, state)
    key = state if a.category == "character" and state else a.key
    asset_db.update_asset(
        asset_db.get_db(d), aid,
        category=a.category, name=a.name, state=state, key=key,
        prompt=a.prompt or a.image_prompt, negative_prompt=a.negative_prompt,
        aliases=a.aliases, episodes=a.episodes, status=a.status,
        seedance_asset_id=a.seedance_asset_id, seedance_asset_name=a.seedance_asset_name,
        level=a.level, parent_id=a.parent_id, profile=a.profile,
    )
    return {"ok": True}


@app.delete("/api/projects/{name}/assets/{aid}")
def delete_asset(name: str, aid: int):
    d = project_dir(name)
    asset_db.delete_asset(asset_db.get_db(d), aid)
    return {"ok": True}


AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
AUDIO_MAX_BYTES = 20 * 1024 * 1024


@app.post("/api/projects/{name}/assets/{aid}/audio")
async def upload_character_audio(name: str, aid: int, file: UploadFile = File(...)):
    d = project_dir(name)
    db_path = asset_db.get_db(d)
    asset_db.init_db(db_path)
    asset = asset_db.get_asset(db_path, aid)
    if not asset:
        raise HTTPException(404, "资产不存在")
    if asset.get("category") != "character" or asset.get("parent_id"):
        raise HTTPException(400, "参考音只能上传到主人物")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise HTTPException(400, "仅支持 MP3、WAV、M4A、AAC、OGG、FLAC 音频")
    content = await file.read()
    if not content:
        raise HTTPException(400, "音频文件为空")
    if len(content) > AUDIO_MAX_BYTES:
        raise HTTPException(400, "音频文件不能超过 20MB")
    audio_dir = d / "assets" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    target = audio_dir / f"character_{aid}{suffix}"
    old_path = Path(asset["audio_path"]) if asset.get("audio_path") else None
    target.write_bytes(content)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE assets SET audio_path=?, audio_name=? WHERE id=?",
            (str(target), file.filename or target.name, aid),
        )
        conn.commit()
    if old_path and old_path != target:
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "asset": asset_db.get_asset(db_path, aid)}


@app.get("/api/projects/{name}/assets/{aid}/audio")
def get_character_audio(name: str, aid: int):
    db_path = asset_db.get_db(project_dir(name))
    asset_db.init_db(db_path)
    asset = asset_db.get_asset(db_path, aid)
    if not asset or not asset.get("audio_path"):
        raise HTTPException(404, "人物尚未上传参考音")
    path = Path(asset["audio_path"])
    if not path.exists():
        raise HTTPException(404, "参考音文件不存在")
    return FileResponse(path, filename=asset.get("audio_name") or path.name)


@app.delete("/api/projects/{name}/assets/{aid}/audio")
def delete_character_audio(name: str, aid: int):
    db_path = asset_db.get_db(project_dir(name))
    asset_db.init_db(db_path)
    asset = asset_db.get_asset(db_path, aid)
    if not asset:
        raise HTTPException(404, "资产不存在")
    path = Path(asset["audio_path"]) if asset.get("audio_path") else None
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("UPDATE assets SET audio_path=NULL, audio_name=NULL WHERE id=?", (aid,))
        conn.commit()
    if path:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True}


@app.delete("/api/projects/{name}/assets/{aid}/image")
def delete_asset_image(name: str, aid: int):
    d = project_dir(name)
    images = asset_db.get_asset_images(asset_db.get_db(d), aid)
    default = next((item for item in images if item.get("is_default")), None)
    if default:
        path = asset_db.delete_asset_image_record(asset_db.get_db(d), aid, int(default["id"]))
        if path:
            (d / path).unlink(missing_ok=True)
    else:
        asset_db.update_asset(asset_db.get_db(d), aid, image_path=None, status="prompt_ready")
    return {"ok": True}


IMAGE_UPLOAD_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024


def _valid_uploaded_image(content: bytes, suffix: str) -> bool:
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


@app.post("/api/projects/{name}/assets/{aid}/images/upload")
async def upload_asset_image(name: str, aid: int, file: UploadFile = File(...)):
    d = project_dir(name)
    db_path = asset_db.get_db(d)
    asset_db.init_db(db_path)
    asset = asset_db.get_asset(db_path, aid)
    if not asset:
        raise HTTPException(404, "资产不存在")
    if asset.get("category") not in {"character", "scene", "prop"}:
        raise HTTPException(400, "该资产类型不支持上传图片")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_UPLOAD_SUFFIXES:
        raise HTTPException(400, "仅支持 PNG、JPG、JPEG、WEBP 图片")
    content = await file.read()
    if not content:
        raise HTTPException(400, "图片文件为空")
    if len(content) > IMAGE_UPLOAD_MAX_BYTES:
        raise HTTPException(400, "图片文件不能超过 20MB")
    if not _valid_uploaded_image(content, suffix):
        raise HTTPException(400, "图片格式与文件扩展名不一致或文件已损坏")
    assets_dir = asset_db.get_assets_dir(d)
    assets_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{aid}_upload_{uuid.uuid4().hex}{suffix}"
    target = assets_dir / filename
    target.write_bytes(content)
    relative_path = f"assets/{filename}"
    try:
        image_id = asset_db.add_asset_image(
            db_path,
            aid,
            relative_path,
            source="uploaded",
            make_default=True,
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {
        "ok": True,
        "image": {
            "id": image_id,
            "asset_id": aid,
            "image_path": relative_path,
            "image_url": f"/api/projects/{name}/assets/{aid}/images/{image_id}",
            "source": "uploaded",
            "is_default": 1,
        },
    }


@app.post("/api/projects/{name}/assets/{aid}/image-url")
def set_asset_image_url(name: str, aid: int, body: dict = Body(...)):
    d = project_dir(name)
    db_path = asset_db.get_db(d)
    asset = asset_db.get_asset(db_path, aid)
    if not asset:
        raise HTTPException(404, "资产不存在")
    image_url = str(body.get("image_url") or "").strip()
    parsed = urllib.parse.urlparse(image_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "请输入有效的 http 或 https 公网图片链接")
    seedance_asset_id = str(body.get("seedance_asset_id") or "").strip()
    if seedance_asset_id.startswith("asset://"):
        seedance_asset_id = seedance_asset_id[len("asset://"):].strip()
    if seedance_asset_id and any(char.isspace() for char in seedance_asset_id):
        raise HTTPException(400, "素材 ID 格式无效，应为 asset://<ASSET_ID>")
    asset_db.update_asset(
        db_path, aid, image_url=image_url, seedance_asset_id=seedance_asset_id,
        seedance_asset_name=_asset_display_name(asset), status="ready",
    )
    return {"ok": True, "asset_id": aid, "image_url": image_url, "seedance_asset_id": seedance_asset_id}


@app.get("/api/projects/{name}/assets/{aid}/images")
def list_asset_images(name: str, aid: int):
    rows = asset_db.get_asset_images(asset_db.get_db(project_dir(name)), aid)
    for row in rows:
        row["image_url"] = f"/api/projects/{name}/assets/{aid}/images/{row['id']}"
    return rows


@app.get("/api/projects/{name}/assets/{aid}/images/{image_id}")
def get_asset_candidate_image(name: str, aid: int, image_id: int):
    d = project_dir(name)
    row = next((item for item in asset_db.get_asset_images(asset_db.get_db(d), aid) if item["id"] == image_id), None)
    if not row:
        raise HTTPException(404, "候选图片不存在")
    fp = d / row["image_path"]
    if not fp.exists():
        raise HTTPException(404, "图片文件缺失")
    return FileResponse(fp)


@app.post("/api/projects/{name}/assets/{aid}/images/{image_id}/default")
def set_asset_default_image(name: str, aid: int, image_id: int):
    if not asset_db.set_default_asset_image(asset_db.get_db(project_dir(name)), aid, image_id):
        raise HTTPException(404, "候选图片不存在")
    return {"ok": True}


@app.delete("/api/projects/{name}/assets/{aid}/images/{image_id}")
def delete_asset_candidate_image(name: str, aid: int, image_id: int):
    d = project_dir(name)
    path = asset_db.delete_asset_image_record(asset_db.get_db(d), aid, image_id)
    if path is None:
        raise HTTPException(404, "候选图片不存在")
    (d / path).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/projects/{name}/assets/{aid}/image")
def get_asset_image(name: str, aid: int):
    d = project_dir(name)
    rows = asset_db.get_all(asset_db.get_db(d))
    row = next((r for r in rows if r["id"] == aid), None)
    if not row or not row.get("image_path"):
        raise HTTPException(404, "无图片")
    fp = d / row["image_path"]
    if not fp.exists():
        raise HTTPException(404, "图片文件缺失")
    return FileResponse(fp)


def _asset_prompt_type(asset: dict) -> str:
    if asset.get("category") == "character":
        return "character_look" if asset.get("state") or asset.get("level") == "secondary" else "character"
    if asset.get("category") == "scene":
        return "scene"
    return "prop"


@app.post("/api/projects/{name}/assets/prompts/generate")
def generate_asset_prompts(name: str, req: AssetPromptBatchModel):
    if not 1 <= len(req.asset_ids) <= 5:
        raise HTTPException(400, "每批请选择 1～5 个资产")
    d = project_dir(name)
    db_path = asset_db.get_db(d)
    assets = [asset_db.get_asset(db_path, aid) for aid in req.asset_ids]
    if any(item is None for item in assets):
        raise HTTPException(404, "存在无效资产")
    if any(item and item.get("category") == "character" for item in assets):
        raise HTTPException(400, "人物主形象和造型由用户上传图片，不生成图片提示词")
    grouped = {_asset_prompt_type(item) for item in assets if item}
    if len(grouped) != 1:
        raise HTTPException(400, "每批只能处理同一类型资产")
    # 妆造提示词显式携带父角色基础设定，避免把同一人物生成成不同的脸。
    for item in assets:
        if item and item.get("parent_id"):
            parent = asset_db.get_asset(db_path, item["parent_id"])
            if parent:
                item["parent_name"] = parent.get("name")
                parent_prompt = parent.get("prompt", "")
                item["parent_prompt"] = parent_prompt.split("【资产内容】", 1)[-1].strip() if "【资产内容】" in parent_prompt else parent_prompt
                item["parent_profile"] = parent.get("profile", {})
                item["parent_image_path"] = parent.get("image_path")
    script = (d / "script.txt").read_text(encoding="utf-8") if (d / "script.txt").exists() else ""
    relevant_episodes = sorted({int(ep) for item in assets if item for ep in item.get("episodes", []) if str(ep).isdigit()})
    if relevant_episodes and script:
        episode_map = {int(ep["index"]): ep.get("content", "") for ep in doc_parser.split_episodes(script)}
        context = "\n\n".join(f"第{ep}集\n{episode_map.get(ep, '')}" for ep in relevant_episodes)
    else:
        context = script
    asset_type = next(iter(grouped))
    visual_style = _require_visual_style(d)
    try:
        results = analyzer.generate_image_prompt_batch(_ark_client(), asset_type, assets, context)
    except Exception as exc:
        raise HTTPException(502, f"资产图片提示词生成失败：{exc}")
    final_results = []
    for result in results:
        final_prompt, final_negative = analyzer.apply_unified_visual_style(
            result["prompt"], result.get("negative_prompt", ""), visual_style,
        )
        asset_db.update_asset(
            db_path, result["id"], prompt=final_prompt,
            negative_prompt=final_negative, status="prompt_ready",
        )
        final_results.append({**result, "prompt": final_prompt, "negative_prompt": final_negative})
    return {"count": len(final_results), "assets": final_results, "visual_style": visual_style}


@app.post("/api/projects/{name}/assets/{aid}/images/generate")
def generate_asset_candidate(name: str, aid: int, req: AssetImageGenerateModel):
    try:
        result = image_gen.generate_one(_cfg(), _ark_client(), project_dir(name), aid, req.size, req.make_default)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"资产图片生成失败：{exc}")
    result["image_url"] = f"/api/projects/{name}/assets/{aid}/images/{result['id']}"
    return result


@app.post("/api/projects/{name}/assets/{aid}/register")
def register_seedance_asset(name: str, aid: int, req: AssetRegisterModel):
    db_path = asset_db.get_db(project_dir(name))
    asset = asset_db.get_asset(db_path, aid)
    if not asset:
        raise HTTPException(404, "资产不存在")
    if not (asset.get("image_path") or asset.get("image_url")):
        raise HTTPException(400, "请先上传资产图片或填写公网图片链接")
    asset_db.update_asset(
        db_path, aid, seedance_asset_id=req.seedance_asset_id,
        seedance_asset_name=req.seedance_asset_name or _asset_display_name(asset),
    )
    return {"ok": True}


def _with_fragment_asset_image_urls(name: str, db_path: Path, rows: list[dict]) -> list[dict]:
    """为片段资产补充带版本号的默认图片地址，换图后避免浏览器缓存旧预览。"""
    for item in rows:
        images = asset_db.get_asset_images(db_path, int(item["id"]))
        item["image_count"] = len(images)
        if item.get("image_url"):
            item["image_url"] = item["image_url"]
        elif item.get("image_path"):
            version = images[0]["id"] if images else item["image_count"]
            item["image_url"] = f"/api/projects/{name}/assets/{item['id']}/image?v={version}"
        else:
            item["image_url"] = ""
    return rows


@app.get("/api/projects/{name}/episodes/{episode}/fragments/{fragment_index}/assets")
def get_fragment_asset_bindings(name: str, episode: int, fragment_index: int):
    db_path = asset_db.get_db(project_dir(name))
    rows = _with_fragment_asset_image_urls(name, db_path, asset_db.get_fragment_assets(db_path, episode, fragment_index))
    return {
        "assets": rows,
        "ready": all(item.get("image_path") or item.get("image_url") for item in rows),
        "seedance_ready": all(item.get("seedance_asset_id") or item.get("image_url") for item in rows),
    }


@app.put("/api/projects/{name}/episodes/{episode}/fragments/{fragment_index}/assets")
def update_fragment_asset_bindings(name: str, episode: int, fragment_index: int, req: FragmentAssetBindingModel):
    db_path = asset_db.get_db(project_dir(name))
    requested = [item.model_dump() for item in req.assets] if req.assets else [{"asset_id": aid} for aid in req.asset_ids]
    stored_assets = [asset_db.get_asset(db_path, int(item["asset_id"])) for item in requested]
    if any(item is None for item in stored_assets):
        raise HTTPException(404, "存在无效资产")
    bindings = []
    for requested_item, stored in zip(requested, stored_assets):
        role = requested_item.get("role") or ("character" if stored["category"] == "character" else stored["category"])
        bindings.append({
            "asset_id": stored["id"],
            "role": role,
            "mapping_text": requested_item.get("mapping_text", ""),
        })
    asset_db.set_fragment_assets(db_path, episode, fragment_index, bindings)
    return {"ok": True, "count": len(bindings)}


def _asset_display_name(asset: dict) -> str:
    name = str(asset.get("name") or "").strip()
    state = str(asset.get("state") or "").strip()
    if asset.get("category") == "character" and state and (asset.get("profile") or {}).get("asset_role") != "extra_character":
        return asset_db.normalize_character_look_name(name, state)
    return str(state or name or asset.get("key") or "未命名资产").strip()


def _extract_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI 未返回 JSON 对象")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("AI 返回格式错误")
    return value


def _fragment_asset_mapping_text(bindings: list[dict]) -> str:
    sections = []
    labels = {"character": "角色资产映射", "scene": "场景资产映射", "prop": "道具资产映射"}
    for role in ("character", "scene", "prop"):
        lines = []
        for item in bindings:
            if item.get("role") != role:
                continue
            name = _asset_display_name(item)
            relation = str(item.get("mapping_text") or name).strip()
            lines.append(f"@{name} 是{relation}")
        if lines:
            sections.append(f"【{labels[role]}】：\n" + "\n".join(lines))
    return "\n\n".join(sections)


@app.post("/api/projects/{name}/episodes/{episode}/fragments/{fragment_index}/assets/smart-match")
def smart_match_fragment_assets(name: str, episode: int, fragment_index: int, req: FragmentAssetMatchModel):
    shot_prompt = req.shot_prompt.strip()
    if not shot_prompt:
        raise HTTPException(400, "当前片段镜头提示词为空")
    project = project_dir(name)
    script_path = project / "script.txt"
    episode_context = ""
    context_episode_numbers = []
    if script_path.exists():
        try:
            script_episodes = doc_parser.split_episodes(script_path.read_text(encoding="utf-8"))
            nearby_episodes = [
                item for item in script_episodes
                if 0 < int(item.get("index", 0)) and abs(int(item.get("index", 0)) - episode) <= 5
            ]
            context_episode_numbers = [int(item.get("index", 0)) for item in nearby_episodes]
            episode_context = "\n\n".join(
                f"【{'当前集' if int(item.get('index', 0)) == episode else '参考集'}：第{int(item.get('index', 0))}集】\n"
                f"{str(item.get('content') or '').strip()}"
                for item in nearby_episodes
            ).strip()
        except (OSError, ValueError, TypeError):
            episode_context = ""
            context_episode_numbers = []
    if not episode_context:
        shots_path = project / "shots.json"
        if shots_path.exists():
            try:
                shots_doc = json.loads(shots_path.read_text(encoding="utf-8"))
                episode_data = next(
                    (item for item in shots_doc.get("episodes", []) if int(item.get("episode", 0)) == episode),
                    None,
                )
                if episode_data:
                    episode_context = f"【当前集：第{episode}集】\n{str(episode_data.get('source') or '').strip()}".strip()
                    context_episode_numbers = [episode]
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                episode_context = ""
                context_episode_numbers = []
    db_path = asset_db.get_db(project)
    assets = asset_db.get_all(db_path)
    candidates = []
    for item in assets:
        candidates.append({
            "id": item["id"], "category": item["category"], "name": item.get("name") or "",
            "state": item.get("state") or "", "aliases": item.get("aliases") or [],
            "episodes": item.get("episodes") or [], "has_image": bool(item.get("image_path") or item.get("image_url")),
            "description": (item.get("profile") or {}).get("description") or item.get("prompt") or "",
        })
    default_instruction = """你是影视视频生成资产匹配助手。当前正在处理第 {{CURRENT_EPISODE}} 集。唯一任务是根据【最终视频提示词】判断本片段实际需要哪些资产。

【当前集前后各 5 集的剧本上下文（如存在）】
{{EPISODE_CONTEXT}}

【最终视频提示词（唯一匹配目标）】
{{FINAL_PROMPT}}

【全部资产库】
{{ASSETS_JSON}}

判断规则：
1. 剧本上下文仅用于消歧人物身份、别名、造型阶段、场景位置、道具归属和剧情前后关系；其中已用“当前集”明确标识第 {{CURRENT_EPISODE}} 集。
2. 最终资产结论必须以最终视频提示词为准，只选择画面中实际出现或明确需要保持视觉一致性的资产；上下文其他集、其他片段出现的资产不得选择。
3. 同名、别名或多个造型资产冲突时，结合当前集及前后剧情判断；仍无法确定时宁可不选，不要猜测。
4. 人物资产需匹配当前剧情阶段的正确造型；场景资产需匹配当前实际地点；道具资产需在本片段明确出现或被使用。

只输出合法 JSON：
{"matches":[{"asset_id":1,"role":"character|scene|prop","mapping_text":"该资产在本片段中对应的具体人物、场景或道具，例如：百姓中说话那个人"}]}
规则：asset_id 必须来自资产库；role 必须与资产 category 一致；同一资产只能出现一次；mapping_text 简洁准确，不要包含 @资产名。没有需要的资产就返回空 matches。"""
    template = str(analyzer.load_prompt_template("smart_asset_match") or default_instruction)
    instruction = (
        template.replace("{{CURRENT_EPISODE}}", str(episode))
        .replace("{{EPISODE_CONTEXT}}", episode_context or f"（第 {episode} 集及前后剧本原文不可用，请仅依据最终视频提示词判断）")
        .replace("{{EPISODE_SOURCE}}", episode_context or f"（第 {episode} 集及前后剧本原文不可用，请仅依据最终视频提示词判断）")
        .replace("{{FINAL_PROMPT}}", shot_prompt)
        .replace("{{SHOT_PROMPT}}", shot_prompt)
        .replace("{{ASSETS_JSON}}", json.dumps(candidates, ensure_ascii=False))
    )
    request_capture: dict[str, Any] = {}
    try:
        raw_response = _ark_client().chat(
            instruction,
            temperature=0.1,
            request_capture=request_capture,
        )
        parsed = _extract_json_object(raw_response)
    except Exception as exc:
        raise HTTPException(502, f"智能匹配资产失败：{exc}") from exc
    by_id = {int(item["id"]): item for item in assets}
    bindings = []
    seen = set()
    for match in parsed.get("matches", []) if isinstance(parsed.get("matches"), list) else []:
        if not isinstance(match, dict):
            continue
        try:
            asset_id = int(match.get("asset_id"))
        except (TypeError, ValueError):
            continue
        asset = by_id.get(asset_id)
        if not asset or asset_id in seen:
            continue
        seen.add(asset_id)
        role = "character" if asset["category"] == "character" else asset["category"]
        bindings.append({
            "asset_id": asset_id,
            "role": role,
            "mapping_text": str(match.get("mapping_text") or _asset_display_name(asset)).strip(),
        })
    asset_db.set_fragment_assets(db_path, episode, fragment_index, bindings)
    rows = _with_fragment_asset_image_urls(name, db_path, asset_db.get_fragment_assets(db_path, episode, fragment_index))
    mapping_text = _fragment_asset_mapping_text(rows)
    final_prompt = shot_prompt
    if mapping_text:
        mapping_section = re.compile(
            r"\n*【(?:角色|场景|道具)资产映射】：[\s\S]*?(?=\n\s*【(?!(?:角色|场景|道具)资产映射)[^\n]+】|$)"
        )
        final_prompt = f"{mapping_section.sub('', shot_prompt).rstrip()}\n\n{mapping_text}".strip()

    prompts_path = project / "seedance_prompts.json"
    if prompts_path.exists():
        try:
            prompts_doc = json.loads(prompts_path.read_text(encoding="utf-8"))
            matched_prompt = next(
                (
                    item for item in prompts_doc.get("prompts", [])
                    if int(item.get("episode", prompts_doc.get("episode", 0))) == episode
                    and int(item.get("fragment_index", 0)) == fragment_index
                ),
                None,
            )
            if matched_prompt is not None:
                matched_prompt["final_prompt"] = final_prompt
                prompts_path.write_text(
                    json.dumps(prompts_doc, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.exception("保存资产匹配后的片段提示词失败")

    return {
        "ok": True,
        "episode": episode,
        "context_episode_numbers": context_episode_numbers,
        "assets": rows,
        "mapping_text": mapping_text,
        "final_prompt": final_prompt,
        "request": request_capture or None,
        "raw_response": raw_response,
    }


# ---------------- 步骤触发 ----------------
STEPS = ["analyze", "image", "split", "compose", "report"]


@app.post("/api/projects/{name}/steps/analyze/stream")
def analyze_stream(name: str):
    """资产拆解：先全剧识别人物母档案，再每五集识别造型和局部资产并流式推送。"""
    d = project_dir(name)
    sp = d / "script.txt"
    if not sp.exists():
        raise HTTPException(400, "请先上传剧本")
    script = sp.read_text(encoding="utf-8")

    template = analyzer.load_prompt_template("asset_analysis")
    if not template:
        raise HTTPException(400, "prompts.yaml 缺少 asset_analysis 模板")

    ark = _ark_client()
    db_path = asset_db.get_db(d)
    model_id = ark.models.get("llm", {}).get("endpoint") or ark.models.get("llm", {}).get("model_id")

    episodes = doc_parser.split_episodes(script)
    batch_size = 5
    batches = [episodes[i:i + batch_size] for i in range(0, len(episodes), batch_size)] or [[{"index": 1, "title": "完整剧本", "content": script}]]
    system_prompt = "你是专业影视剧资产分析师，只输出严格 JSON。"
    _require_visual_style(d)

    def event_gen():
        meta = {
            "model": model_id, "script_len": len(script), "episodes": len(episodes),
            "batches": len(batches) + 1, "request_mode": "global_index_then_character_details_then_batched_looks",
            "template_len": len(template), "template": template,
            "system": system_prompt, "temperature": 0.2,
        }
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        merged = {"characters": [], "scenes": [], "props": []}
        index_prompt = analyzer.build_global_character_index_prompt(script)
        yield f"event: batch\ndata: {json.dumps({'index': 1, 'total': None, 'label': '全局人物索引'}, ensure_ascii=False)}\n\n"
        yield f"event: prompt\ndata: {json.dumps({'index': 1, 'total': None, 'prompt': index_prompt}, ensure_ascii=False)}\n\n"
        tokens = []
        diagnostics = {}
        try:
            for token in ark.chat_stream(index_prompt, system=system_prompt, temperature=0.2, diagnostics=diagnostics):
                tokens.append(token)
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'detail': f'全局人物索引识别失败：{exc}'}, ensure_ascii=False)}\n\n"
            return
        raw = "".join(tokens).strip()
        diagnostics.update({"batch": 1, "stage": "global_character_index", "truncated": diagnostics.get("finish_reason") == "length", "output_chars": len(raw)})
        yield f"event: diagnostics\ndata: {json.dumps(diagnostics, ensure_ascii=False)}\n\n"
        yield f"event: raw_batch\ndata: {json.dumps({'index': 1, 'text': raw}, ensure_ascii=False)}\n\n"
        if diagnostics["truncated"]:
            yield f"event: error\ndata: {json.dumps({'detail': '全局人物索引仍达到输出上限，请检查剧本中是否生成了过多无关路人。'}, ensure_ascii=False)}\n\n"
            return
        try:
            index_assets = analyzer.parse_analysis_text(raw)
            character_index = index_assets.get("characters", [])
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'detail': f'全局人物索引解析失败：{exc}'}, ensure_ascii=False)}\n\n"
            return

        character_batch_size = 3
        character_batches = [character_index[i:i + character_batch_size] for i in range(0, len(character_index), character_batch_size)]
        total_batches = 1 + len(character_batches) + len(batches)
        for detail_offset, character_batch in enumerate(character_batches, 1):
            index = detail_offset + 1
            detail_prompt = analyzer.build_character_detail_prompt(script, character_batch)
            names = "、".join(item.get("name", "") for item in character_batch)
            yield f"event: batch\ndata: {json.dumps({'index': index, 'total': total_batches, 'label': f'人物母档案：{names}'}, ensure_ascii=False)}\n\n"
            yield f"event: prompt\ndata: {json.dumps({'index': index, 'total': total_batches, 'prompt': detail_prompt}, ensure_ascii=False)}\n\n"
            tokens = []
            diagnostics = {}
            try:
                for token in ark.chat_stream(detail_prompt, system=system_prompt, temperature=0.2, diagnostics=diagnostics):
                    tokens.append(token)
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'detail': f'人物母档案批次请求失败：{exc}'}, ensure_ascii=False)}\n\n"
                return
            raw = "".join(tokens).strip()
            diagnostics.update({"batch": index, "total": total_batches, "stage": "character_details", "truncated": diagnostics.get("finish_reason") == "length", "output_chars": len(raw)})
            yield f"event: diagnostics\ndata: {json.dumps(diagnostics, ensure_ascii=False)}\n\n"
            yield f"event: raw_batch\ndata: {json.dumps({'index': index, 'total': total_batches, 'text': raw}, ensure_ascii=False)}\n\n"
            if diagnostics["truncated"]:
                yield f"event: error\ndata: {json.dumps({'detail': f'人物母档案批次 {index} 达到输出上限。'}, ensure_ascii=False)}\n\n"
                return
            try:
                detail_assets = analyzer.parse_analysis_text(raw)
                merged = analyzer.merge_assets(merged, {"characters": detail_assets.get("characters", []), "scenes": [], "props": []})
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'detail': f'人物母档案批次解析失败：{exc}'}, ensure_ascii=False)}\n\n"
                return

        character_profiles = analyzer.character_profiles_from_assets(merged)
        for batch_offset, batch in enumerate(batches, 1):
            index = 1 + len(character_batches) + batch_offset
            batch_text = "\n\n".join(
                f"{item.get('title') or ('第' + str(item.get('index')) + '集')}\n{item.get('content', '')}"
                for item in batch
            )
            prompt = analyzer.build_asset_prompt(template, batch_text, character_profiles)
            yield f"event: batch\ndata: {json.dumps({'index': index, 'total': total_batches, 'label': f'第 {(batch_offset - 1) * batch_size + 1}～{min(batch_offset * batch_size, len(episodes))} 集造型与局部资产'}, ensure_ascii=False)}\n\n"
            yield f"event: prompt\ndata: {json.dumps({'index': index, 'total': total_batches, 'prompt': prompt}, ensure_ascii=False)}\n\n"
            tokens = []
            diagnostics = {}
            try:
                for token in ark.chat_stream(prompt, system=system_prompt, temperature=0.2, diagnostics=diagnostics):
                    tokens.append(token)
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'detail': f'第 {index} 批请求失败：{exc}'}, ensure_ascii=False)}\n\n"
                return
            raw = "".join(tokens).strip()
            diagnostics.update({"batch": index, "total": total_batches, "stage": "episode_looks", "truncated": diagnostics.get("finish_reason") == "length", "output_chars": len(raw)})
            yield f"event: diagnostics\ndata: {json.dumps(diagnostics, ensure_ascii=False)}\n\n"
            yield f"event: raw_batch\ndata: {json.dumps({'index': index, 'total': total_batches, 'text': raw}, ensure_ascii=False)}\n\n"
            if diagnostics["truncated"]:
                yield f"event: error\ndata: {json.dumps({'detail': f'第 {index} 批达到输出上限，请缩小每批集数。'}, ensure_ascii=False)}\n\n"
                return
            try:
                merged = analyzer.merge_assets(merged, analyzer.parse_analysis_text(raw))
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'detail': f'第 {index} 批解析失败：{exc}'}, ensure_ascii=False)}\n\n"
                return
        visual_style = _require_visual_style(d)
        for item in merged.get("characters", []):
            item["prompt"] = ""
            item["image_prompt"] = ""
        analyzer.apply_visual_style_to_assets(
            {"characters": [], "scenes": merged.get("scenes", []), "props": merged.get("props", [])},
            visual_style,
        )
        asset_db.insert_assets(db_path, merged)
        (d / "assets.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        count = sum(len(merged[key]) for key in ("characters", "props", "scenes"))
        yield f"event: done\ndata: {json.dumps({'count': count, 'assets': merged}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


class SplitTaskBatchIn(BaseModel):
    episodes: list[int]


_SPLIT_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="split-task")
_SPLIT_TASK_LOCK = threading.RLock()


def _split_tasks_path(project: Path) -> Path:
    return project / "split_tasks.json"


def _load_split_tasks(project: Path) -> list[dict]:
    path = _split_tasks_path(project)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_split_tasks(project: Path, tasks: list[dict]) -> None:
    path = _split_tasks_path(project)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _update_split_task(project: Path, task_id: str, **changes) -> dict | None:
    with _SPLIT_TASK_LOCK:
        tasks = _load_split_tasks(project)
        updated = None
        for task in tasks:
            if task.get("id") == task_id:
                task.update(changes)
                task["updated_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
                updated = task
                break
        _save_split_tasks(project, tasks)
        return updated


def _save_episode_fragments(project: Path, episode: int, title: str, source: str, fragments: list[dict]) -> None:
    with _SPLIT_TASK_LOCK:
        shots_path = project / "shots.json"
        shots_doc = {"episodes": []}
        if shots_path.exists():
            try:
                shots_doc = json.loads(shots_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        existing = shots_doc.get("episodes", [])
        shots_doc["episodes"] = [item for item in existing if item.get("episode") != episode]
        shots_doc["episodes"].append({
            "episode": episode, "title": title, "source": source, "shots": fragments,
        })
        shots_doc["episodes"].sort(key=lambda item: item.get("episode", 0))
        shots_path.write_text(json.dumps(shots_doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_split_task(project_name: str, task_id: str) -> None:
    project = project_dir(project_name)
    task = next((item for item in _load_split_tasks(project) if item.get("id") == task_id), None)
    if not task:
        return
    episode = int(task["episode"])
    started_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    _update_split_task(project, task_id, status="running", stage="准备请求", progress=10, started_at=started_at)
    try:
        script_path = project / "script.txt"
        if not script_path.exists():
            raise ValueError("请先上传剧本")
        episodes = doc_parser.split_episodes(script_path.read_text(encoding="utf-8"))
        selected = next((item for item in episodes if item.get("index") == episode), None)
        if not selected:
            raise ValueError(f"未找到第 {episode} 集")
        title = selected.get("title") or f"第{episode}集"
        episode_text = f"{title}\n{selected.get('content', '')}".strip()
        template = analyzer.load_prompt_template("shot_split")
        if not template:
            raise ValueError("prompts.yaml 缺少 shot_split 模板")
        prompt = splitter.build_fragment_prompt(template, episode_text)
        ark = _ark_client()
        model_id = ark._llm_model()
        system_prompt = "你是专业短剧剧本拆解专家，只输出严格 JSON 数组。"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        request_info = {
            "method": "POST",
            "url": f"{ark.base_url}/chat/completions",
            "headers": {
                "Authorization": "Bearer <已隐藏>",
                "Content-Type": "application/json",
            },
            "body": {
                "model": model_id,
                "messages": messages,
                "temperature": 0.2,
                "stream": True,
            },
            "captured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": "body 与调用 Ark SDK 时实际传入的请求参数一致；仅鉴权密钥已隐藏。",
        }
        _update_split_task(
            project, task_id, stage="等待模型返回", progress=25,
            model=model_id, source_len=len(episode_text), prompt_len=len(prompt), request=request_info,
        )
        tokens: list[str] = []
        diagnostics: dict = {}
        for token in ark.chat_stream(prompt, system=system_prompt, temperature=0.2, diagnostics=diagnostics):
            tokens.append(token)
            if len(tokens) % 80 == 0:
                raw_so_far = "".join(tokens)
                _update_split_task(
                    project, task_id, stage="接收模型返回", progress=55,
                    output_chars=len(raw_so_far), raw_response=raw_so_far,
                )
        raw = "".join(tokens).strip()
        diagnostics["truncated"] = diagnostics.get("finish_reason") == "length"
        diagnostics["output_chars"] = len(raw)
        _update_split_task(
            project, task_id, stage="解析模型返回", progress=80,
            output_chars=len(raw), raw_response=raw, diagnostics=diagnostics,
        )
        if diagnostics["truncated"]:
            raise ValueError("模型达到单次输出 Token 上限，片段结果已被截断。")
        fragments = splitter.parse_fragment_text(raw, episode)
        _save_episode_fragments(project, episode, title, episode_text, fragments)
        total_seconds = sum(int(item["time"][:-1]) for item in fragments)
        _update_split_task(
            project, task_id, status="succeeded", stage="拆解完成", progress=100,
            count=len(fragments), total_seconds=total_seconds,
            result={"episode": episode, "count": len(fragments), "total_seconds": total_seconds, "fragments": fragments},
            finished_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), error_message="",
        )
    except Exception as exc:
        logger.exception("拆解任务失败 project=%s episode=%s task=%s", project_name, episode, task_id)
        _update_split_task(
            project, task_id, status="failed", stage="拆解失败", progress=100,
            error_message=str(exc), finished_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        )


def _run_split_task_batch(project_name: str, task_ids: list[str]) -> None:
    for task_id in task_ids:
        _run_split_task(project_name, task_id)


@app.post("/api/projects/{name}/split-tasks")
def create_split_tasks(name: str, payload: SplitTaskBatchIn):
    project = project_dir(name)
    script_path = project / "script.txt"
    if not script_path.exists():
        raise HTTPException(400, "请先上传剧本")
    available = {
        int(item["index"]): item for item in doc_parser.split_episodes(script_path.read_text(encoding="utf-8"))
        if int(item.get("index", 0)) > 0
    }
    requested = list(dict.fromkeys(int(value) for value in payload.episodes))
    invalid = [value for value in requested if value not in available]
    if not requested:
        raise HTTPException(400, "请至少选择一集")
    if invalid:
        raise HTTPException(400, f"未找到集数：{invalid}")
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    batch_id = uuid.uuid4().hex
    created = []
    with _SPLIT_TASK_LOCK:
        tasks = _load_split_tasks(project)
        for position, episode in enumerate(requested, 1):
            item = {
                "id": uuid.uuid4().hex, "batch_id": batch_id, "batch_position": position,
                "batch_total": len(requested), "project": name, "episode": episode,
                "episode_title": available[episode].get("title") or f"第{episode}集",
                "status": "queued", "stage": "等待执行", "progress": 0,
                "created_at": now, "updated_at": now, "started_at": None, "finished_at": None,
                "model": "", "source_len": len(str(available[episode].get("content", ""))),
                "prompt_len": 0, "output_chars": 0, "count": 0, "total_seconds": 0,
                "request": None, "raw_response": "", "result": None,
                "diagnostics": None, "error_message": "",
            }
            tasks.append(item)
            created.append(item)
        _save_split_tasks(project, tasks)
    _SPLIT_TASK_EXECUTOR.submit(_run_split_task_batch, name, [item["id"] for item in created])
    return {"batch_id": batch_id, "count": len(created), "tasks": created}


def _split_task_summary(task: dict) -> dict:
    return {key: value for key, value in task.items() if key not in {"request", "raw_response", "result", "diagnostics"}}


@app.get("/api/split-tasks")
def list_split_tasks():
    records = []
    if PROJECTS_DIR.exists():
        for project in PROJECTS_DIR.iterdir():
            if project.is_dir():
                records.extend(_split_task_summary(item) for item in _load_split_tasks(project))
    return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)


@app.get("/api/projects/{name}/split-tasks")
def list_project_split_tasks(name: str):
    return sorted(
        (_split_task_summary(item) for item in _load_split_tasks(project_dir(name))),
        key=lambda item: item.get("created_at", ""), reverse=True,
    )


@app.get("/api/projects/{name}/split-tasks/{task_id}")
def get_split_task(name: str, task_id: str):
    task = next((item for item in _load_split_tasks(project_dir(name)) if item.get("id") == task_id), None)
    if not task:
        raise HTTPException(404, "拆解任务不存在")
    return task


@app.post("/api/projects/{name}/steps/split/stream")
def split_stream(name: str, episode: int = 1):
    """流式拆解指定单集；测试阶段前端默认传第 1 集。"""
    d = project_dir(name)
    sp = d / "script.txt"
    if not sp.exists():
        raise HTTPException(400, "请先上传剧本")
    script = sp.read_text(encoding="utf-8")
    episodes = doc_parser.split_episodes(script)
    selected = next((item for item in episodes if item.get("index") == episode), None)
    if not selected:
        raise HTTPException(404, f"未找到第 {episode} 集")

    selected_content = str(selected.get("content", ""))
    embedded_titles = sum(
        1 for line in selected_content.splitlines()
        if doc_parser._EP_CN_PATTERN.match(line)
        or any(pattern.match(line) for pattern in doc_parser._EP_LATIN_PATTERNS)
    )
    if len(episodes) == 1 and (len(selected_content) > 100_000 or embedded_titles >= 2):
        raise HTTPException(
            400,
            "剧本分集解析异常：当前单集疑似包含整部剧本，请检查集标题格式后重新解析。",
        )

    episode_text = f"{selected.get('title') or f'第{episode}集'}\n{selected_content}".strip()
    template = analyzer.load_prompt_template("shot_split")
    if not template:
        raise HTTPException(400, "prompts.yaml 缺少 shot_split 模板")
    prompt = splitter.build_fragment_prompt(template, episode_text)
    ark = _ark_client()
    model_id = ark._llm_model()
    system_prompt = "你是专业短剧剧本拆解专家，只输出严格 JSON 数组。"

    def event_gen():
        meta = {
            "model": model_id,
            "episode": episode,
            "episode_title": selected.get("title") or f"第{episode}集",
            "source_len": len(episode_text),
            "prompt_len": len(prompt),
            "template_len": len(template),
            "template": template,
            "system": system_prompt,
            "temperature": 0.2,
        }
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        yield f"event: source\ndata: {json.dumps({'episode': episode, 'text': episode_text}, ensure_ascii=False)}\n\n"
        yield f"event: prompt\ndata: {json.dumps({'prompt': prompt}, ensure_ascii=False)}\n\n"

        tokens = []
        diagnostics = {}
        try:
            for token in ark.chat_stream(
                prompt, system=system_prompt, temperature=0.2,
                diagnostics=diagnostics,
            ):
                tokens.append(token)
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            diagnostics["stream_error"] = str(exc)
            yield f"event: diagnostics\ndata: {json.dumps(diagnostics, ensure_ascii=False)}\n\n"
            yield f"event: error\ndata: {json.dumps({'detail': f'流式请求错误：{exc}'}, ensure_ascii=False)}\n\n"
            return

        raw = "".join(tokens).strip()
        diagnostics["truncated"] = diagnostics.get("finish_reason") == "length"
        diagnostics["output_chars"] = len(raw)
        yield f"event: diagnostics\ndata: {json.dumps(diagnostics, ensure_ascii=False)}\n\n"
        yield f"event: raw\ndata: {json.dumps({'text': raw}, ensure_ascii=False)}\n\n"
        if diagnostics["truncated"]:
            yield f"event: error\ndata: {json.dumps({'detail': '模型达到单次输出 Token 上限，片段结果已被截断。'}, ensure_ascii=False)}\n\n"
            return

        try:
            fragments = splitter.parse_fragment_text(raw, episode)
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'detail': f'片段解析失败：{exc}'}, ensure_ascii=False)}\n\n"
            return

        shots_path = d / "shots.json"
        shots_doc = {"episodes": []}
        if shots_path.exists():
            try:
                shots_doc = json.loads(shots_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        episode_result = {
            "episode": episode,
            "title": selected.get("title") or f"第{episode}集",
            "source": episode_text,
            "shots": fragments,
        }
        existing = shots_doc.get("episodes", [])
        shots_doc["episodes"] = [item for item in existing if item.get("episode") != episode]
        shots_doc["episodes"].append(episode_result)
        shots_doc["episodes"].sort(key=lambda item: item.get("episode", 0))
        shots_path.write_text(json.dumps(shots_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        total_seconds = sum(int(item["time"][:-1]) for item in fragments)
        done = {
            "episode": episode,
            "count": len(fragments),
            "total_seconds": total_seconds,
            "source": episode_text,
            "fragments": fragments,
        }
        yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.post("/api/projects/{name}/steps/{step}")
def run_step(name: str, step: str):
    if step not in STEPS:
        raise HTTPException(400, f"未知步骤：{step}")
    d = project_dir(name)
    sp = d / "script.txt"
    if not sp.exists():
        raise HTTPException(400, "请先上传剧本")
    script = sp.read_text(encoding="utf-8")

    cfg = _cfg()
    ark = _ark_client()

    try:
        if step == "analyze":
            template = analyzer.load_prompt_template("asset_analysis")
            if not template:
                raise ValueError("prompts.yaml 缺少 asset_analysis 模板")
            system = "你是专业影视剧资产分析师，只输出严格 JSON。"
            _require_visual_style(d)
            index_raw = ark.chat(analyzer.build_global_character_index_prompt(script), system=system, temperature=0.2)
            index_assets = analyzer.parse_analysis_text(index_raw)
            character_index = index_assets.get("characters", [])
            res = {"characters": [], "scenes": [], "props": []}
            for start in range(0, len(character_index), 3):
                detail_raw = ark.chat(
                    analyzer.build_character_detail_prompt(script, character_index[start:start + 3]),
                    system=system, temperature=0.2,
                )
                detail_assets = analyzer.parse_analysis_text(detail_raw)
                res = analyzer.merge_assets(res, {"characters": detail_assets.get("characters", []), "scenes": [], "props": []})
            profiles = analyzer.character_profiles_from_assets(res)
            episodes = doc_parser.split_episodes(script)
            for start in range(0, len(episodes), 5):
                batch = episodes[start:start + 5]
                batch_text = "\n\n".join(f"{item.get('title') or ('第' + str(item.get('index')) + '集')}\n{item.get('content', '')}" for item in batch)
                raw = ark.chat(analyzer.build_asset_prompt(template, batch_text, profiles), system=system, temperature=0.2)
                res = analyzer.merge_assets(res, analyzer.parse_analysis_text(raw))
            visual_style = _require_visual_style(d)
            for item in res.get("characters", []):
                item["prompt"] = ""
                item["image_prompt"] = ""
            analyzer.apply_visual_style_to_assets(
                {"characters": [], "scenes": res.get("scenes", []), "props": res.get("props", [])},
                visual_style,
            )
            asset_db.insert_assets(asset_db.get_db(d), res)
            (d / "assets.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"ok": True, "count": (
                len(res.get("characters", [])) + len(res.get("props", [])) + len(res.get("scenes", []))
            )}
        if step == "image":
            res = image_gen.run(cfg, ark, d)
            return {"ok": True, "count": len(res)}
        if step == "split":
            res = splitter.run(cfg, ark, script, d)
            total = sum(len(e["shots"]) for e in res.get("episodes", []))
            return {"ok": True, "count": total}
        if step == "compose":
            res = prompt_composer.run(cfg, ark, d)
            return {"ok": True, "count": len(res.get("prompts", []))}
        if step == "report":
            import json
            db_path = asset_db.get_db(d)
            assets = asset_db.get_all(db_path)
            shots_count = 0
            if (d / "shots.json").exists():
                shots_count = sum(len(e["shots"]) for e in json.loads((d / "shots.json").read_text(encoding="utf-8")).get("episodes", []))
            prompts_count = 0
            if (d / "seedance_prompts.json").exists():
                prompts_count = len(json.loads((d / "seedance_prompts.json").read_text(encoding="utf-8")).get("prompts", []))
            return {
                "ok": True,
                "report": {
                    "assets": len(assets),
                    "images": sum(1 for a in assets if a.get("image_path")),
                    "shots": shots_count,
                    "prompts": prompts_count,
                },
            }
    except Exception as e:
        raise HTTPException(500, f"步骤 {step} 失败：{e}")


# ---------------- 片段 / 提示词结果 ----------------
@app.get("/api/projects/{name}/shots")
def get_shots(name: str):
    d = project_dir(name)
    p = d / "shots.json"
    if not p.exists():
        raise HTTPException(404, "尚未生成片段")
    import json
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/projects/{name}/prompts")
def get_prompts(name: str, episode: int | None = None):
    d = project_dir(name)
    p = d / "seedance_prompts.json"
    if not p.exists():
        if episode is not None:
            return {"episode": int(episode), "prompts": []}
        raise HTTPException(404, "尚未生成提示词")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if episode is not None:
        legacy_episode = int(doc.get("episode", 0) or 0)
        prompts = [
            item for item in doc.get("prompts", [])
            if int(item.get("episode", legacy_episode) or 0) == int(episode)
        ]
        doc = {**doc, "episode": int(episode), "prompts": prompts}
    return doc


def _episode_target_duration(project: Path, episode: dict) -> int:
    """优先读取本集已保存配置，其次读取片段配置，最后回退 100 秒。"""
    settings_path = project / "seedance_generation.json"
    if settings_path.exists():
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        value = (saved.get("episode_durations") or {}).get(str(episode.get("episode", 1)))
        if value:
            return max(1, int(value))
    for key in ("target_duration", "target_duration_sec", "duration", "duration_sec"):
        value = episode.get(key)
        if value:
            try:
                return max(1, int(float(str(value).rstrip("s秒"))))
            except ValueError:
                pass
    return 100


DEFAULT_NEGATIVE_PROMPT = (
    "模糊，变形，扭曲，多余手指，缺少手指，肢体融合，低质量，低分辨率，"
    "水印，字幕，文字，logo，卡通风格，动画风格，油画风格，过度曝光，欠曝光，噪点"
)


class BasicSettingsModel(BaseModel):
    era_background: str = "现代都市"
    overall_style: str = "写实电影感"
    photorealistic: bool = True
    video_ratio: str = "9:16 竖屏"
    resolution: str = "1080P"
    camera_equipment: str = "Arri Alexa 65 + Panavision Anamorphic"
    overall_tone: str = "自然中性色"
    lighting_tone: str = "柔和自然光"
    camera_rhythm: str = "克制舒缓"
    narrated_drama: bool = False
    special_requirements: str = ""
    negative_prompt: str = ""


class SeedanceGenerateIn(BaseModel):
    episode: int = 1
    target_duration: int = 100
    fragment_index: int | None = None


class VideoGenerateIn(BaseModel):
    episode: int = 1
    fragment_index: int
    prompt: str
    model: str | None = None
    resolution: str = "720p"
    ratio: str = "9:16"
    duration: int = 5
    generate_audio: bool = True
    watermark: bool = False
    use_last_frame: bool = True
    character_asset_ids: list[int] = []
    asset_ids: list[int] = []


class QuickCutIn(BaseModel):
    video_id: str
    keep_ranges: list[list[float]]
    output_name: str = "quick-cut.mp4"


class FragmentQuickCutIn(QuickCutIn):
    episode: int
    fragment_index: int


def _quick_cut_dir(project: Path) -> Path:
    path = project / "quick_cut"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_ffmpeg() -> str:
    """优先使用项目自带的 tools/ffmpeg.exe，否则回退到 PATH 中的 ffmpeg。"""
    local = Path(__file__).resolve().parents[1] / "tools" / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    if local.is_file():
        return str(local)
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"


def _safe_video_path(project: Path, video_id: str) -> Path:
    try:
        relative = base64.urlsafe_b64decode(video_id.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise HTTPException(400, "无效的视频标识") from exc
    candidate = (project / relative).resolve()
    root = project.resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(400, "无效的视频路径")
    if not candidate.is_file():
        raise HTTPException(404, "视频文件不存在")
    return candidate


def _video_payload(project: Path, path: Path) -> dict:
    relative = path.resolve().relative_to(project.resolve()).as_posix()
    video_id = base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii")
    return {
        "id": video_id,
        "name": path.name,
        "size": path.stat().st_size,
        "url": f"/api/projects/{project.name}/quick-cut/videos/{video_id}",
    }


def _load_basic_settings(project: Path) -> dict:
    defaults = BasicSettingsModel().dict()
    path = project / "basic_settings.json"
    if not path.exists():
        return defaults
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            defaults.update({key: value for key, value in saved.items() if key in defaults})
    except (OSError, json.JSONDecodeError):
        logger.warning("读取基本设定失败，使用默认值：%s", path)
    return BasicSettingsModel(**defaults).dict()


@app.get("/api/projects/{name}/basic-settings")
def get_basic_settings(name: str):
    return _load_basic_settings(project_dir(name))


@app.post("/api/projects/{name}/basic-settings")
def save_basic_settings(name: str, body: BasicSettingsModel):
    d = project_dir(name)
    data = body.dict()
    previous = _load_basic_settings(d)
    existing_style = _load_visual_style(d)
    changed = previous != data
    (d / "basic_settings.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not changed and existing_style.get("unified_prompt"):
        return {"ok": True, "settings": data, "visual_style": existing_style, "style_reanalyzed": False}
    style_path = _visual_style_path(d)
    if style_path.exists():
        style_path.unlink()
    try:
        style = _analyze_and_save_visual_style(d, data)
    except Exception as exc:
        raise HTTPException(502, f"基本设定已保存，但统一视觉风格自动分析失败：{exc}") from exc
    return {"ok": True, "settings": data, "visual_style": style, "style_reanalyzed": True}


@app.get("/api/projects/{name}/visual-style")
def get_visual_style(name: str):
    return _load_visual_style(project_dir(name))


@app.post("/api/projects/{name}/visual-style/analyze")
def analyze_visual_style(name: str):
    d = project_dir(name)
    settings = _load_basic_settings(d)
    try:
        return _analyze_and_save_visual_style(d, settings)
    except Exception as exc:
        raise HTTPException(502, f"视觉风格分析结果解析失败：{exc}") from exc


@app.get("/api/projects/{name}/seedance/config")
def get_seedance_config(name: str, episode: int = 1):
    d = project_dir(name)
    shots_path = d / "shots.json"
    if not shots_path.exists():
        raise HTTPException(404, "尚未生成片段")
    doc = json.loads(shots_path.read_text(encoding="utf-8"))
    ep = next((item for item in doc.get("episodes", []) if int(item.get("episode", 0)) == episode), None)
    if not ep:
        raise HTTPException(404, f"未找到第 {episode} 集")
    return {
        "episode": episode,
        "target_duration": _episode_target_duration(d, ep),
        "total": len(ep.get("shots", [])),
    }


def _video_task_dir(project: Path) -> Path:
    path = project / "video_tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_video_task(project: Path, task: dict) -> dict:
    task_id = str(task.get("id") or "")
    if task_id:
        (_video_task_dir(project) / f"{task_id}.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return task


def _video_task_usage(task: dict) -> dict:
    usage = task.get("usage") or task.get("token_usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and isinstance(input_tokens, (int, float)) and isinstance(output_tokens, (int, float)):
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _video_task_media_dir(project: Path) -> Path:
    path = project / "video_tasks" / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _character_audio_references(project: Path, asset_ids: list[int]) -> list[dict]:
    db_path = asset_db.get_db(project)
    asset_db.init_db(db_path)
    references: list[dict] = []
    seen: set[int] = set()
    for asset_id in asset_ids:
        asset = asset_db.get_asset(db_path, int(asset_id))
        if not asset or asset.get("category") != "character":
            continue
        primary_id = int(asset.get("parent_id") or asset["id"])
        if primary_id in seen:
            continue
        primary = asset_db.get_asset(db_path, primary_id)
        if not primary or not primary.get("audio_path"):
            continue
        path = Path(primary["audio_path"])
        if not path.exists():
            continue
        mime = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
        data_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        references.append({
            "asset_id": primary_id,
            "name": primary.get("name") or primary.get("key") or f"人物{primary_id}",
            "audio_name": primary.get("audio_name") or path.name,
            "content": {"type": "audio_url", "audio_url": {"url": data_url}},
        })
        seen.add(primary_id)
    if len(references) > 1:
        names = "、".join(item["name"] for item in references)
        raise HTTPException(400, f"Seedance 单次视频任务最多引用 1 个音频，当前匹配到：{names}")
    return references


def _video_selection_path(project: Path) -> Path:
    return _video_task_dir(project) / "selections.json"


def _load_video_selections(project: Path) -> dict:
    path = _video_selection_path(project)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_video_selections(project: Path, data: dict) -> None:
    _video_selection_path(project).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_latest_video_default(project: Path, task: dict) -> None:
    episode = int(task.get("episode") or 0)
    fragment_index = int(task.get("fragment_index") or 0)
    task_id = str(task.get("id") or "")
    if not episode or not fragment_index or not task_id or task.get("status") != "succeeded":
        return
    key = f"{episode}:{fragment_index}"
    selections = _load_video_selections(project)
    previous = selections.get(key, {})
    previous_task_id = str(previous.get("task_id") or "")
    if previous_task_id and previous_task_id != task_id:
        previous_path = _video_task_dir(project) / f"{previous_task_id}.json"
        try:
            previous_task = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
            if (previous_task.get("created_at") or 0) > (task.get("created_at") or 0):
                return
        except Exception:
            pass
    edited_file = previous.get("edited_file")
    if edited_file:
        (_video_task_media_dir(project) / Path(edited_file).name).unlink(missing_ok=True)
    selections[key] = {"task_id": task_id}
    _save_video_selections(project, selections)


def _ensure_local_video(project: Path, task: dict) -> dict:
    content = task.get("content") or {}
    if not isinstance(content, dict):
        content = {}
    remote_url = content.get("remote_video_url") or content.get("video_url") or task.get("video_url")
    task_id = str(task.get("id") or "")
    if task.get("status") != "succeeded" or not remote_url or not task_id:
        return task
    local_path = _video_task_media_dir(project) / f"{task_id}.mp4"
    if not local_path.exists():
        try:
            with urllib.request.urlopen(remote_url, timeout=120) as response, local_path.open("wb") as output:
                shutil.copyfileobj(response, output)
        except Exception as exc:
            logger.warning("下载视频任务 %s 失败: %s", task_id, exc)
            local_path.unlink(missing_ok=True)
            return task
    content["remote_video_url"] = content.get("remote_video_url") or remote_url
    content["local_video"] = local_path.name
    project_name = str(task.get("project") or project.name)
    content["video_url"] = f"/api/projects/{urllib.parse.quote(project_name, safe='')}/videos/files/{local_path.name}"
    task["content"] = content
    return task


def _video_task_last_frame_url(task: dict) -> str:
    content = task.get("content") or {}
    return str(content.get("last_frame_url") or task.get("last_frame_url") or "").strip() if isinstance(content, dict) else ""


def _last_frame_dir(project: Path) -> Path:
    path = project / "video_last_frames"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_local_last_frame(project: Path, task: dict) -> dict:
    last_frame_url = _video_task_last_frame_url(task)
    if not last_frame_url or task.get("local_last_frame_path"):
        return task
    try:
        request = urllib.request.Request(last_frame_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            image_bytes = response.read()
            content_type = response.headers.get_content_type()
        if not image_bytes:
            return task
        extension = mimetypes.guess_extension(content_type) or Path(urllib.parse.urlparse(last_frame_url).path).suffix or ".png"
        if extension == ".jpe":
            extension = ".jpg"
        output_path = _last_frame_dir(project) / f"{task.get('id') or uuid.uuid4().hex}{extension}"
        output_path.write_bytes(image_bytes)
        task["local_last_frame_path"] = str(output_path.relative_to(project))
        task["local_last_frame_url"] = f"/api/projects/{urllib.parse.quote(project.name)}/videos/last-frames/{urllib.parse.quote(output_path.name)}"
    except Exception as exc:
        logger.warning("下载视频任务 %s 尾帧失败: %s", task.get("id"), exc)
    return task


def _latest_previous_fragment_last_frame(project: Path, episode: int, fragment_index: int) -> dict | None:
    if fragment_index <= 1:
        return None
    candidates = []
    for task_path in _video_task_dir(project).glob("*.json"):
        try:
            task = json.loads(task_path.read_text(encoding="utf-8"))
            if (
                task.get("status") == "succeeded"
                and int(task.get("episode") or 0) == episode
                and int(task.get("fragment_index") or 0) == fragment_index - 1
                and (_video_task_last_frame_url(task) or task.get("local_last_frame_path"))
            ):
                candidates.append(task)
        except Exception:
            continue
    if not candidates:
        return None
    task = max(candidates, key=lambda item: item.get("created_at") or 0)
    task = _ensure_local_last_frame(project, task)
    _save_video_task(project, task)
    local_path = task.get("local_last_frame_path")
    if local_path:
        path = project / local_path
        if path.is_file():
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            return {
                "url": f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}",
                "task_id": task.get("id"),
                "source_url": _video_task_last_frame_url(task),
                "local_url": task.get("local_last_frame_url"),
            }
    source_url = _video_task_last_frame_url(task)
    return {"url": source_url, "task_id": task.get("id"), "source_url": source_url} if source_url else None


def _compact_video_task_request(request: object) -> dict:
    if not isinstance(request, dict):
        return {}
    compact = {key: value for key, value in request.items() if key != "api_payload"}
    payload = request.get("api_payload")
    if not isinstance(payload, dict):
        return compact
    compact_payload = {key: value for key, value in payload.items() if key != "content"}
    compact_content = []
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        compact_item = dict(item)
        image_url = compact_item.get("image_url")
        if isinstance(image_url, dict):
            url = str(image_url.get("url") or "")
            if url.startswith("data:"):
                compact_item["image_url"] = {
                    **image_url,
                    "url": f"[内嵌图片数据已省略，原始长度 {len(url)} 字符]",
                }
        compact_content.append(compact_item)
    compact["api_payload"] = {**compact_payload, "content": compact_content}
    return compact


def _video_task_record(task: dict, project_name: str) -> dict:
    content = task.get("content") or {}
    if not isinstance(content, dict):
        content = {}
    error = task.get("error") or {}
    if not isinstance(error, dict):
        error = {"message": str(error)}
    return {
        **task,
        "request": _compact_video_task_request(task.get("request")),
        "project": task.get("project") or project_name,
        "video_url": content.get("video_url") or task.get("video_url"),
        "last_frame_url": content.get("last_frame_url") or task.get("last_frame_url"),
        "local_last_frame_url": task.get("local_last_frame_url"),
        "error_message": error.get("message") or error.get("code"),
        "token_usage": _video_task_usage(task),
    }


@app.get("/api/video-tasks")
def list_video_tasks(refresh: bool = False):
    """汇总所有剧的视频任务；仅显式请求时刷新尚未结束的任务状态。"""
    if not PROJECTS_DIR.exists():
        return []
    records = []
    client = None
    terminal_statuses = {"succeeded", "failed", "cancelled", "expired"}
    for project in sorted(PROJECTS_DIR.iterdir()):
        task_dir = project / "video_tasks"
        if not project.is_dir() or not task_dir.exists():
            continue
        for task_path in task_dir.glob("*.json"):
            try:
                task = json.loads(task_path.read_text(encoding="utf-8"))
                if refresh and task.get("id") and task.get("status") not in terminal_statuses:
                    try:
                        client = client or ArkClient()
                        latest = client.get_video_task(str(task["id"]))
                        for key in ("project", "episode", "fragment_index", "request"):
                            if key in task:
                                latest[key] = task[key]
                        task = _save_video_task(project, latest)
                    except Exception as exc:
                        logger.warning("刷新视频任务 %s 失败: %s", task.get("id"), exc)
                if task.get("status") == "succeeded":
                    task = _ensure_local_video(project, task)
                    task = _ensure_local_last_frame(project, task)
                    _make_latest_video_default(project, task)
                    _save_video_task(project, task)
                records.append(_video_task_record(task, project.name))
            except Exception as exc:
                logger.warning("读取视频任务文件 %s 失败: %s", task_path, exc)
    records.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
    return records


@app.get("/api/projects/{name}/videos/latest-success")
def list_latest_success_videos(name: str, episode: int | None = None):
    """返回每个集/片段最近一次成功生成的视频。"""
    project = project_dir(name)
    latest = {}
    latest_frames = {}
    selections = _load_video_selections(project)
    for task_path in _video_task_dir(project).glob("*.json"):
        try:
            task = json.loads(task_path.read_text(encoding="utf-8"))
            task_episode = int(task.get("episode") or 0)
            fragment_index = int(task.get("fragment_index") or 0)
            content = task.get("content") or {}
            video_url = (content.get("video_url") if isinstance(content, dict) else None) or task.get("video_url")
            if task.get("status") != "succeeded" or not video_url or not task_episode or not fragment_index:
                continue
            if episode is not None and task_episode != episode:
                continue
            key = f"{task_episode}:{fragment_index}"
            selection = selections.get(key, {})
            selected_task_id = selection.get("task_id")
            created_at = task.get("created_at") or 0
            if (_video_task_last_frame_url(task) or task.get("local_last_frame_path")) and (key not in latest_frames or created_at > latest_frames[key][0]):
                task = _ensure_local_last_frame(project, task)
                _save_video_task(project, task)
                latest_frames[key] = (created_at, task)
            current_selected = bool(selected_task_id and latest.get(key, {}).get("id") == selected_task_id)
            should_select = task.get("id") == selected_task_id or (not current_selected and (key not in latest or created_at > (latest[key].get("created_at") or 0)))
            if should_select:
                task = _ensure_local_video(project, task)
                task = _ensure_local_last_frame(project, task)
                _save_video_task(project, task)
                latest[key] = _video_task_record(task, name)
        except Exception as exc:
            logger.warning("读取成功视频任务 %s 失败: %s", task_path, exc)
    for key, record in latest.items():
        frame_task = latest_frames.get(key, (None, None))[1]
        if frame_task:
            record["last_frame_url"] = _video_task_last_frame_url(frame_task)
            record["local_last_frame_url"] = frame_task.get("local_last_frame_url")
            record["last_frame_task_id"] = frame_task.get("id")
        selection = selections.get(key, {})
        edited_file = selection.get("edited_file")
        if edited_file and (_video_task_media_dir(project) / Path(edited_file).name).exists():
            record["original_video_url"] = record.get("video_url")
            record["video_url"] = f"/api/projects/{urllib.parse.quote(name, safe='')}/videos/files/{Path(edited_file).name}"
            record["edited_file"] = Path(edited_file).name
        record["is_default"] = record.get("id") == selection.get("task_id")
    return latest


@app.post("/api/projects/{name}/videos/generate")
def create_video_generation(name: str, body: VideoGenerateIn):
    """使用当前片段提示词与页面设置创建 Seedance 视频生成任务。"""
    project = project_dir(name)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "请先填写当前片段的 Seedance 提示词")
    prompt_lines = []
    negative_prompt_seen = False
    for line in prompt.splitlines():
        is_negative_prompt = bool(re.match(r"^\s*【?negative_prompt】?\s*[：:]", line, re.IGNORECASE))
        if is_negative_prompt and negative_prompt_seen:
            continue
        if is_negative_prompt:
            negative_prompt_seen = True
        prompt_lines.append(line)
    prompt = "\n".join(prompt_lines).strip()
    duration = max(2, min(int(body.duration or 5), 15))
    resolution = str(body.resolution or "720p").strip().lower()
    if resolution not in {"480p", "720p", "1080p"}:
        resolution = "720p"
    ratio = str(body.ratio or "9:16").split()[0]
    if ratio not in {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"}:
        ratio = "9:16"
    db_path = asset_db.get_db(project)
    bound_assets = asset_db.get_fragment_assets(db_path, body.episode, body.fragment_index)
    requested_ids = {int(value) for value in body.asset_ids}
    if requested_ids:
        bound_assets = [item for item in bound_assets if int(item["id"]) in requested_ids]
    mapping_text = _fragment_asset_mapping_text(bound_assets)
    if mapping_text and mapping_text not in prompt:
        prompt = f"{prompt.rstrip()}\n\n{mapping_text}"
    continuity_frame = (
        _latest_previous_fragment_last_frame(project, body.episode, body.fragment_index)
        if body.use_last_frame
        else None
    )
    image_references = []
    if continuity_frame:
        image_references.append({
            "asset_id": None,
            "name": f"上一片段尾帧（片段 {body.fragment_index - 1}）",
            "mapping_text": "上一片段的尾帧画面，仅作为当前片段的临时视觉参考，不是当前片段首帧",
            "temporary": True,
            "content": {"type": "image_url", "image_url": {"url": continuity_frame["url"]}, "role": "reference_image"},
        })
    missing_image_assets = []
    for item in bound_assets:
        public_image_url = str(item.get("image_url") or "").strip()
        reference_url = str(item.get("seedance_asset_id") or "").strip()
        if reference_url and not reference_url.startswith("asset://"):
            reference_url = f"asset://{reference_url}"
        if not reference_url and public_image_url:
            reference_url = public_image_url
        if not reference_url:
            image_path = item.get("image_path")
            if not image_path:
                missing_image_assets.append(_asset_display_name(item))
                continue
            path = Path(image_path)
            if not path.is_absolute():
                path = project / path
            if not path.is_file():
                missing_image_assets.append(_asset_display_name(item))
                logger.warning("片段资产图片不存在，跳过引用：asset_id=%s path=%s", item.get("id"), path)
                continue
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            reference_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        image_references.append({
            "asset_id": item["id"],
            "name": _asset_display_name(item),
            "mapping_text": str(item.get("mapping_text") or _asset_display_name(item)).strip(),
            "content": {"type": "image_url", "image_url": {"url": reference_url}, "role": "reference_image"},
        })
    if len(image_references) > 9:
        continuity_count = 1 if continuity_frame else 0
        raise HTTPException(400, f"Seedance 单次视频任务最多使用 9 张图片，当前为 {len(image_references)} 张（临时尾帧 {continuity_count} 张，资产图 {len(image_references) - continuity_count} 张）")
    if bound_assets and not any(not item.get("temporary") for item in image_references):
        detail = "、".join(missing_image_assets) or "当前片段资产"
        raise HTTPException(400, f"当前片段没有可提交的资产图片：{detail}")
    if image_references:
        reference_lines = [
            f"@图片{index}（资产名：{item['name']}）是{item['mapping_text']}"
            for index, item in enumerate(image_references, start=1)
        ]
        prompt = re.sub(r"\n*【参考图片对应关系】：[\s\S]*$", "", prompt).rstrip()
        prompt = f"{prompt}\n\n【参考图片对应关系】：\n" + "\n".join(reference_lines)
    audio_references = _character_audio_references(project, body.character_asset_ids)
    reference_content = [item["content"] for item in image_references] + [item["content"] for item in audio_references]
    request_content = [{"type": "text", "text": prompt}, *reference_content]
    try:
        task = ArkClient().create_video_task(
            prompt=prompt,
            model=body.model,
            resolution=resolution,
            ratio=ratio,
            duration=duration,
            generate_audio=body.generate_audio,
            watermark=body.watermark,
            return_last_frame=True,
            reference_content=reference_content,
        )
    except Exception as exc:
        error_text = str(exc)
        content_match = re.search(r"content\[(\d+)\]", error_text, re.IGNORECASE)
        content_index = int(content_match.group(1)) if content_match else None
        reference_index = content_index - 1 if content_index is not None else None
        reference_name = None
        reference_asset_id = None
        if reference_index is not None and 0 <= reference_index < len(image_references):
            failed_reference = image_references[reference_index]
            reference_name = failed_reference["name"]
            reference_asset_id = failed_reference["asset_id"]
        if "InputImageSensitiveContentDetected.PrivacyInformation" in error_text:
            target = (
                f"资产“{reference_name}”（ID: {reference_asset_id}，请求位置 content[{content_index}]）"
                if reference_name else f"请求中的图片 content[{content_index}]" if content_index is not None else "某张参考图片"
            )
            request_id_match = re.search(r"Request id:\s*([\w-]+)", error_text, re.IGNORECASE)
            request_id_hint = f"\n请求 ID：{request_id_match.group(1)}" if request_id_match else ""
            raise HTTPException(
                400,
                f"{target}被 Seedance 判定可能包含真人或隐私信息，无法用于视频生成。请移除该资产，或将它更新为不含真实人物的虚构角色/AI 生成图片后重试。{request_id_hint}",
            ) from exc
        raise HTTPException(500, f"创建 Seedance 视频任务失败：{exc}") from exc
    task.update({
        "project": name,
        "episode": body.episode,
        "fragment_index": body.fragment_index,
        "request": {
            "prompt": prompt,
            "model": body.model,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "generate_audio": body.generate_audio,
            "watermark": body.watermark,
            "return_last_frame": True,
            "character_asset_ids": body.character_asset_ids,
            "asset_ids": [item["id"] for item in bound_assets],
            "continuity_frame": ({
                "source_fragment_index": body.fragment_index - 1,
                "source_task_id": continuity_frame.get("task_id"),
                "source_url": continuity_frame.get("source_url"),
                "local_url": continuity_frame.get("local_url"),
            } if continuity_frame else None),
            "asset_image_references": [
                {"asset_id": item["asset_id"], "name": item["name"]}
                for item in image_references if not item.get("temporary")
            ],
            "character_audio_references": [
                {key: item[key] for key in ("asset_id", "name", "audio_name")}
                for item in audio_references
            ],
            "api_payload": {
                "model": body.model,
                "content": request_content,
                "resolution": resolution,
                "ratio": ratio,
                "duration": duration,
                "generate_audio": body.generate_audio,
                "watermark": body.watermark,
                "return_last_frame": True,
            },
        },
    })
    return _save_video_task(project, task)


@app.get("/api/projects/{name}/videos/tasks/{task_id}")
def get_video_generation(name: str, task_id: str):
    """查询 Seedance 任务状态；任务成功时返回 content.video_url。"""
    project = project_dir(name)
    try:
        task = ArkClient().get_video_task(task_id)
    except Exception as exc:
        raise HTTPException(500, f"查询 Seedance 视频任务失败：{exc}") from exc
    previous_path = _video_task_dir(project) / f"{task_id}.json"
    if previous_path.exists():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            for key in ("project", "episode", "fragment_index", "request"):
                if key in previous:
                    task[key] = previous[key]
        except Exception:
            pass
    if task.get("status") == "succeeded":
        task = _ensure_local_video(project, task)
        task = _ensure_local_last_frame(project, task)
        _make_latest_video_default(project, task)
    return _save_video_task(project, task)


@app.get("/api/projects/{name}/videos/files/{filename}")
def get_local_video_file(name: str, filename: str):
    project = project_dir(name)
    safe_name = Path(filename).name
    path = _video_task_media_dir(project) / safe_name
    if not path.exists():
        raise HTTPException(404, "视频文件不存在")
    return FileResponse(path, media_type="video/mp4", filename=safe_name)


@app.get("/api/projects/{name}/videos/last-frames/{filename}")
def get_local_video_last_frame(name: str, filename: str):
    project = project_dir(name)
    safe_name = Path(filename).name
    path = _last_frame_dir(project) / safe_name
    if not path.exists():
        raise HTTPException(404, "尾帧图片不存在")
    return FileResponse(path, filename=safe_name)


@app.get("/api/projects/{name}/videos/history")
def list_fragment_video_history(name: str, episode: int, fragment_index: int):
    project = project_dir(name)
    key = f"{episode}:{fragment_index}"
    selection = _load_video_selections(project).get(key, {})
    records = []
    for task_path in _video_task_dir(project).glob("*.json"):
        try:
            task = json.loads(task_path.read_text(encoding="utf-8"))
            if int(task.get("episode") or 0) != episode or int(task.get("fragment_index") or 0) != fragment_index:
                continue
            if task.get("status") == "succeeded":
                task = _ensure_local_video(project, task)
                _save_video_task(project, task)
            record = _video_task_record(task, name)
            record["is_default"] = record.get("id") == selection.get("task_id")
            records.append(record)
        except Exception as exc:
            logger.warning("读取片段历史任务 %s 失败: %s", task_path, exc)
    records.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
    return {"records": records, "selection": selection}


@app.post("/api/projects/{name}/videos/default")
def set_fragment_default_video(name: str, body: dict = Body(...)):
    project = project_dir(name)
    episode = int(body.get("episode") or 0)
    fragment_index = int(body.get("fragment_index") or 0)
    task_id = str(body.get("task_id") or "")
    task_path = _video_task_dir(project) / f"{task_id}.json"
    if not episode or not fragment_index or not task_path.exists():
        raise HTTPException(404, "视频生成记录不存在")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    if task.get("status") != "succeeded":
        raise HTTPException(400, "只能将生成成功的视频设为默认")
    task = _ensure_local_video(project, task)
    _save_video_task(project, task)
    key = f"{episode}:{fragment_index}"
    selections = _load_video_selections(project)
    previous = selections.get(key, {})
    edited_file = previous.get("edited_file")
    if edited_file:
        (_video_task_media_dir(project) / Path(edited_file).name).unlink(missing_ok=True)
    selections[key] = {"task_id": task_id}
    _save_video_selections(project, selections)
    return _video_task_record(task, name)


@app.post("/api/projects/{name}/seedance/generate/stream")
def generate_seedance_stream(name: str, body: SeedanceGenerateIn):
    """按顺序逐个请求本集片段，并通过 SSE 报告片段级进度。"""
    d = project_dir(name)
    shots_path = d / "shots.json"
    if not shots_path.exists():
        raise HTTPException(400, "请先完成片段拆解")
    template = analyzer.load_prompt_template("seedance_prompt")
    if not template.strip():
        raise HTTPException(400, "“Seedance 生成提示词”为空，请先在提示词设置中填写")

    doc = json.loads(shots_path.read_text(encoding="utf-8"))
    episode = next(
        (item for item in doc.get("episodes", []) if int(item.get("episode", 0)) == body.episode),
        None,
    )
    if not episode:
        raise HTTPException(404, f"未找到第 {body.episode} 集")
    fragments = episode.get("shots", [])
    if not fragments:
        raise HTTPException(400, "当前剧集没有已拆好的片段")
    if body.fragment_index is not None:
        if body.fragment_index < 1 or body.fragment_index > len(fragments):
            raise HTTPException(400, f"片段序号必须在 1 到 {len(fragments)} 之间")
        generation_items = [(body.fragment_index - 1, fragments[body.fragment_index - 1])]
    else:
        generation_items = list(enumerate(fragments))

    target_duration = max(1, body.target_duration or _episode_target_duration(d, episode))
    basic_settings = _load_basic_settings(d)
    settings_path = d / "seedance_generation.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    settings.setdefault("episode_durations", {})[str(body.episode)] = target_duration
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def event_gen():
        ark = _ark_client()
        total = len(generation_items)
        seedance_path = d / "seedance_prompts.json"
        existing_doc = json.loads(seedance_path.read_text(encoding="utf-8")) if seedance_path.exists() else {}
        existing_results = existing_doc.get("prompts", [])
        other_episode_results = [
            item for item in existing_results
            if int(item.get("episode", existing_doc.get("episode", 0)) or 0) != body.episode
        ]
        current_episode_results = [
            item for item in existing_results
            if int(item.get("episode", existing_doc.get("episode", 0)) or 0) == body.episode
        ] if body.fragment_index is not None else []
        results_by_index = {
            int(item.get("fragment_index", 0)): item
            for item in current_episode_results
            if item.get("fragment_index")
        }
        previous = None
        if body.fragment_index and body.fragment_index > 1:
            previous_item = results_by_index.get(body.fragment_index - 1)
            previous = previous_item.get("result") if previous_item else None
        completed = 0
        yield f"event: meta\ndata: {json.dumps({'episode': body.episode, 'total': total, 'target_duration': target_duration}, ensure_ascii=False)}\n\n"
        try:
            for task_index, (fragment_index, fragment) in enumerate(generation_items):
                label = fragment.get("scene") or fragment.get("text", "")[:30] or f"片段 {fragment_index + 1}"
                yield f"event: progress\ndata: {json.dumps({'total': total, 'completed': task_index, 'current': task_index + 1, 'fragment_index': fragment_index + 1, 'label': label, 'percent': round(task_index / total * 100)}, ensure_ascii=False)}\n\n"
                system_prompt, user_prompt = prompt_composer.build_episode_fragment_prompt(
                    template, episode, fragment, fragment_index, target_duration, previous,
                    basic_settings=basic_settings,
                )
                raw_parts = []
                diagnostics = {}
                original_request = {}
                stream = iter(ark.chat_stream(
                    user_prompt, system=system_prompt, temperature=0.2,
                    diagnostics=diagnostics, json_mode=True,
                    request_capture=original_request,
                ))
                first_token = next(stream, None)
                yield f"event: request\ndata: {json.dumps({'current': task_index + 1, 'total': total, 'fragment_index': fragment_index + 1, 'label': label, 'original_request': original_request}, ensure_ascii=False)}\n\n"
                if first_token is not None:
                    raw_parts.append(first_token)
                    yield f"event: response_token\ndata: {json.dumps({'current': task_index + 1, 'fragment_index': fragment_index + 1, 'token': first_token}, ensure_ascii=False)}\n\n"
                for token in stream:
                    raw_parts.append(token)
                    yield f"event: response_token\ndata: {json.dumps({'current': task_index + 1, 'fragment_index': fragment_index + 1, 'token': token}, ensure_ascii=False)}\n\n"
                raw = "".join(raw_parts)
                if diagnostics.get("finish_reason") == "length":
                    raise ValueError("模型返回因长度限制被截断，请减少单个片段内容或提高模型输出上限")
                try:
                    result = prompt_composer.parse_seedance_result(raw)
                except ValueError as exc:
                    yield f"event: parse_error\ndata: {json.dumps({'current': task_index + 1, 'fragment_index': fragment_index + 1, 'detail': str(exc), 'raw': raw}, ensure_ascii=False)}\n\n"
                    raise
                item = {
                    "episode": body.episode,
                    "fragment_index": fragment_index + 1,
                    "source": fragment,
                    "result": result,
                }
                results_by_index[fragment_index + 1] = item
                previous = result
                completed += 1
                saved_results = other_episode_results + [results_by_index[key] for key in sorted(results_by_index)]
                saved_results.sort(key=lambda entry: (
                    int(entry.get("episode", existing_doc.get("episode", 0)) or 0),
                    int(entry.get("fragment_index", 0) or 0),
                ))
                seedance_path.write_text(
                    json.dumps({"target_duration": target_duration, "prompts": saved_results}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                yield f"event: fragment_done\ndata: {json.dumps({'total': total, 'completed': completed, 'current': task_index + 1, 'fragment_index': fragment_index + 1, 'label': label, 'percent': round(completed / total * 100), 'result': item}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'total': total, 'completed': total, 'percent': 100}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("Seedance 逐片段生成失败")
            yield f"event: error\ndata: {json.dumps({'detail': str(exc), 'completed': completed, 'total': total}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/api/projects/{name}/quick-cut/videos")
def list_quick_cut_videos(name: str):
    project = project_dir(name)
    extensions = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
    videos = [
        _video_payload(project, path)
        for path in project.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    ]
    videos.sort(key=lambda item: item["name"])
    return videos


@app.post("/api/projects/{name}/quick-cut/upload")
async def upload_quick_cut_video(name: str, file: UploadFile = File(...)):
    project = project_dir(name)
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}:
        raise HTTPException(400, "仅支持 MP4、MOV、M4V、WEBM、MKV 视频")
    safe_name = Path(file.filename or f"video{suffix}").name
    target = _quick_cut_dir(project) / f"{uuid.uuid4().hex}_{safe_name}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return _video_payload(project, target)


@app.get("/api/projects/{name}/quick-cut/videos/{video_id}")
def get_quick_cut_video(name: str, video_id: str):
    project = project_dir(name)
    path = _safe_video_path(project, video_id)
    return FileResponse(path)


@app.post("/api/projects/{name}/quick-cut/export")
def export_quick_cut(name: str, body: QuickCutIn):
    project = project_dir(name)
    source = _safe_video_path(project, body.video_id)
    ranges = sorted(
        ([max(0.0, float(item[0])), max(0.0, float(item[1]))] for item in body.keep_ranges if len(item) == 2),
        key=lambda item: item[0],
    )
    ranges = [item for item in ranges if item[1] - item[0] >= 0.05]
    if not ranges:
        raise HTTPException(400, "至少需要保留一个有效时间段")

    output_name = Path(body.output_name or "quick-cut.mp4").name
    if not output_name.lower().endswith(".mp4"):
        output_name += ".mp4"
    target = _quick_cut_dir(project) / f"export_{uuid.uuid4().hex}_{output_name}"
    work_dir = Path(tempfile.mkdtemp(prefix="quick_cut_", dir=_quick_cut_dir(project)))
    try:
        segments = []
        ffmpeg_bin = _resolve_ffmpeg()
        for index, (start, end) in enumerate(ranges):
            segment = work_dir / f"segment_{index:04d}.mp4"
            command = [
                ffmpeg_bin, "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-c:a", "aac", "-movflags", "+faststart", str(segment),
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip()[-1200:] or "FFmpeg 裁剪失败")
            segments.append(segment)

        concat_file = work_dir / "concat.txt"
        concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in segments), encoding="utf-8")
        completed = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart", str(target)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip()[-1200:] or "FFmpeg 合并失败")
    except FileNotFoundError as exc:
        raise HTTPException(500, "未找到 FFmpeg，无法执行视频裁剪") from exc
    except RuntimeError as exc:
        logger.exception("快剪导出失败")
        raise HTTPException(500, str(exc)) from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return FileResponse(target, media_type="video/mp4", filename=output_name)


@app.post("/api/projects/{name}/videos/quick-cut")
def export_fragment_quick_cut(name: str, body: FragmentQuickCutIn):
    project = project_dir(name)
    source = _safe_video_path(project, body.video_id)
    ranges = sorted(
        ([max(0.0, float(item[0])), max(0.0, float(item[1]))] for item in body.keep_ranges if len(item) == 2),
        key=lambda item: item[0],
    )
    ranges = [item for item in ranges if item[1] - item[0] >= 0.05]
    if not ranges:
        raise HTTPException(400, "至少需要保留一个有效时间段")
    key = f"{body.episode}:{body.fragment_index}"
    selections = _load_video_selections(project)
    selection = selections.get(key, {})
    old_edited = selection.get("edited_file")
    if old_edited:
        (_video_task_media_dir(project) / Path(old_edited).name).unlink(missing_ok=True)
    target_name = f"edited-ep{body.episode}-fragment{body.fragment_index}-{uuid.uuid4().hex}.mp4"
    target = _video_task_media_dir(project) / target_name
    work_dir = Path(tempfile.mkdtemp(prefix="fragment_cut_", dir=_quick_cut_dir(project)))
    try:
        ffmpeg_bin = _resolve_ffmpeg()
        segments = []
        for index, (start, end) in enumerate(ranges):
            segment = work_dir / f"segment_{index:04d}.mp4"
            completed = subprocess.run([ffmpeg_bin, "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-movflags", "+faststart", str(segment)], capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip()[-1200:] or "FFmpeg 裁剪失败")
            segments.append(segment)
        concat_file = work_dir / "concat.txt"
        concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in segments), encoding="utf-8")
        completed = subprocess.run([ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart", str(target)], capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip()[-1200:] or "FFmpeg 合并失败")
    except FileNotFoundError as exc:
        raise HTTPException(500, "未找到 FFmpeg，无法执行视频裁剪") from exc
    except RuntimeError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(500, str(exc)) from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    selection["edited_file"] = target_name
    selections[key] = selection
    _save_video_selections(project, selections)
    return {"video_url": f"/api/projects/{urllib.parse.quote(name, safe='')}/videos/files/{target_name}", "edited_file": target_name}


@app.delete("/api/projects/{name}/videos/quick-cut")
def restore_fragment_quick_cut(name: str, episode: int, fragment_index: int):
    project = project_dir(name)
    key = f"{episode}:{fragment_index}"
    selections = _load_video_selections(project)
    selection = selections.get(key, {})
    edited_file = selection.pop("edited_file", None)
    if edited_file:
        (_video_task_media_dir(project) / Path(edited_file).name).unlink(missing_ok=True)
    selections[key] = selection
    _save_video_selections(project, selections)
    return {"ok": True}


@app.get("/")
def index():
    return HTMLResponse(INDEX_HTML)


if __name__ == "__main__":
    import uvicorn
    port = 8000
    reload = True  # 开发模式：改动 web/ 或 src/ 下文件自动重启，无需手动重启
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])
    if "--no-reload" in sys.argv:
        reload = False
    host = "0.0.0.0"  # 允许同一局域网内的设备访问
    if reload:
        # reload 模式下必须传导入路径字符串，uvicorn 才能可靠监听文件变化
        uvicorn.run("web.app:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(app, host=host, port=port, reload=False)
