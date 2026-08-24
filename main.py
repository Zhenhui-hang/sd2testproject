"""CLI 入口：串联 剧本解析 → 分析 → 生图 → 拆分 → 提示词 → 报告。

按"剧"隔离存储：projects/<剧名>/ 下保存 script、assets.db、assets/ 图片、
shots.json、seedance_prompts.json。

用法：
  python main.py --project 剧名 --input input/script.txt
  python main.py --project 剧名 --step analyze        # 单步
  python main.py --project 剧名 --step all

说明：分析/拆分/提示词/生图均为真实 API 调用，会产生费用。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import yaml
from src import doc_parser, db as asset_db
from src import analyzer, image_gen, splitter, prompt_composer
from src.ark_client import ArkClient


def load_cfg() -> dict:
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        raise RuntimeError("config.yaml 不存在")
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def get_project_dir(project: str) -> Path:
    p = ROOT / "projects" / project
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_script(project_dir: Path, input_path: str | None) -> str:
    """返回剧本纯文本：优先 input_path，否则 project_dir/script.txt。"""
    if input_path:
        text = doc_parser.parse_script(Path(input_path))
        (project_dir / "script.txt").write_text(text, encoding="utf-8")
        return text
    sp = project_dir / "script.txt"
    if sp.exists():
        return sp.read_text(encoding="utf-8")
    raise RuntimeError("未提供剧本：用 --input 指定或先上传剧本")


def step_analyze(ark, cfg, script, project_dir):
    return analyzer.run(cfg, ark, script, project_dir)


def step_image(ark, cfg, project_dir):
    return image_gen.run(cfg, ark, project_dir)


def step_split(ark, cfg, script, project_dir):
    return splitter.run(cfg, ark, script, project_dir)


def step_compose(ark, cfg, project_dir):
    return prompt_composer.run(cfg, ark, project_dir)


def step_report(cfg, project_dir) -> dict:
    """汇总：资产数、已生图数、片段数、提示词数。"""
    import json
    db_path = asset_db.get_db(project_dir)
    assets = asset_db.get_all(db_path)
    shots_json = project_dir / "shots.json"
    seed_json = project_dir / "seedance_prompts.json"

    shots_count = 0
    if shots_json.exists():
        shots_count = sum(
            len(e["shots"])
            for e in json.loads(shots_json.read_text(encoding="utf-8")).get("episodes", [])
        )

    prompts_count = 0
    if seed_json.exists():
        prompts_count = len(json.loads(seed_json.read_text(encoding="utf-8")).get("prompts", []))

    report = {
        "assets": len(assets),
        "images": sum(1 for a in assets if a.get("image_path")),
        "shots": shots_count,
        "prompts": prompts_count,
    }
    (project_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[报告] {report}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="剧名（projects/<剧>/）")
    ap.add_argument("--input", default=None, help="剧本文件路径 (txt/doc/docx)")
    ap.add_argument("--step", default="all",
                    choices=["all", "analyze", "image", "split", "compose", "report"])
    args = ap.parse_args()

    cfg = load_cfg()
    ark = ArkClient(
        api_key=cfg["ark"]["api_key"],
        pro_model=cfg["ark"].get("pro_model"),
        seedream_model=cfg["ark"].get("seedream_model"),
        endpoint=cfg["ark"].get("endpoint"),
    )
    project_dir = get_project_dir(args.project)

    # 解析剧本（analyze/split 需要文本）
    script = ""
    if args.step in ("all", "analyze", "split"):
        script = resolve_script(project_dir, args.input)

    steps = {
        "analyze": lambda: step_analyze(ark, cfg, script, project_dir),
        "image": lambda: step_image(ark, cfg, project_dir),
        "split": lambda: step_split(ark, cfg, script, project_dir),
        "compose": lambda: step_compose(ark, cfg, project_dir),
        "report": lambda: step_report(cfg, project_dir),
    }

    if args.step == "all":
        order = ["analyze", "image", "split", "compose", "report"]
        for s in order:
            print(f"\n===== 步骤：{s} =====")
            steps[s]()
    else:
        steps[args.step]()


if __name__ == "__main__":
    main()
