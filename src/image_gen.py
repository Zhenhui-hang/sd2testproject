"""模块2：资产生图。

从该剧的 SQLite 资产库读取全部资产，对未生成图片的资产调用 Seedream 5.0 pro
生成图片，保存到 projects/<剧>/assets/<id>.png，并把 image_path 写回 SQLite。

- 跳过已有图片的资产（幂等）
- 单张失败重试 3 次，仍失败则记录并继续
- 真实生图会产生费用（每资产一次调用）
"""
from __future__ import annotations

import base64
import mimetypes
import time
from datetime import datetime
from pathlib import Path

from src import db as asset_db


def _image_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def generate_one(cfg: dict, ark_client, project_dir: Path, asset_id: int, size: str = "1024x1024", make_default: bool = False) -> dict:
    """为单个资产生成候选图片；首张图自动成为默认图。"""
    db_path = asset_db.get_db(project_dir)
    asset = asset_db.get_asset(db_path, asset_id)
    if not asset:
        raise ValueError("资产不存在")
    prompt = (asset.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("请先生成或填写资产图片提示词")
    assets_dir = asset_db.get_assets_dir(project_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    reference_images = None
    if asset.get("category") == "character" and asset.get("parent_id"):
        parent = asset_db.get_asset(db_path, asset["parent_id"])
        parent_image = (parent or {}).get("image_path")
        if not parent_image:
            raise ValueError("请先为所属人物生成并确认默认正脸图，再生成造型图")
        parent_path = project_dir / parent_image
        if not parent_path.exists():
            raise ValueError("所属人物的默认正脸图文件不存在，请重新选择或生成")
        reference_images = [_image_data_uri(parent_path)]
    img_bytes = ark_client.generate_image(prompt, size=size, reference_images=reference_images)
    if not img_bytes:
        raise RuntimeError("图片生成接口未返回图片")
    fname = f"{asset_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    (assets_dir / fname).write_bytes(img_bytes)
    rel = f"assets/{fname}"
    image_id = asset_db.add_asset_image(db_path, asset_id, rel, source="generated", make_default=make_default)
    return {"id": image_id, "asset_id": asset_id, "image_path": rel}


def run(cfg: dict, ark_client, project_dir: Path, size: str = "1024x1024") -> list:
    """为所有缺少默认图且已有图片提示词的资产生成首张图片。"""
    db_path = asset_db.get_db(project_dir)
    generated = []
    for asset in asset_db.get_assets(db_path):
        existing = asset.get("image_path")
        if existing and (project_dir / existing).exists():
            generated.append(asset)
            continue
        if not (asset.get("prompt") or "").strip():
            print(f"[模块2] 跳过无提示词资产：{asset['key']} ({asset['id']})")
            continue
        for attempt in range(3):
            try:
                result = generate_one(cfg, ark_client, project_dir, asset["id"], size=size, make_default=True)
                asset["image_path"] = result["image_path"]
                generated.append(asset)
                print(f"[模块2] 生成成功：{asset['key']} ({asset['id']})")
                break
            except Exception as exc:
                print(f"[模块2] 第 {attempt + 1} 次失败 {asset['key']}: {exc}")
                time.sleep(2)
    print(f"[模块2] 生图完成，共处理 {len(generated)} 个资产")
    return generated
