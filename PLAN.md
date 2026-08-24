# Seedanceminiv2 项目规划文档

> 目标：自动根据剧本分析剧集信息，生成人物/道具/场景的生图提示词并连接 Seedream 5.0 pro 生图；
> 再按集拆分剧本为片段，生成 Seedance 提示词，并用 `@` 语法把资产带入提示词中声明。
>
> 当前功能调整、问题修复、交互规则、局域网访问及后续回归事项统一记录在 [`FOLLOW_UP.md`](./FOLLOW_UP.md)。后续修改快剪、剧集切换、Seedance 视频生成或提示词逻辑前，应先核对该文档。

---

## 一、整体数据流

```
剧本文本(txt/doc/docx)
  └─[模块1] 剧集分析 → 人物/道具/场景清单 + 各自生图提示词(落 SQLite + assets.json 快照)
       └─[模块2] 生图(Seedream 5.0 pro) → 资产图片(projects/<剧>/assets/<id>.png)
            └─[模块3] 按集拆分剧本(AI) → 片段 shot(projects/<剧>/shots.json)
                 └─[模块4] 片段 → Seedance 提示词 + @资产声明(projects/<剧>/seedance_prompts.json)
                      └─[模块5] 汇总报告(projects/<剧>/report.json)
```

---

## 二、技术栈选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11 | AI 生态最成熟，火山方舟官方有 Python SDK |
| 后端 | FastAPI + uvicorn | 轻量 API，支撑 Web 前端步骤触发 |
| 前端 | CDN React + Ant Design（零构建单页） | 用户指定 Ant；路线2（前后端解耦，可后期升级为构建方案） |
| 配置 | config.yaml（密钥）/ prompts.yaml（全局提示词模板） | 密钥与提示词分离 |
| 存储 | 按"剧"隔离：`projects/<剧名>/`（script.txt / assets.db / assets/ 图片 / shots.json / seedance_prompts.json） | 每剧独立，资产用 SQLite 轻量表，支持 CRUD + 主次关系 |
| 文档解析 | python-docx(docx) + 内置 txt + antiword(doc 兼容) | 覆盖三种格式 |
| 大模型 | 火山方舟 doubao-seed-2.1-pro（文本分析） | 用户指定 |
| 生图 | 火山方舟 doubao-seedream-5.0-pro | 用户指定 |
| 视频 | Seedance 2.0 API（资产 @ 引用） | 用户指定 |

> 三个模型共用一个 `ARK_API_KEY`，经 ArkClient 统一封装（直接传 model_id，无需 endpoint）。

---

## 三、目录结构

```
Seedanceminiv2/
├── config.yaml              # 火山 ark.api_key + 三模型 model_id
├── prompts.yaml             # 5 类提示词模板（asset_analysis / shot_split / seedance_prompt / asset_match / reserved_5）
├── main.py                  # CLI 入口：--project / --step 串联各模块
├── src/
│   ├── ark_client.py        # 火山方舟统一调用封装（文本 chat / 生图 images.generate）
│   ├── doc_parser.py        # 剧本文档解析（txt/doc/docx）
│   ├── analyzer.py          # [模块1] 剧集分析 → SQLite 资产库
│   ├── image_gen.py         # [模块2] 生图 → projects/<剧>/assets/
│   ├── splitter.py          # [模块3] AI 分集拆分 → shots.json
│   ├── prompt_composer.py   # [模块4] 片段 → Seedance提示词 + @资产声明
│   └── db.py                # SQLite 资产库（按剧隔离，主次关系，CRUD）
├── web/
│   ├── app.py               # FastAPI 后端（剧/剧本/设置/资产/步骤 接口）
│   └── index.py             # 前端单页 HTML（CDN React + AntD）
├── projects/                # 每剧一个目录，独立存储
│   └── <剧名>/
│       ├── script.txt
│       ├── assets.db
│       ├── assets/<id>.png
│       ├── shots.json
│       ├── seedance_prompts.json
│       └── report.json
└── requirements.txt
```

---

## 四、模块职责（细化）

### 模块1 analyzer.py — 剧集信息分析
- 读 `prompts.yaml` 的 `asset_analysis` 模板（替换 `{{SCRIPT}}`），调 Seed 2.1 pro
- 输出结构化 JSON：characters / props / scenes，每项含英文 `image_prompt`
- 同一人物多状态 → 多资产（key = `姓名-状态`）
- 结果写入该剧 SQLite（主次关系由 db 层处理）+ 保留 assets.json 快照

### 模块2 image_gen.py — 资产图片生成
- 从 SQLite 读取全部资产，对未生成图片者调 Seedream 5.0 pro 生图
- 落 `projects/<剧>/assets/<id>.png`，`image_path` 写回 SQLite
- 失败重试 3 次，跳过已生成（幂等）

### 模块3 splitter.py — 剧本分集拆分（AI）
- 读 `prompts.yaml` 的 `shot_split` 模板，调 Seed 2.1 pro 按集/场景拆片段
- 每片段含 scene / text / lines / actions，补 episode 字段
- 落 `projects/<剧>/shots.json`

### 模块4 prompt_composer.py — Seedance 提示词 + @资产声明
- 对每个 shot：① 读 `seedance_prompt` 模板生成视频提示词（prompt/camera/motion/style/duration）
- ② 读 `asset_match` 模板（传入 shot + 资产清单），判定 used_asset_ids，产出带 `@key` 的 final_prompt
- 落 `seedance_prompts.json`，并把 used_asset_ids 写回 shots.json
- 说明：每片段含两段 LLM 调用，真实运行产生费用

### 模块5 汇总报告
- 统计资产数 / 已生图数 / 片段数 / 提示词数，落 report.json（Web 端直接展示）

---

## 五、提示词可配置

前端菜单「设置」编辑 5 类提示词模板，写回 `prompts.yaml`：
1. 资产拆解（asset_analysis）
2. 片段分解（shot_split）
3. Seedance 生成（seedance_prompt）
4. 资产匹配（asset_match）
5. 预留（reserved_5，后续补充）

代码只负责套用模板 + 解析 AI 返回的 JSON，不写死任何提示词内容。

---

## 六、Web 使用流程

1. 启动：`python3 -m web.app --port 8001`
2. 左侧「建剧」→ 输入剧名
3. 「上传剧本」（txt/doc/docx）
4. 「设置」编辑提示词模板（可选）
5. 「分析步骤」Tab 依次触发：①资产拆解 → ②资产生图 → ③片段分解 → ④生成提示词 → ⑤生成报告
   - ①②③④ 为真实 API 调用，会产生费用
6. 查看「资产」「片段」「提示词」Tab 结果；资产支持增删改

---

## 七、实施进度

- [x] 1. 项目骨架（config.yaml / prompts.yaml / main.py / src 包 / web）
- [x] 2. 模块1 analyzer.py（剧集分析，落 SQLite）
- [x] 3. 模块2 image_gen.py（生图）
- [x] 4. 模块3 splitter.py（AI 分集拆分）
- [x] 5. 模块4 prompt_composer.py（Seedance 提示词 + @声明）
- [x] 6. Web 后端 API + 前端单页（建剧/上传/设置/资产CRUD/步骤触发/结果展示）
- [x] 7. db.py SQLite 资产库（按剧隔离，主次关系，CRUD 已验证）

待补充：模块5 HTML 报告页面（当前 report.json 已有数据，可在 Web 展示扩充）。
