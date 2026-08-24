"""剧本文档解析：支持 txt / doc / docx。

统一输出为纯文本字符串，供后续模块分析。
- txt：直接读取
- docx：python-docx 读取段落
- doc：优先尝试 antiword；否则提示用户转换为 docx
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

try:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:  # pragma: no cover
    Document = None
    qn = None
    CT_Tbl = CT_P = Table = Paragraph = None


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _paragraph_text(paragraph) -> str:
    """读取段落可见文字，包含尚未“接受修订”的新增内容。"""
    texts = paragraph._p.xpath(".//w:t/text() | .//w:tab/text() | .//w:br/text()")
    return "".join(texts).strip()


def _iter_docx_blocks(doc):
    """按 DOCX 正文中的原始顺序遍历段落和表格。"""
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def parse_docx(path: Path) -> str:
    if Document is None:
        raise RuntimeError("未安装 python-docx，请执行 pip install python-docx")
    doc = Document(str(path))
    lines = []
    for block in _iter_docx_blocks(doc):
        if isinstance(block, Paragraph):
            text = _paragraph_text(block)
            if text:
                lines.append(text)
            continue
        for row in block.rows:
            cells = []
            for cell in row.cells:
                cell_lines = [
                    _paragraph_text(paragraph)
                    for paragraph in cell.paragraphs
                ]
                cells.append("\n".join(line for line in cell_lines if line))
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def parse_doc(path: Path) -> str:
    """老版 .doc 解析：使用 antiword（需系统安装）。"""
    import shutil
    import subprocess

    if not shutil.which("antiword"):
        raise RuntimeError(
            "解析 .doc 需要 antiword（brew install antiword），"
            "或请先将文件另存为 .docx"
        )
    out = subprocess.run(
        ["antiword", "-m", "utf-8.txt", str(path)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def parse_script(path: str | Path) -> str:
    """根据扩展名自动分发解析。返回剧本纯文本。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return parse_txt(path)
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".doc":
        return parse_doc(path)
    raise ValueError(f"不支持的剧本格式：{suffix}（支持 txt/doc/docx）")


# 集数标题匹配模式。兼容 Markdown 标题、加粗标记和【数字】写法。
_EP_CN_PATTERN = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:\*{1,2})?\s*第\s*[【\[]?\s*'
    r'([一二三四五六七八九十百千零〇两0-9０-９]+)\s*[】\]]?\s*'
    r'[集回话]\s*(.*?)\s*(?:\*{1,2})?\s*$'
)
_EP_LATIN_PATTERNS = [
    re.compile(r'^\s*(?:#{1,6}\s*)?(?:\*{1,2})?\s*EP\s*([0-9]{1,3})\s*(.*?)\s*(?:\*{1,2})?\s*$', re.IGNORECASE),
    re.compile(r'^\s*(?:#{1,6}\s*)?(?:\*{1,2})?\s*Episode\s*([0-9]{1,3})\s*(.*?)\s*(?:\*{1,2})?\s*$', re.IGNORECASE),
]

# 中文数字 → 阿拉伯数字
_CN_NUM = {
    '零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000,
}


def _cn_to_int(s: str) -> int:
    """简单中文数字字符串 → int（支持到千，纯文本，无单位）。"""
    if not s:
        return 0
    # 全角→半角
    s = s.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    if s.isdigit():
        return int(s)
    total, cur = 0, 0
    for ch in s:
        v = _CN_NUM.get(ch)
        if v is None:
            continue
        if v >= 10:
            cur = max(cur, 1) * v
            total += cur
            cur = 0
        else:
            cur = v
    return total + cur


def extract_title(text: str) -> str:
    """从剧本中识别《》包裹的剧名。"""
    m = re.search(r'《([^》]+)》', text or '')
    return m.group(1).strip() if m else ''


def split_episodes(text: str) -> list[dict]:
    """按集数标题行拆分剧本。返回 [{index, title, content}]。

    识别模式：
      - 第 X 集 / 第 X 回 / 第 X 话（中文数字或阿拉伯数字）
      - EP01 / EP 1 / Episode 1
    未命中时整段作为单集 index=1。
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    # 找出所有集数标题行的位置
    boundaries: list[tuple[int, int, str]] = []  # (行号, 集号, 完整标题)
    for i, line in enumerate(lines):
        m = _EP_CN_PATTERN.match(line)
        if m:
            idx = _cn_to_int(m.group(1))
            remainder = m.group(2).strip()
            title = f"第{idx}集" + (f" {remainder}" if remainder else "")
            boundaries.append((i, idx, title))
            continue
        for pat in _EP_LATIN_PATTERNS:
            m = pat.match(line)
            if not m:
                continue
            idx = int(m.group(1))
            remainder = m.group(2).strip()
            title = f"EP{idx:02d}" + (f" {remainder}" if remainder else "")
            boundaries.append((i, idx, title))
            break

    if not boundaries:
        # 没有集数标记：整段作为第1集
        return [{"index": 1, "title": "第1集", "content": text.strip()}]

    # 集号去重（按出现顺序重排）
    seen = set()
    cleaned = []
    counter = 0
    for line_no, raw_idx, title in boundaries:
        if raw_idx in seen:
            continue
        seen.add(raw_idx)
        counter += 1
        cleaned.append((line_no, counter, title))

    # 切片；同一集连续出现多种标题写法时，不把别名标题混入正文。
    boundary_lines = {line_no for line_no, _, _ in boundaries}
    episodes = []
    for k, (line_no, idx, title) in enumerate(cleaned):
        end = cleaned[k + 1][0] if k + 1 < len(cleaned) else len(lines)
        content = "\n".join(
            line for pos, line in enumerate(lines[line_no + 1:end], start=line_no + 1)
            if pos not in boundary_lines
        ).strip()
        if not content:
            continue
        episodes.append({"index": idx, "title": title, "content": content})

    # 集标题前的前言部分（0 到第一个集标题）
    if cleaned and cleaned[0][0] > 0:
        prelude = "\n".join(lines[:cleaned[0][0]]).strip()
        if prelude:
            episodes.insert(0, {"index": 0, "title": "前言", "content": prelude})

    return episodes


def load_first_script(input_dir: str | Path = "input") -> tuple[str, Path]:
    """读取 input 目录下第一个剧本文件，返回 (文本, 路径)。"""
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"剧本目录不存在：{input_dir}")
    for ext in ("*.txt", "*.docx", "*.doc"):
        files = sorted(input_dir.glob(ext))
        if files:
            return parse_script(files[0]), files[0]
    raise FileNotFoundError(f"{input_dir} 下未找到 txt/doc/docx 剧本文件")
