"""模块4：片段 → Seedance 提示词 + @资产声明。

对每个片段(shot)：
  1. 调 doubao-seed-evolving-latest-version（seedance_prompt 模板）→ 生成精细视频提示词结构
     {prompt, camera, motion, style, duration_sec}
  2. 调 doubao-seed-evolving-latest-version（asset_match 模板）→ 传入片段 + 资产清单，判定用到的资产，
     产出带 @key 声明的 final_prompt

结果写 projects/<剧>/seedance_prompts.json，并把每个 shot 的 used_asset_ids 写回 shots.json。

说明：此模块含两段 LLM 调用（每片段），真实运行会产生费用。
"""
from __future__ import annotations

import json
from pathlib import Path

from src.analyzer import load_prompt_template, _strip_code_fence
from src import db as asset_db


def _shot_text(shot: dict) -> str:
    """组装片段的可读文本（场景 + 台词 + 动作）。"""
    parts = [f"场景：{shot.get('scene', '')}"]
    if shot.get("actions"):
        parts.append("动作/描写：\n" + "\n".join(shot["actions"]))
    if shot.get("lines"):
        parts.append("台词：\n" + "\n".join(f"{l['speaker']}：{l['text']}" for l in shot["lines"]))
    if shot.get("text"):
        parts.append("原文：\n" + shot["text"])
    return "\n".join(parts)


def build_episode_fragment_prompt(template: str, episode: dict, fragment: dict,
                                  fragment_index: int, target_duration: int,
                                  previous_result: dict | None = None,
                                  basic_settings: dict | None = None) -> tuple[str, str]:
    """构造逐片段请求：模板作为系统提示词，用户消息携带全片上下文与当前任务。"""
    fragments = episode.get("shots", [])
    episode_no = episode.get("episode", fragment.get("episode", 1))
    settings = basic_settings or {}
    ai_settings = {
        "年代背景": settings.get("era_background", ""),
        "整体风格": settings.get("overall_style", ""),
        "是否仿真人": settings.get("photorealistic", True),
        "拍摄设备": settings.get("camera_equipment", ""),
        "整体色调": settings.get("overall_tone", ""),
        "光影基调": settings.get("lighting_tone", ""),
        "镜头节奏": settings.get("camera_rhythm", ""),
        "解说剧形式": settings.get("narrated_drama", False),
        "特殊要求": settings.get("special_requirements", ""),
        "negative_prompt": settings.get("negative_prompt", ""),
    }
    payload = {
        "任务": "只生成当前片段对应的 Seedance JSON。必须参考基本设定、全片列表和上一片段结果保持连贯；不要提问，不要输出 Markdown。",
        "基本设定": ai_settings,
        "集数": episode_no,
        "剧集标题": episode.get("title", f"第{episode_no}集"),
        "目标总时长_秒": target_duration,
        "当前片段序号": fragment_index + 1,
        "总片段数": len(fragments),
        "当前片段建议时长_秒": _duration_seconds(fragment.get("time")),
        "当前片段": fragment,
        "本集全部已拆片段": fragments,
        "上一片段生成结果": previous_result,
        "输出要求": {
            "格式": "严格 JSON 对象，不要代码块或解释",
            "范围": "仅输出当前片段的结果；可含 meta 和 fragments，但 fragments 只能对应当前片段",
            "时长约束": "每个 clip 不超过15秒，当前结果总时长尽量贴合当前片段建议时长",
        },
    }
    return template.strip(), json.dumps(payload, ensure_ascii=False, indent=2)


def _normalized_field_name(key) -> str:
    """规整模型偶尔返回的【字段】、字段：等 JSON 键名。"""
    return str(key or "").strip().strip("【】[]").rstrip(":：").strip()


def _normalize_shot_fields(shot: dict) -> dict:
    normalized = dict(shot)
    fields = {_normalized_field_name(key): value for key, value in shot.items()}

    aliases = ("画面内容", "画面描述", "视觉内容", "镜头内容", "画面")
    visual_content = next(
        (fields.get(key) for key in aliases if fields.get(key) not in (None, "")),
        None,
    )
    if visual_content in (None, ""):
        visual_parts = [
            fields.get(key) for key in ("画面首帧", "画面中段", "画面尾帧")
            if fields.get(key) not in (None, "")
        ]
        if visual_parts:
            visual_content = " ".join(str(part).strip() for part in visual_parts)
    if visual_content not in (None, ""):
        normalized["画面内容"] = visual_content
    return normalized


def normalize_seedance_result(data: dict) -> dict:
    """统一 Seedance 字段名，并为旧版三段式画面描述补出画面内容。"""
    normalized = dict(data)
    fragments = normalized.get("fragments")
    if not isinstance(fragments, list):
        return normalized

    normalized_fragments = []
    for fragment in fragments:
        if not isinstance(fragment, dict):
            normalized_fragments.append(fragment)
            continue
        normalized_fragment = dict(fragment)
        shots = fragment.get("shots")
        if isinstance(shots, list):
            normalized_fragment["shots"] = [
                _normalize_shot_fields(shot) if isinstance(shot, dict) else shot
                for shot in shots
            ]
        normalized_fragments.append(normalized_fragment)
    normalized["fragments"] = normalized_fragments
    return normalized


def parse_seedance_result(raw: str) -> dict:
    """解析单片段 Seedance JSON，并提供可定位的格式错误。"""
    cleaned = _strip_code_fence(raw)
    if not cleaned:
        raise ValueError("模型未返回任何内容")
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start = max(0, exc.pos - 80)
        end = min(len(cleaned), exc.pos + 80)
        context = cleaned[start:end].replace("\n", " ")
        raise ValueError(
            f"模型返回的 JSON 格式错误：第 {exc.lineno} 行第 {exc.colno} 列，"
            f"{exc.msg}；错误附近：{context}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("Seedance 返回必须是 JSON 对象")
    return normalize_seedance_result(data)


def _duration_seconds(value) -> int:
    text = str(value or "").strip().lower()
    if text.endswith("s"):
        text = text[:-1]
    try:
        return max(0, int(float(text)))
    except (TypeError, ValueError):
        return 0


def _compose_one(ark_client, shot: dict, assets_text: str,
                 prompts_path: str | Path | None) -> dict:
    """对单个片段生成 Seedance 提示词 + 资产匹配。返回片段级结果 dict。"""
    shot_blob = _shot_text(shot)

    # 1) Seedance 视频提示词
    tpl_seed = load_prompt_template("seedance_prompt", prompts_path)
    seed_raw = ark_client.chat(
        tpl_seed.replace("{{SHOT}}", shot_blob),
        system="你是 Seedance 2.0 视频提示词专家，只输出严格 JSON。",
        temperature=0.4,
    )
    seed = json.loads(_strip_code_fence(seed_raw))

    # 2) 资产匹配 + @声明
    tpl_match = load_prompt_template("asset_match", prompts_path)
    match_prompt = (
        tpl_match.replace("{{SHOT}}", shot_blob)
        .replace("{{ASSETS}}", assets_text)
    )
    match_raw = ark_client.chat(
        match_prompt,
        system="你是资产匹配专家，只输出严格 JSON，used_asset_ids 只能取给定清单。",
        temperature=0.2,
    )
    match = json.loads(_strip_code_fence(match_raw))

    used_ids = match.get("used_asset_ids", []) or []
    # 规整为 int 列表
    used_ids = [int(x) for x in used_ids if str(x).isdigit()]

    return {
        "episode": shot.get("episode"),
        "scene": shot.get("scene", ""),
        "seedance": {
            "prompt": seed.get("prompt", ""),
            "camera": seed.get("camera", ""),
            "motion": seed.get("motion", ""),
            "style": seed.get("style", ""),
            "duration_sec": seed.get("duration_sec", 10),
        },
        "used_asset_ids": used_ids,
        "final_prompt": match.get("final_prompt", seed.get("prompt", "")),
    }


def run(cfg: dict, ark_client, project_dir: Path,
        prompts_path: str | Path | None = None) -> dict:
    """执行模块4，读写 shots.json 并生成 seedance_prompts.json。"""
    db_path = asset_db.get_db(project_dir)
    shots_json = project_dir / "shots.json"
    seed_json = project_dir / "seedance_prompts.json"

    if not shots_json.exists():
        raise RuntimeError("请先运行模块3（片段分解）生成 shots.json")

    shots_doc = json.loads(shots_json.read_text(encoding="utf-8"))
    assets_text = asset_db.assets_for_prompt(db_path)

    results = []
    for ep in shots_doc.get("episodes", []):
        for sh in ep.get("shots", []):
            one = _compose_one(ark_client, sh, assets_text, prompts_path)
            results.append(one)

    out = {"prompts": results}
    seed_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 把 used_asset_ids 写回 shots.json（便于前端展示）
    idx = 0
    for ep in shots_doc.get("episodes", []):
        for sh in ep.get("shots", []):
            if idx < len(results):
                sh["used_asset_ids"] = results[idx]["used_asset_ids"]
            idx += 1
    shots_json.write_text(json.dumps(shots_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[模块4] 生成完成：{len(results)} 条 Seedance 提示词 → {seed_json}")
    return out
