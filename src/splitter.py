"""模块3：剧本分集拆分（AI 版）。

调用 doubao-seed-evolving-latest-version（读 prompts.yaml 的 shot_split 模板），把剧本按"集"和
"场景/镜头"拆分成片段(shot)。每个片段含：
  - episode: 集号
  - scene:   场景标题
  - text:    该片段原始文本
  - lines:   台词行（含说话人）
  - actions: 动作/描写行

结果写 projects/<剧>/shots.json，并保留到内存供 compose 阶段使用。

片段分解由 AI 完成（非规则），因此会产生 LLM 调用费用。
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.analyzer import load_prompt_template, _strip_code_fence


def build_fragment_prompt(template: str, episode_text: str) -> str:
    """把单集原文注入片段拆解模板。"""
    if "{{SCRIPT}}" in template:
        return template.replace("{{SCRIPT}}", episode_text)
    return f"{template.rstrip()}\n\n---\n\n以下为本集剧本原文：\n\n{episode_text}"


def parse_fragment_text(text: str, episode_index: int) -> list[dict]:
    """解析并校验单集片段数组，补充后续流程需要的 episode 字段。"""
    data = json.loads(_strip_code_fence(text))
    if isinstance(data, dict):
        data = data.get("fragments") or data.get("shots") or []
    if not isinstance(data, list):
        raise ValueError("模型返回必须是片段 JSON 数组")

    required = {"id", "scene", "characters", "text", "reason", "time"}
    fragments = []
    total_seconds = 0
    for index, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 个片段不是 JSON 对象")
        missing = required - set(item)
        if missing:
            raise ValueError(f"第 {index} 个片段缺少字段：{', '.join(sorted(missing))}")
        time_text = str(item.get("time", "")).strip()
        if not time_text.endswith("s") or not time_text[:-1].isdigit():
            raise ValueError(f"第 {index} 个片段 time 必须为秒数格式，如 8s")
        total_seconds += int(time_text[:-1])
        fragment = dict(item)
        fragment["episode"] = episode_index
        fragment["characters"] = item.get("characters") or []
        fragments.append(fragment)
    if total_seconds > 180:
        raise ValueError(f"本集片段总时长 {total_seconds}s，超过 180s 上限")
    return fragments


def run(cfg: dict, ark_client, script_text: str, project_dir: Path,
        prompts_path: str | Path | None = None) -> dict:
    """执行模块3，写 shots.json。返回 {"episodes": [...]}。"""
    shots_json = project_dir / "shots.json"

    if cfg["run"].get("skip_existing") and shots_json.exists():
        print("[模块3] shots.json 已存在，跳过分析")
        return json.loads(shots_json.read_text(encoding="utf-8"))

    template = load_prompt_template("shot_split", prompts_path)
    if not template:
        raise RuntimeError("prompts.yaml 缺少 shot_split 模板")
    prompt = template.replace("{{SCRIPT}}", script_text)

    raw = ark_client.chat(prompt, system="你是专业剧本分镜师，只输出严格 JSON。", temperature=0.3)
    raw = _strip_code_fence(raw)
    data = json.loads(raw)

    # 规整：每个 shot 补 episode 字段（与所属 episode 对齐）
    episodes = data.get("episodes", [])
    for ep in episodes:
        no = ep.get("episode", 1)
        for sh in ep.get("shots", []):
            sh["episode"] = no

    result = {"episodes": episodes}
    shots_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(e["shots"]) for e in episodes)
    print(f"[模块3] 拆分完成：{len(episodes)} 集 / {total} 个片段 → {shots_json}")
    return result
