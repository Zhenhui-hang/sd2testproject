"""模块1：剧集信息分析。

输入：剧本纯文本
流程：
  1. 读取 prompts.yaml 的 asset_analysis 模板（{{SCRIPT}} 替换为剧本文本）
  2. 调用 doubao-seed-evolving-latest-version 抽取人物/道具/场景 + 各自生图提示词
  3. 结果写入该剧的 SQLite 资产库（projects/<剧>/assets.db）
  4. 同时保留 assets.json 快照（便于排查）

同一人物按不同状态/服装拆分为独立资产（key = 姓名-状态）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from src import db as asset_db


# ---------- 提示词模板 ----------
def load_prompt_template(key: str, prompts_path: str | Path | None = None) -> str:
    """读取 prompts.yaml 中指定 key 的模板文本（去尾随空白）。"""
    if prompts_path is None:
        prompts_path = Path(__file__).resolve().parent.parent / "prompts.yaml"
    data = yaml.safe_load(Path(prompts_path).read_text(encoding="utf-8")) or {}
    return (data.get(key) or "").strip()


def _character_look_name(character_name: str, look_name: str) -> str:
    """人物造型统一使用“人物名-造型名”，并避免重复人物名前缀。"""
    character_name = str(character_name or "").strip()
    look_name = str(look_name or "").strip()
    if not character_name or not look_name:
        return look_name
    if look_name == character_name or look_name.startswith(f"{character_name}-"):
        return look_name
    return f"{character_name}-{look_name.lstrip('-')}"


def _sanitize_key(name: str, state: str) -> str:
    """生成资产唯一键；子项已带父项名前缀时不重复拼接。"""
    key = name
    if state:
        key = state if state == name or state.startswith(f"{name}-") else f"{name}-{state}"
    key = re.sub(r"[^\w一-龥-]", "", key)
    return key


def _strip_code_fence(text: str) -> str:
    """去除可能的 ```json ... ``` 包裹。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _normalize_episodes(value) -> list:
    """把模型返回的出场集数归一为去重列表。"""
    if value is None:
        return []
    if not isinstance(value, list):
        value = re.split(r"[、,，/\s]+", str(value).strip())
    result = []
    for episode in value:
        if episode in (None, ""):
            continue
        text = str(episode).strip()
        match = re.search(r"\d+", text)
        normalized = int(match.group()) if match else text
        if normalized not in result:
            result.append(normalized)
    return result


def _parse_sub_item(sub, base_prompt: str, base_episodes: list | None = None) -> tuple[str, str, list, str]:
    """兼容标准子项和旧版 {造型名:提示词} 子项，并保留集数与占位描述。"""
    if not isinstance(sub, dict):
        return str(sub).strip(), base_prompt, list(base_episodes or []), ""
    sub_name = sub.get("name") or sub.get("state") or ""
    sub_prompt = sub.get("prompt", "") or ""
    sub_description = sub.get("description", "") or ""
    sub_episodes = _normalize_episodes(sub.get("episodes", sub.get("episode")))
    if not sub_name and len(sub) == 1:
        sub_name, sub_prompt = next(iter(sub.items()))
    return (
        str(sub_name).strip(),
        str(sub_prompt or base_prompt).strip(),
        sub_episodes or list(base_episodes or []),
        str(sub_description).strip(),
    )


def _expand_item(item: dict) -> list[dict]:
    """把一个 AI 返回的资产项展开为主项 + 子项占位。"""
    name = (item.get("name") or "").strip()
    if not name:
        return []
    base_prompt = str(item.get("prompt", "") or "").strip()
    episodes = _normalize_episodes(item.get("episodes", item.get("episode")))
    aliases = [str(value).strip() for value in (item.get("aliases") or []) if str(value).strip()]
    out = [{"name": name, "state": "", "prompt": base_prompt, "episodes": [], "aliases": aliases,
            "profile": item.get("profile", {}) or {}}]

    for sub in item.get("styling", []) or []:
        sub_name, sub_prompt, sub_episodes, sub_description = _parse_sub_item(sub, base_prompt)
        if sub_name:
            sub_name = _character_look_name(name, sub_name)
            out.append({
                "name": name,
                "state": sub_name,
                "prompt": sub_prompt,
                "description": sub_description,
                "profile": {"description": sub_description} if sub_description else {},
                "episodes": sub_episodes,
                "aliases": [],
            })

    for sub in item.get("extra_characters", []) or []:
        sub_name, _, sub_episodes, sub_description = _parse_sub_item(sub, "")
        if not sub_name:
            continue
        count = sub.get("count", 1) if isinstance(sub, dict) else 1
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 1
        multiple = isinstance(sub, dict) and (bool(sub.get("multiple")) or count > 1)
        count = max(3, count) if multiple else 1
        names = [f"{sub_name}{chr(65 + index)}" for index in range(min(count, 26))] if multiple else [sub_name]
        for extra_name in names:
            extra_profile = dict(sub.get("profile", {}) or {}) if isinstance(sub, dict) else {}
            extra_profile.update({"asset_role": "extra_character", "description": sub_description})
            out.append({
                "name": name,
                "state": extra_name,
                "prompt": "",
                "description": sub_description,
                "profile": extra_profile,
                "episodes": sub_episodes,
                "aliases": [sub_name] if multiple else [],
            })

    for sub in item.get("scene_type", []) or []:
        sub_name, sub_prompt, sub_episodes, sub_description = _parse_sub_item(sub, base_prompt, episodes)
        if sub_name:
            out.append({
                "name": name,
                "state": sub_name,
                "prompt": sub_prompt,
                "description": sub_description,
                "profile": {"description": sub_description} if sub_description else {},
                "episodes": sub_episodes,
                "aliases": [],
            })

    return out


def build_global_character_index_prompt(script: str) -> str:
    """通读完整剧本，只输出精简人物索引，避免一次生成全部详情而截断。"""
    return f"""你是专业影视角色统筹。请通读完整剧本，从全剧范围识别并统一所有需要建立视觉资产的人物。此步骤只输出精简索引，不写人物小传和生图提示词。

【完整剧本】
{script}

只输出合法 JSON 数组，不要 Markdown、解释或前后缀：
[{{"name":"统一人物名","type":"character","aliases":["别名/称谓"],"episodes":[],"profile":{{"role":"主角或配角","identity":"一句话身份"}},"prompt":"","styling":[],"extra_characters":[],"scene_type":[]}}]

规则：
1. 结合完整剧本统一姓名、别名和身份，不得把同一人物的不同阶段拆成多个人。
2. 所有人物母项（包括“其他角色”）的 episodes 必须严格为空数组 []；人物母项只用于身份统一，不记录出场集数。
3. 有姓名、持续剧情身份或需要多套造型的主角与配角分别建人物；纯路人、百姓、群众、村民、士兵、侍从、宾客等不单独建立人物母档案，统一只建立一个名为“其他角色”的人物母项。
4. “其他角色”的 profile.role 固定为“群演集合”；此索引阶段不要展开具体路人。
5. 每人只写一句话身份，prompt 必须为空，严格控制输出长度。
6. 主角名称只保留一个【主角】前缀；输出必须可被 json.loads 直接解析。"""


def build_character_detail_prompt(script: str, characters: list[dict]) -> str:
    """基于完整剧本按小批次补全人物母档案，控制单次输出长度。"""
    targets = [
        {key: item.get(key) for key in ("name", "aliases", "episodes", "profile")}
        for item in characters
    ]
    return f"""你是专业影视角色资产分析师。请通读完整剧本，为指定人物建立图片占位。不得新增人物母项，不得生成图片提示词，不得创作、改写或猜测项目美术风格。

【本批指定人物】
{json.dumps(targets, ensure_ascii=False, indent=2)}

【完整剧本】
{script}

普通人物输出格式：
[{{"name":"与指定人物完全一致","type":"character","aliases":["别名/称谓"],"episodes":[],"profile":{{"role":"主角或配角","gender":"","visual_age":"","identity":"","occupation":"","relationships":[""],"personality":"核心性格及全剧变化","appearance":"稳定身份与外形识别信息，不含具体着装"}},"prompt":"","styling":[{{"name":"人物名-可区分的着装或状态名称","episodes":[1,2],"description":"服装、鞋、配饰、发型、妆容及身体状态；注明适用剧情阶段","prompt":""}}],"extra_characters":[],"scene_type":[]}}]

“其他角色”固定输出格式：
[{{"name":"其他角色","type":"character","aliases":[],"episodes":[],"profile":{{"role":"群演集合","identity":"无名路人角色容器"}},"prompt":"","styling":[],"extra_characters":[{{"name":"百姓","multiple":true,"episodes":[1,2],"description":"该类路人的身份、性别、年龄、外形与服装区别","profile":{{"identity":"百姓路人"}}}}],"scene_type":[]}}]

规则：
1. 返回数量、name 与本批指定人物完全一致。普通人物结合全剧补全身份、关系、性格及变化。
2. 普通人物主项 episodes 必须为空数组；只有 styling.episodes 记录该造型实际出现的全部集数。
3. 每个 styling.name 必须使用“人物名-造型名”完整格式，例如人物“主角”的破衣服造型必须写为“主角-破衣服”，不得只写“破衣服”。
4. 普通人物 profile.appearance 记录稳定身份识别信息，不要混入具体服装；扫描全文找全主要着装和明显视觉状态，相同着装跨集出现时合并。
4. 如果指定人物是“其他角色”，不要生成主人物形象和 styling；把全剧所有无名路人、百姓、群众、村民、士兵、侍从、宾客等写入 extra_characters。
5. extra_characters 每项代表一种可独立上传、直接用于视频参考的路人形象，并准确记录 episodes。若文本表示复数或群体，multiple 必须为 true，系统将至少创建 A、B、C 三个不同子角色；单一路人 multiple 为 false。
6. 同类群体跨集出现时合并并汇总实际集数；description 必须给出可区分的具体人物外形与服装，不要只写“若干群众”。
7. 主项、styling 和 extra_characters 的 prompt 必须为空字符串；所有人物图片由用户后续上传。
8. 只输出合法 JSON 数组，不要 Markdown、解释或前后缀，必须可被 json.loads 直接解析。"""


def build_global_character_prompt(script: str) -> str:
    """兼容旧调用：返回精简全局人物索引请求。"""
    return build_global_character_index_prompt(script)


def build_asset_prompt(template: str, script: str, character_profiles: list[dict] | None = None) -> str:
    """构造每五集局部资产请求；人物只提取造型，母档案来自全局识别。"""
    prompt = template.replace("{{SCRIPT}}", script)
    profiles = json.dumps(character_profiles or [], ensure_ascii=False, indent=2)
    contract = f"""

【全局人物母档案——本批必须遵守】
{profiles}

【最终输出协议——优先级高于上文中任何冲突要求】
当前阶段按本批剧本建立局部资产占位。人物身份、姓名和别名必须服从全局人物母档案；不要重新创建人物母档案，也不要为人物母资产生成提示词。

只输出一个合法 JSON 数组，不要 Markdown、解释、前后缀：
{{"name":"资产唯一名称","type":"character|scene|prop","aliases":["别名"],"episodes":[1,2],"prompt":"","styling":[{{"name":"人物名-造型名称","episodes":[1,2],"prompt":""}}],"extra_characters":[{{"name":"百姓","multiple":true,"episodes":[1,2],"description":"独立路人外形"}}],"scene_type":[{{"name":"固定子空间名称","episodes":[1,2],"prompt":""}}]}}
规则：
1. 普通 character 只用于承载 styling；styling 识别本批明确出现且影响视觉连续性的造型状态，styling.name 必须为“人物名-造型名”，例如“主角-破衣服”。
2. “其他角色”不得使用 styling，只把本批出现的无名路人和群体写入 extra_characters；复数群体 multiple=true，系统至少展开 A、B、C 三个独立角色。
3. styling 和 extra_characters 的 episodes 必须填写实际出现集数，绝不能继承人物所有出场集数；普通表情变化不单独建项。
4. scene_type 只列固定子空间，不按白天、夜晚、天气拆分；prop 的两个人物子数组为空。
5. aliases 保存同一资产的称谓和简称，不得拆成新资产；人物名称必须使用全局母档案中的统一名称。
6. 剧情关键、反复出现、具有特殊造型或文字要求的道具必须占位；普通背景杂物不提取。
7. prompt 及所有子项 prompt 必须为空字符串，图片提示词将在后续按类型小批次生成。
8. 输出前检查 JSON 可被 json.loads 直接解析。
"""
    return prompt + contract


def character_profiles_from_assets(assets: dict) -> list[dict]:
    """提取可安全传给局部解析的全局人物母档案。"""
    return [
        {key: item.get(key) for key in ("name", "aliases", "episodes", "profile", "prompt")}
        for item in assets.get("characters", []) if not item.get("state")
    ]


def merge_assets(base: dict | None, incoming: dict | None) -> dict:
    """按类别、名称和状态跨批去重；合并集数并保留信息更完整的提示词。"""
    merged = {"characters": [], "scenes": [], "props": []}
    index = {}

    def identity(category: str, item: dict) -> tuple[str, str, str]:
        name = re.sub(r"^【[^】]+】", "", str(item.get("name", ""))).strip()
        name = re.sub(r"[\s·・]+", "", name).lower()
        state = re.sub(r"[\s·・]+", "", str(item.get("state", ""))).lower()
        return category, name, state

    for source in (base or {}, incoming or {}):
        for category in merged:
            for raw_item in source.get(category, []) or []:
                item = dict(raw_item)
                if not item.get("name"):
                    continue
                item["state"] = item.get("state", "") or ""
                item["prompt"] = item.get("prompt", "") or ""
                item["episodes"] = _normalize_episodes(item.get("episodes"))
                if category == "characters" and not item["state"]:
                    item["episodes"] = []
                item["aliases"] = sorted({str(value).strip() for value in item.get("aliases", []) if str(value).strip()})
                item["profile"] = item.get("profile", {}) or {}
                item["description"] = str(item.get("description", "") or "").strip()
                item["key"] = _sanitize_key(item["name"], item["state"])
                marker = identity(category, item)
                existing = index.get(marker)
                if existing is None:
                    merged[category].append(item)
                    index[marker] = item
                    for alias in item["aliases"]:
                        alias_item = dict(item, name=alias)
                        index.setdefault(identity(category, alias_item), item)
                    continue
                existing["episodes"] = _normalize_episodes(
                    existing.get("episodes", []) + item.get("episodes", [])
                )
                existing["aliases"] = sorted(set(existing.get("aliases", [])) | set(item.get("aliases", [])))
                if item.get("name") != existing.get("name"):
                    existing["aliases"] = sorted(set(existing["aliases"]) | {item["name"]})
                if len(item["prompt"]) > len(existing.get("prompt", "")):
                    existing["prompt"] = item["prompt"]
                if len(item["description"]) > len(existing.get("description", "")):
                    existing["description"] = item["description"]
                if item.get("profile") and not existing.get("profile"):
                    existing["profile"] = item["profile"]
                if str(item["name"]).startswith("【主角】"):
                    existing["name"] = item["name"]
                    existing["key"] = _sanitize_key(existing["name"], existing.get("state", ""))
    return merged


def parse_analysis_text(raw: str) -> dict:
    """解析 AI 返回的 JSON 文本，返回标准 assets dict（已按 type 分发并展开父子）。

    兼容两种格式：
      1) 单数组 [{name,type,prompt,styling,scene_type}]（提示词约定格式）
      2) 旧字典 {characters,props,scenes}

    容错：当模型输出被截断或带噪声（多余字符/缺逗号）导致整体 JSON 解析失败时，
    退化为「逐对象正则提取」，尽量救回能解析的资产项。
    """
    text = _strip_code_fence(raw)

    # 优先整体解析
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        data = _rescue_objects(text)
        if not data and text.strip() not in ("[]", "{}"):
            raise ValueError(f"模型未返回可解析的资产 JSON：{exc}") from exc

    groups = {"characters": [], "scenes": [], "props": []}

    if isinstance(data, list):
        for it in data:
            if not isinstance(it, dict):
                continue
            t = (it.get("type") or "").strip().lower()
            cat = {"character": "characters", "scene": "scenes",
                   "prop": "props", "props": "props"}.get(t)
            if not cat:
                # 无 type 时按有无 styling/scene_type 猜测，默认 prop
                cat = "props"
            for sub in _expand_item(it):
                sub["key"] = _sanitize_key(sub["name"], sub["state"])
                groups[cat].append(sub)
    elif isinstance(data, dict):
        for cat in ("characters", "props", "scenes"):
            for it in data.get(cat, []) or []:
                if not isinstance(it, dict):
                    continue
                it["key"] = _sanitize_key(it.get("name", ""), it.get("state", ""))
                groups[cat].append({
                    "name": it.get("name", ""),
                    "state": it.get("state", ""),
                    "prompt": it.get("prompt", "") or it.get("image_prompt", ""),
                    "episodes": _normalize_episodes(it.get("episodes")),
                    "aliases": it.get("aliases", []) or [],
                    "profile": it.get("profile", {}) or {},
                    "description": it.get("description", "") or "",
                    "key": it["key"],
                })
    return groups


def _rescue_objects(text: str):
    """从可能截断/带噪声的文本中尽力提取 JSON 对象列表。

    策略：
      1) 去掉 ```...``` 代码围栏与多余前缀；
      2) 用正则贪婪匹配每个 {...} 对象（支持嵌套，因为资产项里有子对象）；
      3) 逐个 json.loads，成功即保留，失败尝试补 } 再试一次；
      4) 返回提取到的对象列表（至少有一个有效项）。
    """
    text = _strip_code_fence(text).strip()
    objs = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    frag = text[start:i + 1]
                    objs.append(frag)
                    start = None
    # 末尾若仍欠闭合（截断），补 } 再试
    if start is not None and depth > 0:
        frag = text[start:] + "}" * depth
        objs.append(frag)

    items = []
    for frag in objs:
        try:
            obj = json.loads(frag)
            if isinstance(obj, dict):
                items.append(obj)
        except (json.JSONDecodeError, ValueError):
            # 尝试截断修复：截到最后一个完整 "key":value 之后
            try:
                fixed = _patch_trailing(frag)
                obj = json.loads(fixed)
                if isinstance(obj, dict):
                    items.append(obj)
            except (json.JSONDecodeError, ValueError):
                continue
    # 若文本里其实是 {characters,scenes,props} 字典结构被截断，尝试整体补 }
    if not items:
        try:
            fixed = _patch_trailing(text)
            obj = json.loads(fixed)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
    return items


def _patch_trailing(frag: str) -> str:
    """去掉截断字符串末尾不完整的 "key": 片段，并补齐 [] / } 闭合。"""
    # 去掉形如 ... "scene_type":[ 或 ... "prompt":"xxx  这种不完整尾巴
    frag = re.sub(r',\s*"[^"]*"\s*:\s*\[?\s*$', '', frag)
    frag = re.sub(r',\s*"[^"]*"\s*:\s*"[^"]*$', '', frag)
    # 补齐未闭合的数组/对象
    depth = 0
    in_str = False
    esc = False
    for ch in frag:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
    # 先补 ] 再补 }
    frag = frag.rstrip()
    if not frag.endswith("}"):
        frag += "}"
    if depth > 0:
        frag += "]" * depth
    return frag


def analyze_script(ark_client, script_text: str, prompts_path: str | Path | None = None) -> dict:
    """调用模型提取资产占位并返回结构化资产。"""
    template = load_prompt_template("asset_analysis", prompts_path)
    if not template:
        raise RuntimeError("prompts.yaml 缺少 asset_analysis 模板")
    prompt = build_asset_prompt(template, script_text)
    raw = ark_client.chat(prompt, system="你是专业影视剧资产分析师，只输出严格 JSON。", temperature=0.2)
    return parse_analysis_text(raw)


ASSET_PROMPT_FIELDS = {
    "character": "视觉年龄、脸型、五官比例、眉眼、鼻型、唇形、肤色、发际线、基础发型、体型、可视觉化气质、身份和固定识别特征",
    "character_look": "绑定人物、实际出现集数、季节与场合、上装下装、鞋、配饰、发型妆容、材质新旧、受伤污渍等剧情状态、身份经济状况、人物一致性",
    "scene": "年代地域、空间结构、门窗位置、家具布局、主色调、材质新旧、生活痕迹、固定标志物、标准中性光照、可拍摄方向",
    "prop": "类别尺寸、形状、材质、颜色、年代磨损、准确文字、使用方式、与人物比例、正侧参考视角",
}


def build_visual_style_analysis_prompt(settings: dict) -> str:
    """将项目基础设定分析为唯一、可复用的视觉风格规范。"""
    payload = json.dumps(settings, ensure_ascii=False, indent=2)
    return f"""你是影视项目视觉总监。请把项目基础设定分析成一份唯一、稳定、可直接复用的视觉风格规范。

项目基础设定：
{payload}

要求：
1. 风格规范是项目级母版，不描述任何具体人物、服装、场景、道具或剧情动作。
2. 将媒介形态、真实度、造型语言、线条与材质、色彩系统、光影系统、时代质感、镜头观感统一成明确规则。
3. 必须消除互相冲突的风格词；如果设定为国漫且非仿真人，不得出现真人摄影、写实皮肤、照片级等表述。
4. unified_prompt 必须是一段可原样追加到每个最终图片提示词中的中文风格块，信息完整且无需按资产改写。
5. negative_prompt 只写项目级风格禁忌，不写具体资产错误。
6. 只输出合法 JSON 对象，不要 Markdown：
{{"style_name":"简短风格名","summary":"风格说明","unified_prompt":"统一风格提示词","negative_prompt":"统一风格反向提示词","rules":["规则1","规则2"]}}"""


def parse_visual_style_analysis(raw: str) -> dict:
    data = json.loads(_strip_code_fence(raw))
    if not isinstance(data, dict) or not str(data.get("unified_prompt", "")).strip():
        raise ValueError("风格分析结果缺少 unified_prompt")
    return {
        "style_name": str(data.get("style_name", "统一视觉风格")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "unified_prompt": str(data.get("unified_prompt", "")).strip(),
        "negative_prompt": str(data.get("negative_prompt", "")).strip(),
        "rules": [str(item).strip() for item in (data.get("rules") or []) if str(item).strip()],
    }


def apply_unified_visual_style(prompt: str, negative_prompt: str, visual_style: dict) -> tuple[str, str]:
    """把同一份项目风格母版原样注入最终提示词。"""
    style_prompt = str(visual_style.get("unified_prompt", "")).strip()
    style_negative = str(visual_style.get("negative_prompt", "")).strip()
    content_prompt = prompt.split("【资产内容】", 1)[-1].strip() if "【资产内容】" in prompt else prompt.strip()
    content_negative = negative_prompt
    if style_negative and content_negative.startswith(style_negative):
        content_negative = content_negative[len(style_negative):].lstrip("； ")
    final_prompt = f"【项目统一视觉风格】\n{style_prompt}\n\n【资产内容】\n{content_prompt}" if style_prompt else content_prompt
    negatives = [part for part in (style_negative, content_negative.strip()) if part]
    return final_prompt, "；".join(negatives)


def apply_visual_style_to_assets(assets: dict, visual_style: dict) -> dict:
    """在资产落库前统一完成风格母版注入，保证直接生图也使用同一风格。"""
    for group in ("characters", "scenes", "props"):
        for item in assets.get(group, []):
            prompt = str(item.get("prompt", "")).strip()
            if prompt:
                item["prompt"], item["negative_prompt"] = apply_unified_visual_style(
                    prompt, str(item.get("negative_prompt", "")), visual_style,
                )
    return assets


def build_image_prompt_batch(asset_type: str, assets: list[dict], script_context: str) -> str:
    """构造资产内容提示词请求；项目风格在模型返回后统一注入。"""
    fields = ASSET_PROMPT_FIELDS[asset_type]
    payload = [{
        "id": item["id"],
        "name": item.get("name", ""),
        "state": item.get("state", ""),
        "aliases": item.get("aliases", []),
        "episodes": item.get("episodes", []),
        "category": item.get("category", ""),
        "parent_id": item.get("parent_id"),
        "parent_name": item.get("parent_name", ""),
        "parent_prompt": item.get("parent_prompt", ""),
        "parent_profile": item.get("parent_profile", {}),
        "profile": item.get("profile", {}),
        "parent_has_default_image": bool(item.get("parent_image_path")),
    } for item in assets]
    return f"""你是影视资产内容设计提示词专家。只描述以下资产自身的视觉内容，不分析片段，不生成视频提示词，也不得创作、改写或猜测项目美术风格。
资产类型：{asset_type}
本批资产：{json.dumps(payload, ensure_ascii=False)}
相关剧本证据：\n{script_context}

每项必须覆盖：{fields}。
要求：
1. 严格依据剧本；剧本未明确但生图必需的细节可做保守补全，不得改变人物关系和剧情事实。
2. character 只生成身份基准正脸提示词：高清正面头肩像或胸像、五官无遮挡、均匀光照、简洁背景；不得混入临时服装、帽子、受伤或污渍。
3. character_look 必须输出同一张角色设定板中的 2～3 视图：正面全身、侧面或四分之三全身、高清正脸特写；所有视图是同一人物、同一套造型，不得出现多人、重复肢体或造型混杂，并要求以父人物正脸参考图锁定脸型五官。
4. 人物造型必须保持所属人物一致；场景子空间必须继承父场景的空间结构与美术风格。
5. 场景使用中性光照，不把白天、夜晚、天气写成独立资产；道具上的文字必须逐字准确。
6. 使用具体可执行的中文视觉描述，禁止空泛质量词；每条 prompt 信息完整。
7. prompt 和 negative_prompt 只能描述资产内容，不得包含国漫、写实、摄影、渲染、画风、色调、光影基调等项目级风格词。
8. 只输出合法 JSON 数组，不要 Markdown：
[{{"id":1,"prompt":"完整中文图片提示词","negative_prompt":"需要避免的错误"}}]
9. 返回数量和 id 必须与输入完全一致。"""


def generate_image_prompt_batch(ark_client, asset_type: str, assets: list[dict], script_context: str) -> list[dict]:
    """按类型生成资产内容提示词，尚不包含项目统一风格。"""
    if asset_type not in ASSET_PROMPT_FIELDS:
        raise ValueError(f"不支持的资产提示词类型：{asset_type}")
    if not assets or len(assets) > 5:
        raise ValueError("每批必须包含 1～5 个资产")
    raw = ark_client.chat(
        build_image_prompt_batch(asset_type, assets, script_context),
        system="你只输出严格 JSON，并保证每个输入资产都有且只有一个结果。",
        temperature=0.25,
    )
    parsed = json.loads(_strip_code_fence(raw))
    if not isinstance(parsed, list):
        raise ValueError("模型未返回资产提示词数组")
    expected = {int(item["id"]) for item in assets}
    results = {}
    for item in parsed:
        if not isinstance(item, dict) or "id" not in item:
            continue
        asset_id = int(item["id"])
        prompt = str(item.get("prompt", "")).strip()
        if asset_id in expected and prompt:
            results[asset_id] = {
                "id": asset_id,
                "prompt": prompt,
                "negative_prompt": str(item.get("negative_prompt", "")).strip(),
            }
    missing = expected - set(results)
    if missing:
        raise ValueError(f"以下资产未生成有效图片提示词：{sorted(missing)}")
    return [results[int(item["id"])] for item in assets]


def run(cfg: dict, ark_client, script_text: str, project_dir: Path,
        prompts_path: str | Path | None = None) -> dict:
    """执行模块1：分析剧本并落 SQLite。返回 assets dict（含 key）。"""
    db_path = asset_db.get_db(project_dir)
    assets_json = project_dir / "assets.json"

    if cfg["run"].get("skip_existing") and assets_json.exists():
        print("[模块1] assets.json 已存在，跳过分析")
        assets = json.loads(assets_json.read_text(encoding="utf-8"))
        # 确保 SQLite 也有（首次用快照同步）
        asset_db.insert_assets(db_path, assets)
        return assets

    assets = analyze_script_batched(ark_client, script_text, prompts_path)

    # 写 SQLite（主次关系由 db 层处理）
    asset_db.insert_assets(db_path, assets)
    # 写 JSON 快照
    assets_json.write_text(
        json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    n_c = len(assets.get("characters", []))
    n_p = len(assets.get("props", []))
    n_s = len(assets.get("scenes", []))
    print(f"[模块1] 分析完成：人物 {n_c} / 道具 {n_p} / 场景 {n_s} → {db_path}")
    return assets
