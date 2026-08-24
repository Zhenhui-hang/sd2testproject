"""前端单页 HTML（CDN 引入 React + Ant Design，零构建）。

布局：
  - 左侧 Ant Menu：剧管理 / 设置
  - 剧管理：卡片列表（剧名/创建日期/已上传剧本），右上「新建剧」
  - 新建剧弹窗：上传剧本(可选) + 剧名输入框（若剧本含《》自动识别填入）
  - 选中剧后工作区：资产/步骤/片段/提示词 Tabs
  - 设置：编辑 5 类提示词模板（prompts.yaml）
"""
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Seedanceminiv2 · 剧本资产与提示词工作台</title>
  <link rel="stylesheet" href="/static/vendor/antd-reset.css" />
  <script src="/static/vendor/react.production.min.js"></script>
  <script src="/static/vendor/react-dom.production.min.js"></script>
  <script src="/static/vendor/dayjs.min.js"></script>
  <script src="/static/vendor/antd.min.js"></script>
  <script src="/static/vendor/babel.min.js"></script>
  <style>
    body { margin: 0; font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", sans-serif; }
    #root { height: 100vh; }
    .prompt-card { margin-bottom:16px; }
    .asset-img { max-width:120px; max-height:120px; border-radius:6px; border:1px solid #eee; }
    .shot-card { border:1px solid #eee; border-radius:8px; padding:12px; margin-bottom:12px; }
    .proj-card { cursor:pointer; }
    .proj-card.active { border-color:#1677ff; box-shadow:0 0 0 2px rgba(22,119,255,0.2); }
    /* 右侧电梯：默认收起只显手柄，hover 展开 */
    .ep-nav {
      position: fixed; right: 16px; top: 96px; z-index: 20;
      max-height: 76vh; overflow: hidden;
      background: rgba(255,255,255,0.92); border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.12);
      transition: all .2s ease;
      width: 34px;
    }
    .ep-nav:hover { width: 200px; overflow-y: auto; }
    .ep-nav-handle {
      width: 34px; height: 34px; line-height: 12px; padding-top: 4px;
      text-align: center; font-size: 12px; color: #1677ff;
      cursor: pointer; user-select: none; font-weight: 600;
    }
    .ep-nav-body {
      display: none; padding: 6px 8px 10px; white-space: nowrap;
    }
    .ep-nav:hover .ep-nav-body { display: block; }
    .ep-nav-body .ant-anchor { padding-left: 0; }
    .video-studio { height:calc(100vh - 178px); min-height:650px; display:flex; flex-direction:column; background:#f5f6f8; border:1px solid #e7e9ee; border-radius:14px; overflow:hidden; }
    .video-studio-toolbar { min-height:58px; padding:10px 14px; display:flex; align-items:center; justify-content:space-between; gap:12px; background:#fff; border-bottom:1px solid #eceef2; }
    .video-studio-toolbar-left,.video-studio-toolbar-right { display:flex; align-items:center; gap:8px; min-width:0; }
    .video-studio-body { flex:1; min-height:0; display:grid; grid-template-columns:220px minmax(420px,1.6fr) minmax(220px,24%); }
    .video-studio-sidebar { min-width:0; overflow:auto; padding:14px; background:#fafafa; border-right:1px solid #e7e9ee; }
    .video-studio-main { min-width:0; min-height:0; overflow:hidden; background:#fff; display:flex; }
    .video-studio-preview { min-width:0; padding:14px; background:#f7f7f8; border-left:1px solid #e7e9ee; display:flex; flex-direction:column; }
    .studio-section-title { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; font-size:13px; font-weight:600; color:#25262b; }
    .studio-assets { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-bottom:18px; }
    .studio-asset-card { min-width:0; }
    .studio-asset-thumb { aspect-ratio:1; border:1px solid #e1e4e8; border-radius:12px; background:linear-gradient(145deg,#f3f4f6,#e7e9ed); display:flex; align-items:center; justify-content:center; overflow:hidden; color:#a2a8b0; font-size:25px; }
    .studio-asset-thumb img { width:100%; height:100%; object-fit:cover; }
    .studio-asset-name { margin-top:5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; color:#555b64; }
    .studio-fragment-assets { display:flex; flex-direction:column; gap:9px; }
    .studio-fragment-asset { position:relative; display:grid; grid-template-columns:52px minmax(0,1fr); grid-template-areas:'name name' 'thumb info'; align-items:center; gap:6px 8px; padding:8px; border:1px solid #e5e7eb; border-radius:12px; background:#fff; }
    .studio-fragment-asset-name { grid-area:name; min-width:0; padding-right:24px; white-space:normal; overflow-wrap:anywhere; line-height:1.4; font-size:13px; }
    .studio-fragment-asset-upload { grid-area:thumb; display:block; width:52px; height:52px; }
    .studio-fragment-asset-upload .ant-upload { display:block; width:52px; height:52px; }
    .studio-fragment-asset .studio-asset-thumb { position:relative; width:52px; height:52px; aspect-ratio:auto; border-radius:9px; font-size:16px; cursor:pointer; }
    .studio-fragment-asset-upload-mask { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; background:rgba(17,24,39,.66); color:#fff; font-size:12px; font-weight:600; opacity:0; transition:opacity .16s ease; }
    .studio-fragment-asset-upload:hover .studio-fragment-asset-upload-mask { opacity:1; }
    .studio-fragment-asset-info { grid-area:info; min-width:0; display:flex; flex-direction:column; gap:3px; }
    .studio-fragment-asset-delete { position:absolute; top:5px; right:5px; width:26px!important; min-width:26px!important; height:26px; padding:0!important; display:flex!important; align-items:center; justify-content:center; color:#8c8c8c; opacity:0; transition:opacity .16s ease,color .16s ease,background .16s ease; }
    .studio-fragment-asset:hover .studio-fragment-asset-delete { opacity:1; }
    .studio-fragment-asset-delete:hover { color:#ff4d4f!important; background:#fff1f0!important; }
    .studio-fragment-asset-info .ant-tag { margin-inline-end:0; font-size:10px; line-height:18px; }
    .studio-fragment-heading { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
    .studio-fragment-index { width:42px; height:42px; flex:0 0 42px; display:flex; align-items:center; justify-content:center; border-radius:11px; background:#f0f1f3; color:#686d75; font-weight:700; }
    .studio-prompt-box { position:relative; width:100%; height:100%; min-height:0; background:#fff; display:flex; flex-direction:column; }
    .studio-prompt-editor { flex:1; min-height:0; padding:18px 18px 62px; overflow:auto; }
    .studio-prompt-editor .ant-input { width:100%; height:100% !important; min-height:100% !important; padding:0; resize:none; font-family:inherit; line-height:1.75; }
    .studio-prompt-actions { position:absolute; z-index:4; right:18px; bottom:16px; display:flex; align-items:center; justify-content:flex-end; gap:12px; }
    .studio-prompt-progress { position:absolute; z-index:3; left:18px; right:18px; bottom:76px; padding:7px 10px; border-radius:8px; background:rgba(255,255,255,.94); box-shadow:0 3px 12px rgba(17,24,39,.08); display:flex; flex-direction:column; gap:4px; }
    .studio-preview-stage { position:relative; width:100%; max-width:260px; margin:0 auto; aspect-ratio:9 / 16; border-radius:12px; background:linear-gradient(155deg,#f0f1f2,#e7e8ea); display:flex; align-items:center; justify-content:center; overflow:hidden; color:#a2a5aa; }
    .studio-preview-stage video { width:100%; height:100%; object-fit:contain; background:#111318; }
    .studio-preview-restore { position:absolute; right:10px; top:10px; z-index:3; opacity:0; transition:opacity .15s; }
    .studio-preview-stage:hover .studio-preview-restore { opacity:1; }
    .studio-preview-play-hint { position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); width:52px; height:52px; display:flex; align-items:center; justify-content:center; border-radius:50%; color:#fff; background:rgba(0,0,0,.55); font-size:22px; pointer-events:none; backdrop-filter:blur(4px); }
    .studio-preview-empty { text-align:center; }
    .studio-timeline-thumb video { width:100%; height:100%; object-fit:cover; pointer-events:none; }
    .video-studio-timeline { min-height:106px; padding:10px 14px; background:#fff; border-top:1px solid #e7e9ee; }
    .studio-timeline-track { display:flex; gap:10px; overflow-x:auto; padding:2px 1px 8px; }
    .studio-timeline-card { width:112px; flex:0 0 112px; cursor:pointer; }
    .studio-timeline-thumb { position:relative; height:60px; border:2px solid transparent; border-radius:10px; background:linear-gradient(135deg,#f0f1f3,#e2e4e8); display:flex; align-items:center; justify-content:center; color:#989da5; overflow:hidden; }
    .studio-timeline-actions { position:absolute; top:4px; right:4px; display:flex; align-items:center; gap:4px; opacity:0; transition:opacity .15s; }
    .studio-timeline-card:hover .studio-timeline-actions { opacity:1; }
    .studio-timeline-action { width:22px; height:22px; padding:0; display:flex; align-items:center; justify-content:center; border:1px solid rgba(255,255,255,.72); border-radius:6px; background:rgba(24,27,32,.72); color:#fff; cursor:pointer; box-shadow:0 1px 4px rgba(0,0,0,.18); backdrop-filter:blur(3px); }
    .studio-timeline-action:hover { background:rgba(24,27,32,.92); }
    .studio-timeline-action svg { width:13px; height:13px; display:block; }
    .fragment-history-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; max-height:66vh; overflow:auto; }
    .fragment-history-card { overflow:hidden; border-radius:12px; }
    .fragment-history-card video { width:100%; aspect-ratio:9 / 16; max-height:360px; display:block; object-fit:contain; background:#111318; }
    .sequence-preview { display:flex; flex-direction:column; gap:12px; }
    .sequence-preview-stage { height:min(68vh,680px); display:flex; align-items:center; justify-content:center; overflow:hidden; border-radius:12px; background:#0f1115; }
    .sequence-preview-stage video { width:100%; height:100%; display:block; object-fit:contain; background:#0f1115; }
    .sequence-preview-info { display:flex; align-items:center; justify-content:space-between; gap:12px; }
    .studio-timeline-card.active .studio-timeline-thumb { border-color:#722ed1; box-shadow:0 0 0 2px rgba(114,46,209,.12); }
    .studio-timeline-label { margin-top:4px; font-size:11px; text-align:center; color:#646a73; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .studio-timeline-empty { padding:18px 8px; display:flex; align-items:center; gap:6px; color:#9097a3; }
    .studio-prompt-box .ant-input { font-size:14px; }
    .studio-episode-switch { display:flex; align-items:center; gap:8px; min-width:0; padding:6px 10px; border:1px solid transparent; border-radius:8px; cursor:pointer; transition:background .15s,border-color .15s; }
    .studio-episode-switch:hover { background:#f1f2f5; border-color:#e3e6ec; }
    .studio-episode-switch .studio-episode-caret { color:#9097a3; font-size:12px; transition:transform .2s; }
    .studio-episode-switch .studio-episode-caret.open { transform:rotate(180deg); }
    .video-task-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:18px; }
    .video-task-card { overflow:hidden; border-radius:16px; border:1px solid #e6e8ec; box-shadow:0 5px 18px rgba(17,24,39,.05); transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease; }
    .video-task-card:hover { transform:translateY(-2px); border-color:#cfd6e4; box-shadow:0 10px 28px rgba(17,24,39,.10); }
    .video-task-card .ant-card-body { padding:0; }
    .video-task-preview { position:relative; aspect-ratio:16 / 10; overflow:hidden; display:flex; align-items:center; justify-content:center; background:linear-gradient(145deg,#1d2028,#303540); color:#aeb5c1; }
    .video-task-preview video { width:100%; height:100%; object-fit:contain; background:#111318; }
    .video-task-preview-empty { text-align:center; padding:20px; }
    .video-task-preview-status { position:absolute; left:12px; top:12px; z-index:2; }
    .video-task-preview-action { position:absolute!important; right:12px; bottom:12px; z-index:2; border-color:rgba(255,255,255,.45)!important; background:rgba(17,19,24,.72)!important; color:#fff!important; backdrop-filter:blur(6px); }
    .video-task-preview-modal .ant-modal-content { padding:16px; background:#111318; }
    .video-task-preview-modal .ant-modal-close { color:#fff; }
    .video-task-preview-modal video { display:block; width:100%; max-height:78vh; border-radius:8px; background:#000; }
    .video-task-card-body { padding:16px; }
    .video-task-card-title { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin-bottom:12px; }
    .video-task-meta { display:grid; grid-template-columns:1fr 1fr; gap:10px 16px; padding:12px 0; border-top:1px solid #f0f1f3; border-bottom:1px solid #f0f1f3; }
    .video-task-meta-item { min-width:0; }
    .video-task-meta-label { margin-bottom:2px; color:#8a9099; font-size:11px; }
    .video-task-meta-value { color:#343941; font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .video-task-card-footer { display:flex; align-items:center; justify-content:space-between; gap:8px; padding-top:12px; }
    .quick-cut-modal .ant-modal-content { background:#16181d; color:#f4f5f7; padding:0; overflow:hidden; }
    .quick-cut-modal .ant-modal-header { margin:0; padding:18px 22px; background:#1d2026; border-bottom:1px solid #30343d; }
    .quick-cut-modal .ant-modal-title,.quick-cut-modal .ant-modal-close { color:#f4f5f7; }
    .quick-cut-modal .ant-modal-body { padding:20px 22px; }
    .quick-cut-modal .ant-modal-footer { margin:0; padding:14px 22px; background:#1d2026; border-top:1px solid #30343d; }
    .quick-cut-select .ant-upload-drag { border-color:#4b5260; background:#20232a; }
    .quick-cut-select .ant-upload-drag:hover { border-color:#8b5cf6; }
    .quick-cut-select .ant-upload-text,.quick-cut-select .ant-typography { color:#dfe2e8; }
    .quick-cut-upload-icon { margin:0 0 8px; color:#a78bfa; font-size:42px; line-height:1; }
    .quick-cut-video-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; max-height:230px; overflow:auto; }
    .quick-cut-video-item { display:flex; align-items:center; gap:12px; padding:12px; border:1px solid #343944; border-radius:10px; background:#20232a; color:#e8eaf0; cursor:pointer; }
    .quick-cut-video-item.active { border-color:#8b5cf6; box-shadow:0 0 0 2px rgba(139,92,246,.18); }
    .quick-cut-video-icon { width:42px; height:42px; display:flex; align-items:center; justify-content:center; border-radius:8px; background:#303540; color:#a78bfa; }
    .quick-cut-editor { display:grid; grid-template-columns:minmax(0,1fr) 330px; grid-template-rows:minmax(440px,1fr) 104px; gap:16px; }
    .quick-cut-player { min-width:0; min-height:440px; display:flex; align-items:center; justify-content:center; border-radius:10px; background:#08090b; overflow:hidden; }
    .quick-cut-player video { width:100%; max-height:560px; background:#000; }
    .quick-cut-panel { padding:16px; border:1px solid #30343d; border-radius:10px; background:#20232a; }
    .quick-cut-panel .ant-typography { color:#e5e7eb; }
    .quick-cut-panel .ant-slider-rail { background:#454b57; }
    .quick-cut-panel .ant-input-number { width:145px; }
    .quick-cut-deleted { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
    .quick-cut-timeline { grid-column:1 / -1; padding:12px; border:1px solid #30343d; border-radius:10px; background:#20232a; }
    .quick-cut-ruler { display:flex; justify-content:space-between; margin-bottom:8px; color:#8f96a3; font-size:10px; }
    .quick-cut-track { position:relative; height:55px; border-radius:7px; background:repeating-linear-gradient(90deg,#5a6170 0,#5a6170 44px,#4b5260 44px,#4b5260 88px); overflow:hidden; }
    .quick-cut-deleted-block { position:absolute; top:0; bottom:0; min-width:2px; display:flex; align-items:center; justify-content:center; background:rgba(239,68,68,.82); color:#fff; font-size:11px; }
    .asset-audio-player { width:150px; height:30px; }
    @media (max-width:1100px) { .video-studio-body { grid-template-columns:190px minmax(390px,1fr); } .video-studio-preview { display:none; } .quick-cut-editor { grid-template-columns:1fr; } .quick-cut-timeline { grid-column:1; } }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel">
    const { useState, useEffect, useRef, useMemo } = React;
    const { Layout, Menu, Button, Modal, Input, InputNumber, Progress, Tabs, Table, Upload, message, Empty, Tag, Space, Typography, Card, DatePicker, Row, Col, Anchor, Popconfirm, Alert, AutoComplete, Radio, Switch, Divider, Tooltip, Slider, Spin, Dropdown, Checkbox, Descriptions, Collapse, Select, Segmented } = antd;
    const { Title, Text, Paragraph } = Typography;

    const PROMPT_KEYS = [
      { key: "asset_analysis", label: "1. 资产拆解提示词" },
      { key: "shot_split", label: "2. 片段分解提示词" },
      { key: "seedance_prompt", label: "3. Seedance 生成提示词" },
      { key: "asset_match", label: "4. 资产匹配提示词" },
      { key: "smart_asset_match", label: "5. 资产自动分配提示词" },
      { key: "reserved_5", label: "6. 预留（后续补充）" },
    ];

    const STEP_API = {
      analyze: { label: "① 资产拆解", note: "调用 LLM 抽人物/道具/场景，落 SQLite" },
      image:   { label: "② 资产生图", note: "Seedream 生图，每资产一次调用（产生费用）" },
      split:   { label: "③ 片段分解", note: "AI 拆分剧本为集/片段（产生费用）" },
      compose: { label: "④ 生成提示词", note: "逐片段生成 Seedance 提示词+@资产（产生费用）" },
      report:  { label: "⑤ 生成报告", note: "汇总资产/图片/片段/提示词数量" },
    };

    function extractTitle(text) {
      const m = text.match(/《([^》]+)》/);
      return m ? m[1].trim() : "";
    }

    function isExtraCharacter(asset) {
      return asset?.category==='character' && asset?.profile?.asset_role==='extra_character';
    }

    function formatEpisodeRanges(values) {
      const episodes = [...new Set((values || []).map(Number).filter(Number.isFinite))].sort((a,b)=>a-b);
      if (!episodes.length) return '-';
      const ranges = [];
      let start = episodes[0], end = episodes[0];
      for (let index=1; index<episodes.length; index+=1) {
        if (episodes[index] === end + 1) { end = episodes[index]; continue; }
        ranges.push(start === end ? `${start}` : `${start}-${end}`);
        start = end = episodes[index];
      }
      ranges.push(start === end ? `${start}` : `${start}-${end}`);
      return `第${ranges.join('、')}集`;
    }

    function App() {
      const [menuKey, setMenuKey] = useState('projects');
      const [projects, setProjects] = useState([]);
      const [videoTaskRecords, setVideoTaskRecords] = useState([]);
      const [videoTasksLoading, setVideoTasksLoading] = useState(false);
      const [splitTaskRecords, setSplitTaskRecords] = useState([]);
      const [splitTaskDetails, setSplitTaskDetails] = useState({});
      const [splitTasksLoading, setSplitTasksLoading] = useState(false);
      const [splitSelectOpen, setSplitSelectOpen] = useState(false);
      const [selectedSplitEpisodes, setSelectedSplitEpisodes] = useState([]);
      const [splitSubmitting, setSplitSubmitting] = useState(false);
      const [active, setActive] = useState(null);
      const [settings, setSettings] = useState({});
      const [assets, setAssets] = useState([]);
      const [shots, setShots] = useState(null);
      const [prompts, setPrompts] = useState(null);
      const [projectTab, setProjectTab] = useState('script');
      const [running, setRunning] = useState(null);
      const [report, setReport] = useState(null);
      const [createOpen, setCreateOpen] = useState(false);
      const [newName, setNewName] = useState('');
      const [scriptFile, setScriptFile] = useState(null);
      const [scriptMeta, setScriptMeta] = useState(null);       // {title, created, chars}
      const [scriptEpisodes, setScriptEpisodes] = useState([]); // [{index, title, content}]
      const [reparsing, setReparsing] = useState(false);
      const [streaming, setStreaming] = useState(false);
      const [streamText, setStreamText] = useState("");
      const [streamMeta, setStreamMeta] = useState(null);
      const [streamBatch, setStreamBatch] = useState(null);
      const [streamRaw, setStreamRaw] = useState("");
      const [streamDiagnostics, setStreamDiagnostics] = useState(null);
      const [streamPrompts, setStreamPrompts] = useState({}); // { [batchIndex]: full prompt text }
      const [streamPromptIdx, setStreamPromptIdx] = useState(0); // 请求 Tab 当前展示的批次
      const [metaTab, setMetaTab] = useState('overview'); // 请求 Tab 内嵌子 Tab: overview/template/batch
      const [streamModalOpen, setStreamModalOpen] = useState(false);
      const [promptModalOpen, setPromptModalOpen] = useState(false);
      const [assetPromptDraft, setAssetPromptDraft] = useState("");
      const [selectedAssetIds, setSelectedAssetIds] = useState([]);
      const [assetPromptGenerating, setAssetPromptGenerating] = useState(false);
      const [assetImageGenerating, setAssetImageGenerating] = useState(null);
      const [assetGalleryOpen, setAssetGalleryOpen] = useState(false);
      const [assetGalleryAsset, setAssetGalleryAsset] = useState(null);
      const [assetGalleryImages, setAssetGalleryImages] = useState([]);
      const [assetGalleryLoading, setAssetGalleryLoading] = useState(false);
      const [assetImageUrl, setAssetImageUrl] = useState('');
      const [assetImageMaterialId, setAssetImageMaterialId] = useState('');
      const [assetImageUrlSaving, setAssetImageUrlSaving] = useState(false);
      const [fragmentStreaming, setFragmentStreaming] = useState(false);
      const [fragmentModalOpen, setFragmentModalOpen] = useState(false);
      const [fragmentText, setFragmentText] = useState("");
      const [fragmentMeta, setFragmentMeta] = useState(null);
      const [fragmentPrompt, setFragmentPrompt] = useState("");
      const [fragmentRaw, setFragmentRaw] = useState("");
      const [fragmentDiagnostics, setFragmentDiagnostics] = useState(null);
      const [fragmentSource, setFragmentSource] = useState("");
      const [fragmentPromptModalOpen, setFragmentPromptModalOpen] = useState(false);
      const [fragmentPromptDraft, setFragmentPromptDraft] = useState("");
      const [seedancePromptSettingsOpen, setSeedancePromptSettingsOpen] = useState(false);
      const [seedancePromptSettingsDraft, setSeedancePromptSettingsDraft] = useState("");
      const [seedanceGenerating, setSeedanceGenerating] = useState(false);
      const [seedanceProgress, setSeedanceProgress] = useState({ total:0, completed:0, current:0, label:'', percent:0 });
      const [seedanceDuration, setSeedanceDuration] = useState(100);
      const [seedanceModalOpen, setSeedanceModalOpen] = useState(false);
      const [seedanceExchanges, setSeedanceExchanges] = useState({});
      const [seedanceExchangeIndex, setSeedanceExchangeIndex] = useState(1);
      const [basicSettings, setBasicSettings] = useState(null);
      const [basicSettingsSaving, setBasicSettingsSaving] = useState(false);
      const [visualStyle, setVisualStyle] = useState(null);
      const [visualStyleAnalyzing, setVisualStyleAnalyzing] = useState(false);
      const contentRef = useRef(null);

      const api = async (url, opt={}) => {
        const response = await fetch(url, { headers:{'Content-Type':'application/json'}, ...opt });
        const data = await response.json();
        if (!response.ok) throw new Error(data?.detail || `请求失败（${response.status}）`);
        return data;
      };

      const loadProjects = () => api('/api/projects').then(setProjects);
      const loadVideoTasks = async (refresh=false) => {
        setVideoTasksLoading(true);
        try {
          const records = await api(`/api/video-tasks?refresh=${refresh}`);
          setVideoTaskRecords(Array.isArray(records) ? records : []);
        } catch (error) {
          message.error('加载视频生成任务失败');
        } finally {
          setVideoTasksLoading(false);
        }
      };
      const loadSplitTasks = async (silent=false) => {
        if (!silent) setSplitTasksLoading(true);
        try {
          const records = await api('/api/split-tasks');
          setSplitTaskRecords(Array.isArray(records) ? records : []);
        } catch (error) {
          if (!silent) message.error('加载拆解任务失败');
        } finally {
          if (!silent) setSplitTasksLoading(false);
        }
      };
      const loadSplitTaskDetail = async record => {
        if (!record?.id || splitTaskDetails[record.id]) return;
        try {
          const detail = await api(`/api/projects/${encodeURIComponent(record.project)}/split-tasks/${encodeURIComponent(record.id)}`);
          setSplitTaskDetails(previous=>({...previous,[record.id]:detail}));
        } catch (error) { message.error(`任务详情加载失败：${error.message || error}`); }
      };
      const openSplitSelector = () => {
        if (!scriptEpisodes.filter(item => Number(item.index) > 0).length) return message.warning('请先上传并解析剧本');
        setSelectedSplitEpisodes([]);
        setSplitSelectOpen(true);
      };
      const submitSplitTasks = async () => {
        if (!active || !selectedSplitEpisodes.length) return message.warning('请至少选择一集');
        setSplitSubmitting(true);
        try {
          const result = await api(`/api/projects/${encodeURIComponent(active)}/split-tasks`, {
            method:'POST', body:JSON.stringify({episodes:selectedSplitEpisodes.map(Number)}),
          });
          if (!result.tasks) throw new Error(result.detail || '提交拆解任务失败');
          setSplitSelectOpen(false);
          message.success(`已提交 ${result.count} 个拆解任务，将按选择顺序依次执行`);
          loadSplitTasks(true);
        } catch (error) {
          message.error(error.message || String(error));
        } finally {
          setSplitSubmitting(false);
        }
      };
      const loadAssets = (name) => api(`/api/projects/${encodeURIComponent(name)}/assets`).then(setAssets);
      const loadBasicSettings = (name) => api(`/api/projects/${encodeURIComponent(name)}/basic-settings`).then(setBasicSettings);
      const loadVisualStyle = (name) => api(`/api/projects/${encodeURIComponent(name)}/visual-style`).then(setVisualStyle).catch(()=>setVisualStyle(null));
      const analyzeVisualStyle = async () => {
        if (!active) return;
        setVisualStyleAnalyzing(true);
        try {
          const style = await api(`/api/projects/${encodeURIComponent(active)}/visual-style/analyze`, {method:'POST'});
          setVisualStyle(style);
          message.success('项目统一视觉风格已手动重新分析并固化');
        } catch (error) { message.error('视觉风格分析失败：' + error); }
        finally { setVisualStyleAnalyzing(false); }
      };
      const saveBasicSettings = async (silent=false) => {
        if (!active || !basicSettings) return;
        setBasicSettingsSaving(true);
        try {
          const res = await api(`/api/projects/${encodeURIComponent(active)}/basic-settings`, {
            method:'POST', body:JSON.stringify(basicSettings),
          });
          setBasicSettings(res.settings || basicSettings);
          setVisualStyle(res.visual_style || null);
          if (!silent) message.success(res.style_reanalyzed === false ? '基本设定未变化，继续使用现有风格母版' : '基本设定已保存，统一视觉风格已自动更新');
          return res.settings || basicSettings;
        } catch (err) {
          message.error('保存基本设定失败：' + err);
          throw err;
        } finally {
          setBasicSettingsSaving(false);
        }
      };
      const loadScript = (name) => {
        api(`/api/projects/${encodeURIComponent(name)}/script`)
          .then(r => { setScriptMeta(r); setScriptEpisodes(r.episodes || []); })
          .catch(() => { setScriptMeta(null); setScriptEpisodes([]); });
      };
      const reparseScript = () => {
        if (!active) return;
        setReparsing(true);
        api(`/api/projects/${encodeURIComponent(active)}/script/reparse`, { method:'POST' })
          .then(r => {
            setScriptMeta(prev => ({ ...(prev||{}), title: r.title, chars: r.chars }));
            setScriptEpisodes(r.episodes || []);
            message.success(`重新解析完成，共 ${r.episodes?.length || 0} 集`);
          })
          .catch(e => message.error('重新解析失败：'+e))
          .finally(() => setReparsing(false));
      };
      useEffect(() => { loadProjects(); }, []);
      useEffect(() => {
        if (menuKey !== 'video-tasks') return;
        loadVideoTasks();
      }, [menuKey]);
      useEffect(() => {
        if (menuKey !== 'video-tasks') return;
        const hasActiveTask = videoTaskRecords.some(item => ['creating','queued','pending','running','processing','in_progress'].includes(String(item.status || '').toLowerCase()));
        if (!hasActiveTask) return;
        const timer = window.setInterval(()=>loadVideoTasks(true), 10000);
        return () => window.clearInterval(timer);
      }, [menuKey, videoTaskRecords]);
      useEffect(() => {
        if (menuKey !== 'split-tasks') return;
        loadSplitTasks(true);
        const timer = window.setInterval(()=>loadSplitTasks(true), 2000);
        return () => window.clearInterval(timer);
      }, [menuKey]);
      useEffect(() => {
        if (!active || projectTab !== 'shots') return;
        const refreshShots = () => api(`/api/projects/${encodeURIComponent(active)}/shots`).then(setShots).catch(()=>{});
        refreshShots();
        const timer = window.setInterval(refreshShots, 2000);
        return () => window.clearInterval(timer);
      }, [active, projectTab]);

      const openProject = (name) => {
        setActive(name); setShots(null); setPrompts(null); setReport(null);
        setScriptMeta(null); setScriptEpisodes([]); setBasicSettings(null); setVisualStyle(null);
        setSeedanceProgress({ total:0, completed:0, current:0, label:'', percent:0 });
        loadAssets(name);
        loadScript(name);
        loadBasicSettings(name);
        loadVisualStyle(name);
        api(`/api/projects/${encodeURIComponent(name)}/shots`).then(setShots).catch(()=>{});
        api(`/api/projects/${encodeURIComponent(name)}/prompts`).then(setPrompts).catch(()=>{});
        api(`/api/projects/${encodeURIComponent(name)}/seedance/config?episode=1`)
          .then(cfg => { setSeedanceDuration(cfg.target_duration || 100); setSeedanceProgress(p=>({...p,total:cfg.total||0})); })
          .catch(()=>setSeedanceDuration(100));
      };

      // 新建剧：先建剧，若有剧本则上传到该剧
      const doCreate = () => {
        const name = (newName || '').trim();
        if (!name) { message.warning('请填写剧名（或上传剧本自动识别）'); return; }
        api('/api/projects', { method:'POST', body: JSON.stringify({ name }) })
          .then(() => {
            if (scriptFile) {
              const fd = new FormData(); fd.append('file', scriptFile);
              return fetch(`/api/projects/${encodeURIComponent(name)}/script`, { method:'POST', body: fd })
                .then(()=>{});
            }
          })
          .then(() => {
            message.success('已建剧' + (scriptFile ? '并上传剧本' : ''));
            setCreateOpen(false); setNewName(''); setScriptFile(null);
            loadProjects(); openProject(name);
          })
          .catch(e => message.error('建剧失败：'+e));
      };

      const onScriptChange = (info) => {
        const f = info.file.originFileObj || info.file;
        if (!f) return;
        setScriptFile(f);
        const fallbackFromName = () => {
          const title = extractTitle(f.name || '');
          if (title) { setNewName(title); message.info('已从文件名《》识别剧名：' + title); }
        };
        // .docx/.doc 是二进制，readAsText 会得到乱码，直接用文件名识别《》
        if (/\.(docx?|pdf)$/i.test(f.name || '')) {
          fallbackFromName();
          return;
        }
        const reader = new FileReader();
        reader.onload = () => {
          const title = extractTitle(String(reader.result || ''));
          if (title) { setNewName(title); message.info('已从《》识别剧名：' + title); }
          else fallbackFromName();
        };
        reader.readAsText(f, 'utf-8');
      };

      const uploadScript = (name) => {
        const inp = document.createElement('input');
        inp.type = 'file'; inp.accept = '.txt,.doc,.docx';
        inp.onchange = () => {
          const f = inp.files[0]; if (!f) return;
          const fd = new FormData(); fd.append('file', f);
          fetch(`/api/projects/${encodeURIComponent(name)}/script`, { method:'POST', body: fd })
            .then(r=>r.json()).then(()=>{
              message.success('剧本已上传');
              loadProjects();
              loadScript(name);
            });
        };
        inp.click();
      };

      const loadSettings = () => { api('/api/settings').then(setSettings); };
      const saveSettings = () => {
        api('/api/settings', { method:'POST', body: JSON.stringify(settings) })
          .then(()=>{ message.success('设置已保存'); });
      };

      // 资产页：单独编辑"资产拆解"提示词（与设置页共用同一份 prompts.yaml，键名 asset_analysis）
      const openAssetPromptModal = () => {
        api('/api/settings').then(s => {
          setAssetPromptDraft(s.asset_analysis || '');
          setPromptModalOpen(true);
        });
      };
      const saveAssetPrompt = () => {
        api('/api/settings').then(s => {
          const next = { ...s, asset_analysis: assetPromptDraft };
          api('/api/settings', { method:'POST', body: JSON.stringify(next) })
            .then(()=>{
              message.success('资产拆解提示词已保存（与设置页同步）');
              setSettings(next);
              setPromptModalOpen(false);
            });
        });
      };

      const openFragmentPromptModal = () => {
        api('/api/settings').then(s => {
          setFragmentPromptDraft(s.shot_split || '');
          setFragmentPromptModalOpen(true);
        });
      };
      const saveFragmentPrompt = () => {
        api('/api/settings').then(s => {
          const next = { ...s, shot_split: fragmentPromptDraft };
          api('/api/settings', { method:'POST', body: JSON.stringify(next) })
            .then(() => {
              setSettings(next);
              setFragmentPromptModalOpen(false);
              message.success('片段拆解提示词已保存（与设置页同步）');
            });
        });
      };

      const openSeedancePromptSettings = () => {
        api('/api/settings').then(s => {
          setSeedancePromptSettingsDraft(s.seedance_prompt || '');
          setSeedancePromptSettingsOpen(true);
        });
      };
      const saveSeedancePromptSettings = () => {
        api('/api/settings').then(s => {
          const next = { ...s, seedance_prompt: seedancePromptSettingsDraft };
          api('/api/settings', { method:'POST', body: JSON.stringify(next) })
            .then(() => {
              setSettings(next);
              setSeedancePromptSettingsOpen(false);
              message.success('Seedance 生成提示词已保存（与设置页同步）');
            });
        });
      };

      const splitFirstEpisodeStream = () => {
        if (!active) return;
        setFragmentStreaming(true); setFragmentModalOpen(true); setFragmentText('');
        setFragmentMeta(null); setFragmentPrompt(''); setFragmentRaw('');
        setFragmentDiagnostics(null); setFragmentSource('');
        const url = `/api/projects/${encodeURIComponent(active)}/steps/split/stream?episode=1`;
        fetch(url, { method:'POST' })
          .then(resp => {
            if (!resp.ok) return resp.text().then(txt => {
              let msg = txt;
              try { msg = JSON.parse(txt).detail || txt; } catch (e) {}
              throw new Error(msg);
            });
            const reader = resp.body.getReader();
            const dec = new TextDecoder();
            let buf = '';
            const flush = () => {
              const parts = buf.split('\n\n');
              buf = parts.pop();
              for (const block of parts) {
                const lines = block.split('\n').filter(Boolean);
                let ev = 'message', data = '';
                for (const ln of lines) {
                  if (ln.startsWith('event:')) ev = ln.slice(6).trim();
                  else if (ln.startsWith('data:')) data += ln.slice(5).trim();
                }
                if (!data) continue;
                try {
                  const obj = JSON.parse(data);
                  if (ev === 'meta') setFragmentMeta(obj);
                  else if (ev === 'source') setFragmentSource(obj.text || '');
                  else if (ev === 'prompt') setFragmentPrompt(obj.prompt || '');
                  else if (ev === 'diagnostics') setFragmentDiagnostics(obj);
                  else if (ev === 'raw') setFragmentRaw(obj.text || '');
                  else if (ev === 'done') {
                    setFragmentSource(obj.source || '');
                    setShots(prev => {
                      const existing = (prev?.episodes || []).filter(ep => ep.episode !== obj.episode);
                      return { episodes: [...existing, { episode: obj.episode, source: obj.source, shots: obj.fragments }].sort((a,b)=>a.episode-b.episode) };
                    });
                    setFragmentStreaming(false);
                    message.success(`第 1 集拆解完成：${obj.count} 个片段，共 ${obj.total_seconds} 秒`);
                  } else if (ev === 'error') {
                    setFragmentStreaming(false);
                    message.error(obj.detail || '片段拆解失败');
                  } else if (obj.token) setFragmentText(t => t + obj.token);
                } catch (e) {}
              }
            };
            const pump = () => reader.read().then(({ done, value }) => {
              if (done) { if (buf) flush(); setFragmentStreaming(false); return; }
              buf += dec.decode(value, { stream:true }); flush(); return pump();
            });
            return pump();
          })
          .catch(e => { setFragmentStreaming(false); message.error('片段拆解失败：' + e.message); });
      };

      const runStep = (step) => {
        if (!active) return;
        setRunning(step);
        api(`/api/projects/${encodeURIComponent(active)}/steps/${step}`, { method:'POST' })
          .then(res => {
            if (res.ok) {
              const c = res.count!=null ? `（${res.count} 项）` : '';
              message.success(`${STEP_API[step].label} 完成${c}`);
              if (step==='analyze' || step==='image') loadAssets(active);
              if (step==='split') api(`/api/projects/${encodeURIComponent(active)}/shots`).then(setShots);
              if (step==='compose') api(`/api/projects/${encodeURIComponent(active)}/prompts`).then(setPrompts);
              if (step==='report') setReport(res.report);
            } else {
              message.error(res.detail || '步骤失败');
            }
          })
          .catch(e => message.error('请求失败：'+e))
          .finally(() => setRunning(null));
      };

      const loadPromptsForEpisode = (episode) => {
        if (!active) return;
        const target = episode || 1;
        setPrompts(null);
        api(`/api/projects/${encodeURIComponent(active)}/seedance/config?episode=${target}`)
          .then(cfg => { setSeedanceDuration(cfg.target_duration || 100); setSeedanceProgress(p=>({...p,total:cfg.total||0})); })
          .catch(()=>setSeedanceDuration(100));
        api(`/api/projects/${encodeURIComponent(active)}/prompts?episode=${target}`).then(setPrompts).catch(()=>setPrompts(null));
      };
      const loadSeedanceConfig = async (episode=1) => {
        if (!active) return;
        try {
          const cfg = await api(`/api/projects/${encodeURIComponent(active)}/seedance/config?episode=${episode}`);
          setSeedanceDuration(cfg.target_duration || 100);
          setSeedanceProgress(p => ({ ...p, total:cfg.total || 0 }));
        } catch (_) {
          setSeedanceDuration(100);
        }
      };

      const runSeedanceGenerate = async (episode=1, onlyFragmentIndex=null) => {
        if (!active || seedanceGenerating) return;
        const target = Number(seedanceDuration);
        if (!Number.isFinite(target) || target <= 0) {
          message.error('请输入有效的目标总时长');
          return;
        }
        try {
          await saveBasicSettings(true);
        } catch (_) {
          return;
        }
        setSeedanceGenerating(true);
        setSeedanceProgress({ total:0, completed:0, current:0, label:'准备中', percent:0 });
        setSeedanceExchanges({});
        setSeedanceExchangeIndex(1);
        setSeedanceModalOpen(true);
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(active)}/seedance/generate/stream`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({ episode, target_duration:target, fragment_index:onlyFragmentIndex }),
          });
          if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try { detail = (await response.json()).detail || detail; } catch (_) {}
            throw new Error(detail);
          }
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          let streamError = null;
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, {stream:true});
            const blocks = buffer.split('\n\n');
            buffer = blocks.pop() || '';
            for (const block of blocks) {
              const event = (block.match(/^event:\s*(.+)$/m) || [])[1];
              const dataText = (block.match(/^data:\s*(.+)$/m) || [])[1];
              if (!dataText) continue;
              const data = JSON.parse(dataText);
              if (event === 'error') { streamError = data.detail || '生成失败'; break; }
              if (event === 'parse_error') {
                const exchangeIndex = data.fragment_index || data.current;
                setSeedanceExchangeIndex(exchangeIndex);
                setSeedanceExchanges(prev => ({
                  ...prev,
                  [exchangeIndex]: {
                    ...prev[exchangeIndex],
                    response: data.raw || prev[exchangeIndex]?.response || '',
                    parseError: data.detail || 'JSON 格式错误',
                  },
                }));
              } else if (event === 'request') {
                const exchangeIndex = data.fragment_index || data.current;
                setSeedanceExchangeIndex(exchangeIndex);
                setSeedanceExchanges(prev => ({
                  ...prev,
                  [exchangeIndex]: { ...prev[exchangeIndex], ...data, response:'' },
                }));
              } else if (event === 'response_token') {
                const exchangeIndex = data.fragment_index || data.current;
                setSeedanceExchanges(prev => ({
                  ...prev,
                  [exchangeIndex]: {
                    ...prev[exchangeIndex],
                    response: (prev[exchangeIndex]?.response || '') + (data.token || ''),
                  },
                }));
              } else if (event === 'fragment_done') {
                setSeedanceProgress(p => ({ ...p, ...data }));
                const generatedItem = data.result;
                if (generatedItem && generatedItem.fragment_index) {
                  setPrompts(prev => {
                    const generatedEpisode = Number(generatedItem.episode || episode);
                    const previousList = Number(prev?.episode) === generatedEpisode ? (prev?.prompts || []) : [];
                    const nextList = previousList
                      .filter(entry => Number(entry?.fragment_index) !== Number(generatedItem.fragment_index))
                      .concat(generatedItem)
                      .sort((a, b) => Number(a?.fragment_index || 0) - Number(b?.fragment_index || 0));
                    return { ...(prev || {}), episode:generatedEpisode, prompts:nextList };
                  });
                }
              } else if (['meta','progress','done'].includes(event)) {
                setSeedanceProgress(p => ({ ...p, ...data }));
              }
            }
            if (streamError) throw new Error(streamError);
          }
          message.success(onlyFragmentIndex ? `片段 ${onlyFragmentIndex} 的 Seedance 提示词已生成` : '本集 Seedance 提示词已全部生成');
          api(`/api/projects/${encodeURIComponent(active)}/prompts${onlyFragmentIndex ? `?episode=${episode}` : ''}`).then(setPrompts).catch(()=>{});
        } catch(e) {
          message.error(e.message);
        } finally {
          setSeedanceGenerating(false);
        }
      };

      const assetStatus = {placeholder:['占位','default'],prompt_ready:['提示词就绪','blue'],ready:['图片就绪','green']};
      const assetKind = (asset) => asset.category==='character' && (asset.state || asset.level==='secondary') && !isExtraCharacter(asset) ? 'character_look' : asset.category;
      const generateSelectedAssetPrompts = async () => {
        const selected = assets.filter(item=>selectedAssetIds.includes(item.id));
        if (!selected.length) return message.warning('请先选择 1～5 个同类型的场景或道具资产');
        if (selected.some(item=>item.category==='character')) return message.warning('人物主形象和造型只需上传图片，不生成图片提示词');
        if (selected.length > 5) return message.warning('每批最多选择 5 个资产');
        if (new Set(selected.map(assetKind)).size > 1) return message.warning('每批只能选择同一类型资产');
        if (!visualStyle?.unified_prompt) return message.warning('请先在“基本设定”中分析并固化项目统一视觉风格');
        setAssetPromptGenerating(true);
        try {
          await api(`/api/projects/${encodeURIComponent(active)}/assets/prompts/generate`, {method:'POST',body:JSON.stringify({asset_ids:selectedAssetIds})});
          message.success(`已生成 ${selected.length} 个资产图片提示词`);
          setSelectedAssetIds([]);
          await loadAssets(active);
        } catch (error) { message.error('图片提示词生成失败：'+error); }
        finally { setAssetPromptGenerating(false); }
      };
      const generateAssetImage = async (asset) => {
        setAssetImageGenerating(asset.id);
        try {
          await api(`/api/projects/${encodeURIComponent(active)}/assets/${asset.id}/images/generate`, {method:'POST',body:JSON.stringify({size:'1024x1024',make_default:!asset.image_url})});
          message.success('资产图片已生成');
          await loadAssets(active);
          if (assetGalleryAsset?.id===asset.id) await openAssetGallery(asset);
        } catch (error) { message.error('资产图片生成失败：'+error); }
        finally { setAssetImageGenerating(null); }
      };
      const openAssetGallery = async (asset) => {
        setAssetGalleryAsset(asset); setAssetImageUrl(asset.image_url && /^https?:\/\//i.test(asset.image_url) ? asset.image_url : ''); setAssetImageMaterialId(asset.seedance_asset_id ? String(asset.seedance_asset_id).replace(/^asset:\/\//i,'') : ''); setAssetGalleryOpen(true); setAssetGalleryLoading(true);
        try { setAssetGalleryImages(await api(`/api/projects/${encodeURIComponent(active)}/assets/${asset.id}/images`)); }
        catch (_) { setAssetGalleryImages([]); }
        finally { setAssetGalleryLoading(false); }
      };
      const setDefaultAssetImage = async (imageId) => {
        await api(`/api/projects/${encodeURIComponent(active)}/assets/${assetGalleryAsset.id}/images/${imageId}/default`, {method:'POST'});
        message.success('已设为默认资产图片');
        await loadAssets(active); await openAssetGallery(assetGalleryAsset);
      };
      const saveAssetImageUrl = async () => {
        const imageUrl = assetImageUrl.trim();
        const materialId = assetImageMaterialId.trim();
        if (!/^https?:\/\/\S+$/i.test(imageUrl)) return message.warning('请输入有效的 http 或 https 公网图片链接');
        if (materialId && /\s/.test(materialId)) return message.warning('素材 ID 不能包含空格');
        setAssetImageUrlSaving(true);
        try {
          const seedanceAssetId = materialId.replace(/^asset:\/\//i,'');
          await api(`/api/projects/${encodeURIComponent(active)}/assets/${assetGalleryAsset.id}/image-url`, {method:'POST', body:JSON.stringify({image_url:imageUrl,seedance_asset_id:seedanceAssetId})});
          message.success(seedanceAssetId ? '链接和素材 ID 已保存，生成时优先使用素材 ID' : '公网链接已保存，生成时使用该链接');
          await loadAssets(active);
          setAssetGalleryAsset(prev=>prev ? {...prev,image_url:imageUrl,seedance_asset_id:seedanceAssetId,status:'ready'} : prev);
        } catch(error) { message.error(`链接保存失败：${error.message || error}`); }
        finally { setAssetImageUrlSaving(false); }
      };
      const uploadAssetImage = async (asset, file) => {
        try {
          const fd = new FormData();
          fd.append('file', file);
          await api(`/api/projects/${encodeURIComponent(active)}/assets/${asset.id}/images/upload`, {method:'POST', body:fd, headers:{}});
          message.success(`${asset.parent_id?'造型图':'人物主图'}已上传并设为默认图`);
          await loadAssets(active);
          if (assetGalleryOpen && assetGalleryAsset?.id===asset.id) await openAssetGallery(asset);
        } catch(error) { message.error(`图片上传失败：${error.message || error}`); }
        return false;
      };
      const uploadCharacterAudio = async (asset, file) => {
        try {
          const fd = new FormData();
          fd.append('file', file);
          await api(`/api/projects/${encodeURIComponent(active)}/assets/${asset.id}/audio`, {method:'POST', body:fd, headers:{}});
          message.success(`${asset.name || asset.key}参考音已上传`);
          await loadAssets(active);
        } catch(error) { message.error(`参考音上传失败：${error.message || error}`); }
        return false;
      };
      const removeCharacterAudio = async asset => {
        try {
          await api(`/api/projects/${encodeURIComponent(active)}/assets/${asset.id}/audio`, {method:'DELETE'});
          message.success('参考音已删除');
          await loadAssets(active);
        } catch(error) { message.error(`参考音删除失败：${error.message || error}`); }
      };
      const assetColumns = [
        { title: '图片', dataIndex: 'image_url', width: 100, render:(u,row)=> u ? <img className="asset-img" src={u} alt="" onClick={()=>openAssetGallery(row)} style={{cursor:'pointer'}}/> : <Text type="secondary">{row.category==='character'?'待上传':'待生成'}</Text> },
        { title: '资产', key: 'asset', render:(_,row)=><div><Text strong>{row.parent_id ? row.state : row.name}</Text><div><Text type="secondary">{row.parent_id ? `${isExtraCharacter(row)?'独立路人':'妆造'} · ${row.parent_name || row.name}` : row.key}</Text></div></div> },
        { title: '造型/角色出场集数', dataIndex: 'episodes', width:155, render:(values,row)=> row.category==='character'&&!row.state ? <Text type="secondary">仅用于身份统一</Text> : <Text type={(values||[]).length?'':'secondary'}>{formatEpisodeRanges(values)}{row.category==='character'&&row.state?' 出场':''}</Text> },
        { title: '状态', dataIndex: 'status', width:105, render:(value,row)=>{ const item=assetStatus[value]||assetStatus[row.image_url?'ready':row.image_prompt?'prompt_ready':'placeholder']; return <Tag color={item[1]}>{item[0]}</Tag>; } },
        { title: '人物参考音', key:'audio', width:260, render:(_,row)=> row.category!=='character' || row.parent_id ? <Text type="secondary">继承主人物</Text> : <Space direction="vertical" size={4}>{row.audio_path ? <Space size={6}><audio controls preload="none" src={`/api/projects/${encodeURIComponent(active)}/assets/${row.id}/audio`} className="asset-audio-player"/><Popconfirm title="删除该人物参考音？" onConfirm={()=>removeCharacterAudio(row)}><Button size="small" danger>删除</Button></Popconfirm></Space> : <Text type="secondary">未上传</Text>}<Upload accept="audio/mpeg,audio/wav,audio/mp4,audio/aac,audio/ogg,audio/flac,.mp3,.wav,.m4a,.aac,.ogg,.flac" showUploadList={false} beforeUpload={file=>uploadCharacterAudio(row,file)}><Button size="small">{row.audio_path?'更换参考音':'上传参考音'}</Button></Upload>{row.audio_name && <Text type="secondary" ellipsis style={{maxWidth:220}}>{row.audio_name}</Text>}</Space> },
        { title: '图片提示词', dataIndex: 'image_prompt', ellipsis:true, render:(value,row)=><Text type={value?'':'secondary'}>{row.category==='character'?'无需生成':(value||'待生成')}</Text> },
        { title: '操作', key:'actions', width:285, render:(_,row)=>{ const isCharacter=row.category==='character'; return <Space size={4} wrap>{isCharacter && <Upload accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" showUploadList={false} beforeUpload={file=>uploadAssetImage(row,file)}><Button size="small">{row.image_url?'上传新图':'上传图片'}</Button></Upload>}{!isCharacter && <Button size="small" disabled={!row.image_prompt} loading={assetImageGenerating===row.id} onClick={()=>generateAssetImage(row)}>生成图片</Button>}<Button size="small" onClick={()=>openAssetGallery(row)}>图片来源{row.image_count?`(${row.image_count})`:''}</Button></Space>; } },
      ];

      const flatAssets = (list) => {
        const out = [];
        list.forEach(r => { out.push(r); (r.children||[]).forEach(c=>out.push(c)); });
        return out;
      };

      // 流式重新拆解：fetch SSE，实时拼接 token，结束刷新资产列表
      const reanalyzeStream = () => {
        if (!active) return;
        setStreaming(true); setStreamText(""); setStreamMeta(null); setStreamBatch(null); setStreamRaw("");
        setStreamDiagnostics(null); setStreamPrompts({}); setStreamPromptIdx(0); setMetaTab('overview');
        setStreamModalOpen(true);  // 先打开弹窗，再发请求
        const url = `/api/projects/${encodeURIComponent(active)}/steps/analyze/stream`;
        fetch(url, { method:'POST' })
          .then(resp => {
            if (!resp.ok) {
              // 非 SSE 错误响应（如 400/500 JSON），直接读文本提示
              return resp.text().then(txt => {
                let msg = txt;
                try { msg = JSON.parse(txt).detail || txt; } catch (e) {}
                message.error('拆解失败：' + msg);
                setStreaming(false);
                throw new Error(msg);
              });
            }
            const reader = resp.body.getReader();
            const dec = new TextDecoder();
            let buf = "";
            const flush = () => {
              // SSE 按空行分块
              const parts = buf.split("\n\n");
              buf = parts.pop();
              for (const block of parts) {
                const lines = block.split("\n").filter(Boolean);
                let ev = "message", data = "";
                for (const ln of lines) {
                  if (ln.startsWith("event:")) ev = ln.slice(6).trim();
                  else if (ln.startsWith("data:")) data += ln.slice(5).trim();
                }
                if (!data) continue;
                try {
                  const obj = JSON.parse(data);
                  if (ev === "meta") {
                    setStreamMeta(obj);
                  } else if (ev === "batch") {
                    setStreamBatch({ index: obj.index, total: obj.total, label: obj.label });
                    setStreamPromptIdx(obj.index); // 同步切到当前正在进行的批次
                  } else if (ev === "prompt") {
                    setStreamPrompts(p => ({ ...p, [obj.index]: obj.prompt }));
                    setStreamPromptIdx(obj.index);
                  } else if (ev === "raw_batch") {
                    setStreamRaw(prev => prev + (prev ? '\n\n' : '') + `===== 第 ${obj.index}/${obj.total} 批 =====\n${obj.text || ''}`);
                  } else if (ev === "diagnostics") {
                    setStreamDiagnostics(obj);
                  } else if (ev === "raw") {
                    setStreamRaw(prev => prev || obj.text || "");
                  } else if (obj.token) {
                    setStreamText(t => t + obj.token);
                  } else if (ev === "done") {
                    loadAssets(active);
                    setStreaming(false);
                    setStreamBatch(null);
                    // 不自动关闭弹窗，由用户手动关闭；弹窗内"已完成"标签会更新
                  } else if (ev === "error") {
                    message.error(obj.detail || "拆解失败");
                    setStreaming(false);
                    setStreamBatch(null);
                  }
                } catch (e) { /* 忽略非 JSON 心跳 */ }
              }
            };
            const pump = () => reader.read().then(({ done, value }) => {
              if (done) { if (buf) flush(); return; }
              buf += dec.decode(value, { stream: true });
              flush();
              return pump();
            });
            return pump();
          })
          .catch(e => { message.error('请求失败：'+e); setStreaming(false); });
      };

      // 人物妆造和场景子空间按 parent_id 挂在基础资产下，道具保持平铺。
      const AssetGroup = ({ list, cat, single }) => {
        const flatRows = list.filter(a => a.category === cat);
        const cat_cn = { character:'人物', scene:'场景', prop:'道具' }[cat] || cat;
        if (flatRows.length === 0) return <Empty description={`尚无${cat_cn}`} />;
        let rows = flatRows;
        if (!single) {
          const byId = new Map(flatRows.map(item => [item.id, {...item, children:[]}]))
          rows = [];
          byId.forEach(item => {
            if (item.parent_id && byId.has(item.parent_id)) byId.get(item.parent_id).children.push(item);
            else rows.push(item);
          });
          byId.forEach(item => { if (!item.children.length) delete item.children; });
        }
        return (
          <Table rowKey="id" size="small" pagination={false} defaultExpandAllRows
                 rowSelection={{selectedRowKeys:selectedAssetIds,onChange:setSelectedAssetIds,checkStrictly:true,getCheckboxProps:record=>({disabled:record.category==='character'})}}
                 columns={assetColumns}
                 dataSource={rows} scroll={{ y: 520 }} />
        );
      };

      const menuItems = [
        { key: 'projects', icon: '🎬', label: '剧管理' },
        { key: 'split-tasks', icon: '☷', label: '拆解任务' },
        { key: 'video-tasks', icon: '▣', label: '视频生成任务' },
        { key: 'settings', icon: '⚙️', label: '设置' },
      ];

      return (
        <Layout style={{ height: '100vh' }}>
          <Layout.Sider width={200} theme="dark">
            <div style={{ color:'#fff', padding:'16px', fontWeight:600 }}>Seedanceminiv2</div>
            <Menu theme="dark" mode="inline" selectedKeys={[menuKey]}
                  onClick={({key})=>{
                    setMenuKey(key);
                    if (key==='settings') loadSettings();
                    if (key==='split-tasks') loadSplitTasks();
                    if (key==='video-tasks') loadVideoTasks();
                  }} items={menuItems} />
          </Layout.Sider>

          <Layout>
            <Layout.Header style={{ background:'#fff', display:'flex', alignItems:'center', justifyContent:'space-between', padding:'0 24px' }}>
              <Title level={4} style={{ margin:0 }}>{menuKey==='projects' ? '剧管理' : menuKey==='split-tasks' ? '拆解任务' : menuKey==='video-tasks' ? '视频生成任务' : '设置'}</Title>
              {menuKey==='projects' &&
                <Button type="primary" onClick={()=>{ setNewName(''); setScriptFile(null); setCreateOpen(true); }}>
                  ＋ 新建剧
                </Button>}
            </Layout.Header>

            <Layout.Content ref={contentRef} style={{ padding:24, overflow:'auto', background:'#f5f5f5' }}>
              {menuKey==='settings' && (
                <div>
                  <Space style={{ marginBottom:16 }}>
                    <Button type="primary" onClick={saveSettings}>保存提示词模板</Button>
                    <Text type="secondary">打开即编辑，修改后点保存（资产拆解 / 片段分解 / Seedance 生成 / 资产匹配 / 预留）。</Text>
                  </Space>
                  <Row gutter={[12, 12]}>
                    {PROMPT_KEYS.map(pk => (
                      <Col span={24 / PROMPT_KEYS.length} key={pk.key}>
                        <Text strong style={{ display:'block', marginBottom:6 }}>{pk.label}</Text>
                        <Input.TextArea rows={12} style={{ width:'100%' }}
                                        value={settings[pk.key] || ''}
                                        onChange={(e)=>setSettings({...settings, [pk.key]: e.target.value})} />
                      </Col>
                    ))}
                  </Row>
                </div>
              )}

              {menuKey==='projects' && !active && (
                projects.length===0
                  ? <Empty description="暂无剧，点击右上角「新建剧」" />
                  : <div style={{ display:'flex', flexWrap:'wrap', gap:16 }}>
                      {projects.map(p => (
                        <Card key={p.name} className="proj-card"
                              style={{ width:260 }}
                              hoverable
                              onClick={()=>openProject(p.name)}
                              title={p.name}
                              extra={p.has_script ? <Tag color="green">已上传剧本</Tag> : <Tag>未上传</Tag>}>
                          <div style={{ color:'#888', fontSize:13 }}>创建：{p.created}</div>
                        </Card>
                      ))}
                    </div>
              )}

              {menuKey==='split-tasks' && (
                <SplitTasksView records={splitTaskRecords} details={splitTaskDetails} loading={splitTasksLoading} onRefresh={loadSplitTasks} onLoadDetail={loadSplitTaskDetail} />
              )}

              {menuKey==='video-tasks' && (
                <VideoTasksView
                  records={videoTaskRecords}
                  loading={videoTasksLoading}
                  onRefresh={loadVideoTasks}
                  onOpenProject={(name)=>{ setMenuKey('projects'); openProject(name); }}
                />
              )}

              {menuKey==='projects' && active && (
                <div>
                  <Space style={{marginBottom:16}}>
                    <Button onClick={()=>{ setActive(null); }}>← 返回剧列表</Button>
                    <Button type="primary" onClick={()=>uploadScript(active)}>⬆ 上传剧本</Button>
                    <Text strong>当前剧：{active}</Text>
                  </Space>
                  <Tabs activeKey={projectTab} onChange={setProjectTab} items={[
                    { key:'basic', label:'基本设定', children: (
                      <BasicSettingsView settings={basicSettings} onChange={setBasicSettings}
                                         onSave={saveBasicSettings} saving={basicSettingsSaving}
                                         visualStyle={visualStyle} onAnalyzeStyle={analyzeVisualStyle}
                                         styleAnalyzing={visualStyleAnalyzing} />
                    )},
                    { key:'script', label:'剧本',
                      children: (
                        <div style={{ position:'relative' }}>
                          {/* 电梯：悬浮右侧，默认收起，hover 展开，绑定内容滚动容器 */}
                          {scriptEpisodes.length > 0 && (
                            <div className="ep-nav">
                              <div className="ep-nav-handle">☰<br/>剧<br/>集</div>
                              <div className="ep-nav-body">
                                <Anchor
                                  affix={false}
                                  offsetTop={96}
                                  getContainer={() => contentRef.current}
                                  targetOffset={96}
                                  items={[
                                    { key:'#ep-info', href:'#ep-info', title:'基本信息' },
                                    ...scriptEpisodes.map(ep => ({
                                      key: `#ep-${ep.index}`,
                                      href: `#ep-${ep.index}`,
                                      title: ep.title || (ep.index === 0 ? '前言' : `第 ${ep.index} 集`),
                                    })),
                                  ]}
                                />
                              </div>
                            </div>
                          )}
                          {scriptMeta ? (
                            <Card id="ep-info" size="small" style={{ marginBottom:16 }}
                                  title="基本信息"
                                  extra={<Button size="small" loading={reparsing} onClick={reparseScript}>🔄 重新解析</Button>}>
                              <Space size="large" wrap>
                                <span><Text type="secondary">项目名称：</Text><Text strong>{active}</Text></span>
                                <span><Text type="secondary">创建时间：</Text><Text>{scriptMeta.created || '—'}</Text></span>
                                <span><Text type="secondary">总字符数：</Text><Text>{scriptMeta.chars || 0}</Text></span>
                                <span><Text type="secondary">识别剧名：</Text><Text>{scriptMeta.title || '—（未识别到《》）'}</Text></span>
                                <span><Text type="secondary">分集数：</Text><Tag color="blue">{scriptEpisodes.length} 集</Tag></span>
                              </Space>
                            </Card>
                          ) : (
                            <Empty description="尚未上传剧本" />
                          )}
                          <Title level={5} style={{ marginTop:8 }}>各集内容</Title>
                          {scriptEpisodes.length === 0
                            ? <Empty description="剧本未解析出集数" />
                            : scriptEpisodes.map(ep => (
                                <Card id={`ep-${ep.index}`} key={ep.index} size="small"
                                      className="shot-card"
                                      title={ep.title || (ep.index === 0 ? '前言' : `第 ${ep.index} 集`)}
                                      style={{ marginBottom:12, marginRight:120 }}>
                                  <pre style={{
                                    whiteSpace:'pre-wrap', wordBreak:'break-word',
                                    margin:0, fontFamily:'inherit', fontSize:14, lineHeight:1.8,
                                  }}>{ep.content || '（空）'}</pre>
                                  <Text type="secondary" style={{ fontSize:12, marginTop:6, display:'block' }}>
                                    {ep.content ? ep.content.length : 0} 字
                                  </Text>
                                </Card>
                              ))}
                        </div>
                      )
                    },
                    { key:'assets', label:'资产',
                      children: (
                        <div>
                          <Space style={{ marginBottom:16 }} wrap>
                            <Popconfirm title="确认重新拆解？"
                                        description="将清空当前资产并重新调用 AI 拆解（产生费用）"
                                        okText="重新拆解" cancelText="取消"
                                        onConfirm={reanalyzeStream}>
                              <Button type="primary" loading={streaming}>🔄 重新拆解</Button>
                            </Popconfirm>
                            <Button onClick={()=>runStep('analyze')} loading={running==='analyze'}>① 资产拆解（非流式）</Button>
                            <Button onClick={openAssetPromptModal}>⚙ 资产拆解提示词</Button>
                            <Button type="primary" ghost loading={assetPromptGenerating} disabled={!selectedAssetIds.length} onClick={generateSelectedAssetPrompts}>生成所选场景/道具提示词{selectedAssetIds.length?` (${selectedAssetIds.length})`:''}</Button>
                            <Text type="secondary">AI 通读剧本全文，找出每个角色的主形象和全部主要着装并创建占位；人物无需图片提示词，请直接上传主图和各造型图。场景、道具等其他资产继续生成提示词。</Text>
                          </Space>

                          {assets.length === 0 ? (
                            <Empty description="尚无资产，先运行『① 资产拆解』或『🔄 重新拆解』" />
                          ) : (
                            <Tabs defaultActiveKey="character" size="small"
                                  items={[
                                    { key:'character', label:`人物 (${assets.filter(a=>a.category==='character').length})`,
                                      children: <AssetGroup list={assets} cat="character" /> },
                                    { key:'scene', label:`场景 (${assets.filter(a=>a.category==='scene').length})`,
                                      children: <AssetGroup list={assets} cat="scene" /> },
                                    { key:'prop', label:`道具 (${assets.filter(a=>a.category==='prop').length})`,
                                      children: <AssetGroup list={assets} cat="prop" single /> },
                                  ]} />
                          )}
                        </div>
                      )
                    },
                    { key:'steps', label:'分析步骤',
                      children: (
                        <Space direction="vertical" style={{width:'100%'}}>
                          {Object.keys(STEP_API).map(step => (
                            <Space key={step}>
                              <Button type={step==='analyze'?'primary':'default'} loading={running===step} onClick={()=>runStep(step)}>
                                {STEP_API[step].label}
                              </Button>
                              <Text type="secondary">{STEP_API[step].note}</Text>
                            </Space>
                          ))}
                          {report && (
                            <Alert type="success" message="报告"
                              description={`资产 ${report.assets} · 图片 ${report.images} · 片段 ${report.shots} · 提示词 ${report.prompts}`} />
                          )}
                        </Space>
                      )
                    },
                    { key:'shots', label:'片段',
                      children: (
                        <div>
                          <Space wrap style={{ marginBottom:16 }}>
                            <Button type="primary" onClick={openSplitSelector}>拆解片段</Button>
                            <Button onClick={openFragmentPromptModal}>提示词设置</Button>
                            <Text type="secondary">支持多选集数，任务将按选择顺序依次执行，可在左侧“拆解任务”查看进度和原始数据。</Text>
                          </Space>
                          <ShotsView
                            shots={shots}
                            source={fragmentSource}
                            onGenerate={(episode, fragmentIndex=null)=>runSeedanceGenerate(episode, fragmentIndex)}
                            onRefresh={()=>api(`/api/projects/${encodeURIComponent(active)}/shots`).then(setShots)}
                            generating={seedanceGenerating}
                            progress={seedanceProgress}
                            targetDuration={seedanceDuration}
                            onDurationChange={value=>setSeedanceDuration(value || 100)}
                          />
                        </div>
                      )
                    },
                    { key:'prompts', label:'Seedance 视频生成',
                      children: <SeedanceVideoStudio project={active} data={prompts} assets={assets} onAssetsChange={()=>loadAssets(active)} settings={basicSettings} episodes={scriptEpisodes} shots={shots} onEpisodeChange={loadPromptsForEpisode} onSplitNeeded={()=>setProjectTab('shots')} onOpenPromptSettings={openSeedancePromptSettings} onRegenerateFragment={(fragmentIndex)=>runSeedanceGenerate(prompts?.episode || 1, fragmentIndex)} generatingFragment={seedanceGenerating} activeFragmentIndex={seedanceProgress?.fragment_index} progress={seedanceProgress} exchanges={seedanceExchanges} exchangeIndex={seedanceExchangeIndex} modalOpen={seedanceModalOpen} onCloseModal={()=>setSeedanceModalOpen(false)} />
                    },
                  ]} />
                </div>
              )}
            </Layout.Content>
          </Layout>

          <Modal title="新建剧" open={createOpen} onOk={doCreate} onCancel={()=>setCreateOpen(false)} okText="创建"
                 destroyOnClose>
            <Space direction="vertical" style={{width:'100%'}}>
              <div>
                <Text strong>上传剧本（可选，txt/doc/docx）</Text>
                <Upload beforeUpload={()=>false} maxCount={1} onChange={onScriptChange} fileList={scriptFile?[scriptFile]:[]}>
                  <Button>选择剧本文件</Button>
                </Upload>
                <Text type="secondary" style={{fontSize:12}}>若剧本含《剧名》，将自动识别并填入下方</Text>
              </div>
              <div>
                <Text strong>剧名称</Text>
                <Input value={newName} onChange={(e)=>setNewName(e.target.value)}
                       placeholder="输入剧名，或上传剧本自动识别" />
              </div>
            </Space>
          </Modal>

          <Modal title="选择需要拆解的集数" open={splitSelectOpen} onCancel={()=>setSplitSelectOpen(false)}
                 onOk={submitSplitTasks} confirmLoading={splitSubmitting} okText={`提交 ${selectedSplitEpisodes.length || ''} 个任务`} width={760} destroyOnClose>
            <Space direction="vertical" style={{width:'100%'}} size={12}>
              <Text type="secondary">可多选。提交后将按你的选择顺序逐集执行，不会主动弹出请求和返回窗口。</Text>
              <Space wrap>
                <Button size="small" onClick={()=>setSelectedSplitEpisodes(scriptEpisodes.filter(item=>Number(item.index)>0).map(item=>Number(item.index)))}>全选</Button>
                <Button size="small" onClick={()=>setSelectedSplitEpisodes([])}>清空</Button>
                <Tag color="blue">已选择 {selectedSplitEpisodes.length} 集</Tag>
              </Space>
              <Checkbox.Group value={selectedSplitEpisodes} onChange={setSelectedSplitEpisodes} style={{width:'100%'}}>
                <Row gutter={[8,8]}>
                  {scriptEpisodes.filter(item=>Number(item.index)>0).map(item=><Col xs={12} sm={8} md={6} key={item.index}><Checkbox value={Number(item.index)}>{item.title || `第${item.index}集`}</Checkbox></Col>)}
                </Row>
              </Checkbox.Group>
            </Space>
          </Modal>

          <Modal title={assetGalleryAsset ? `${assetGalleryAsset.name}${assetGalleryAsset.state?`-${assetGalleryAsset.state}`:''} · 图片来源` : '资产图片来源'} open={assetGalleryOpen} onCancel={()=>setAssetGalleryOpen(false)} width={900} footer={null} destroyOnClose>
            <Space direction="vertical" size={12} style={{width:'100%',marginBottom:16}}>
              <Space wrap>{assetGalleryAsset?.category==='character' && <Upload accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" showUploadList={false} beforeUpload={file=>uploadAssetImage(assetGalleryAsset,file)}><Button type="primary">上传新候选图</Button></Upload>}<Text type="secondary">或填写公网图片链接；火山报白素材 ID 可选</Text></Space>
              <Input value={assetImageUrl} onChange={e=>setAssetImageUrl(e.target.value)} placeholder="公网图片链接：https://example.com/image.jpg" />
              <Space.Compact style={{width:'100%'}}><Input addonBefore="asset://" value={assetImageMaterialId} onChange={e=>setAssetImageMaterialId(e.target.value.replace(/^asset:\/\//i,''))} placeholder="<ASSET_ID>（选填）" onPressEnter={saveAssetImageUrl}/><Button loading={assetImageUrlSaving} disabled={!assetImageUrl.trim()} onClick={saveAssetImageUrl}>保存</Button></Space.Compact>
              {/^https?:\/\//i.test(assetImageUrl) && <img src={assetImageUrl} alt="公网图片预览" style={{width:160,height:160,objectFit:'contain',background:'#f5f5f5',borderRadius:8}}/>}
            </Space>
            <Divider style={{margin:'8px 0 16px'}}>本地候选图片</Divider>
            {assetGalleryLoading ? <div style={{textAlign:'center',padding:40}}><Spin /></div> : assetGalleryImages.length ? <Row gutter={[12,12]}>{assetGalleryImages.map(image=><Col span={8} key={image.id}><Card size="small" cover={<img src={image.image_url} style={{height:240,objectFit:'contain',background:'#f5f5f5'}}/>} actions={[image.is_default?<Tag color="green">默认图片</Tag>:<Button type="link" onClick={()=>setDefaultAssetImage(image.id)}>设为默认</Button>]}><Text type="secondary">{image.source==='generated'?'AI 生成':'用户上传'}</Text></Card></Col>)}</Row> : <Empty description="暂无本地候选图片" />}
          </Modal>

          {/* 资产拆解提示词编辑弹窗（仅 asset_analysis，与设置页同步） */}
          <Modal title="⚙ 资产拆解提示词" open={promptModalOpen} onCancel={()=>setPromptModalOpen(false)}
                 width={760} footer={null} destroyOnClose>
            <Text type="secondary" style={{ display:'block', marginBottom:8 }}>
              仅编辑「资产拆解」所用的提示词模板（键名 asset_analysis），保存后会与设置页同步更新 prompts.yaml。
              占位符 <code>{'{{SCRIPT}}'}</code> 会被替换为按集分批后的剧本正文。
            </Text>
            <Input.TextArea rows={18} value={assetPromptDraft}
                            onChange={(e)=>setAssetPromptDraft(e.target.value)}
                            style={{ fontFamily:'ui-monospace,Menlo,monospace', fontSize:12 }} />
            <Space style={{ marginTop:12 }}>
              <Button type="primary" onClick={saveAssetPrompt}>保存</Button>
              <Button onClick={()=>setPromptModalOpen(false)}>取消</Button>
              <Button size="small" onClick={()=>{
                api('/api/settings').then(s=>setAssetPromptDraft(s.asset_analysis||''));
              }}>从服务器重新加载</Button>
            </Space>
          </Modal>

          <Modal title={seedanceGenerating ? 'Seedance 提示词生成中…' : 'Seedance 提示词生成信息'}
                 open={seedanceModalOpen}
                 onCancel={()=>setSeedanceModalOpen(false)}
                 width={1000} footer={null} destroyOnClose maskClosable keyboard closable>
            <Space wrap style={{ marginBottom:12 }}>
              {Object.keys(seedanceExchanges).map(index => {
                const item = seedanceExchanges[index];
                return <Button key={index} size="small"
                               type={Number(index) === seedanceExchangeIndex ? 'primary' : 'default'}
                               onClick={()=>setSeedanceExchangeIndex(Number(index))}>
                  片段 {index}{item?.label ? ` · ${item.label}` : ''}
                </Button>;
              })}
            </Space>
            {seedanceExchanges[seedanceExchangeIndex] ? <Tabs defaultActiveKey="response" items={[
              { key:'request', label:'① 请求信息', children:<div>
                  <Space wrap style={{ marginBottom:10 }}>
                    <Tag>片段 {seedanceExchangeIndex}/{seedanceExchanges[seedanceExchangeIndex].total}</Tag>
                    <Tag color="blue">{seedanceExchanges[seedanceExchangeIndex].label}</Tag>
                  </Space>
                  <Paragraph strong>System Prompt</Paragraph>
                  <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:220, overflow:'auto', background:'#f6f6f6', padding:10 }}>{seedanceExchanges[seedanceExchangeIndex].system_prompt}</pre>
                  <Paragraph strong>User Prompt</Paragraph>
                  <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:320, overflow:'auto', background:'#f6f6f6', padding:10 }}>{seedanceExchanges[seedanceExchangeIndex].user_prompt}</pre>
                </div> },
              { key:'response', label:'② 实时返回', children:<div>
                  {seedanceExchanges[seedanceExchangeIndex].parseError && <Alert type="error" showIcon style={{ marginBottom:10 }} message="返回内容不是合法 JSON" description={seedanceExchanges[seedanceExchangeIndex].parseError} />}
                  <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:520, overflow:'auto', background:'#111827', color:'#d1fae5', padding:12 }}>{seedanceExchanges[seedanceExchangeIndex].response || '等待模型返回…'}</pre>
                </div> },
            ]} /> : <Empty description="等待发送第一个片段请求" />}
            <div style={{ marginTop:12, textAlign:'right' }}><Space>
              {seedanceGenerating ? <Tag color="processing">生成中…</Tag> : <Tag color="success">已结束</Tag>}
              <Button onClick={()=>setSeedanceModalOpen(false)}>关闭</Button>
            </Space></div>
          </Modal>

          <Modal title="片段拆解提示词" open={fragmentPromptModalOpen}
                 onCancel={()=>setFragmentPromptModalOpen(false)} width={860} footer={null} destroyOnClose>
            <Text type="secondary" style={{ display:'block', marginBottom:8 }}>
              编辑 `shot_split` 模板；保存后与全局设置页同步。占位符 <code>{'{{SCRIPT}}'}</code> 会替换为当前单集原文。
            </Text>
            <Input.TextArea rows={24} value={fragmentPromptDraft}
                            onChange={(e)=>setFragmentPromptDraft(e.target.value)}
                            style={{ fontFamily:'ui-monospace,Menlo,monospace', fontSize:12 }} />
            <Space style={{ marginTop:12 }}>
              <Button type="primary" onClick={saveFragmentPrompt}>保存</Button>
              <Button onClick={()=>setFragmentPromptModalOpen(false)}>取消</Button>
              <Button size="small" onClick={()=>api('/api/settings').then(s=>setFragmentPromptDraft(s.shot_split||''))}>从服务器重新加载</Button>
            </Space>
          </Modal>

          <Modal title="设置 Seedance 生成提示词" open={seedancePromptSettingsOpen}
                 onCancel={()=>setSeedancePromptSettingsOpen(false)} width={860} footer={null} destroyOnClose>
            <Text type="secondary" style={{ display:'block', marginBottom:8 }}>
              编辑 Seedance 视频生成使用的提示词模板；保存后与设置页中的「Seedance 生成提示词」同步。
            </Text>
            <Input.TextArea rows={24} value={seedancePromptSettingsDraft}
                            onChange={(e)=>setSeedancePromptSettingsDraft(e.target.value)}
                            style={{ fontFamily:'ui-monospace,Menlo,monospace', fontSize:12 }} />
            <Space style={{ marginTop:12 }}>
              <Button type="primary" onClick={saveSeedancePromptSettings}>保存</Button>
              <Button onClick={()=>setSeedancePromptSettingsOpen(false)}>取消</Button>
              <Button size="small" onClick={()=>api('/api/settings').then(s=>setSeedancePromptSettingsDraft(s.seedance_prompt||''))}>从服务器重新加载</Button>
            </Space>
          </Modal>

          <Modal title={fragmentStreaming ? '第 1 集片段拆解中…' : '第 1 集片段拆解结果'}
                 open={fragmentModalOpen} onCancel={()=>{ if (!fragmentStreaming) setFragmentModalOpen(false); }}
                 width={960} footer={null} destroyOnClose maskClosable={!fragmentStreaming}>
            <Tabs items={[
              { key:'request', label:'① 请求信息', children: fragmentMeta ? <div>
                  <Space wrap style={{ marginBottom:12 }}>
                    <Tag color="geekblue">{fragmentMeta.model}</Tag><Tag>第 {fragmentMeta.episode} 集</Tag>
                    <Tag>单集原文：{fragmentMeta.source_len} 字符</Tag><Tag>完整请求：{fragmentMeta.prompt_len} 字符</Tag>
                    <Tag>temperature：{fragmentMeta.temperature}</Tag>
                  </Space>
                  <Paragraph strong>完整请求 Prompt</Paragraph>
                  <pre style={{ whiteSpace:'pre-wrap', maxHeight:420, overflow:'auto', background:'#f6f6f6', padding:10 }}>{fragmentPrompt}</pre>
                </div> : <Empty description="等待请求信息" /> },
              { key:'live', label:'② 实时返回', children: <pre style={{ whiteSpace:'pre-wrap', maxHeight:480, overflow:'auto', background:'#111827', color:'#d1fae5', padding:12 }}>{fragmentText || '等待模型返回…'}</pre> },
              { key:'diagnostics', label:'③ 输出诊断', children: fragmentDiagnostics ? <div>
                  <Space wrap style={{ marginBottom:12 }}>
                    <Tag color={fragmentDiagnostics.truncated ? 'error' : 'success'}>{fragmentDiagnostics.truncated ? '已达到输出上限' : `停止原因：${fragmentDiagnostics.finish_reason || '未返回'}`}</Tag>
                    <Tag>实际模型：{fragmentDiagnostics.response_model || '—'}</Tag>
                    <Tag>输入 Token：{fragmentDiagnostics.usage?.prompt_tokens ?? '—'}</Tag>
                    <Tag>输出 Token：{fragmentDiagnostics.usage?.completion_tokens ?? '—'}</Tag>
                    <Tag>总 Token：{fragmentDiagnostics.usage?.total_tokens ?? '—'}</Tag>
                  </Space>
                  {fragmentDiagnostics.truncated && <Alert type="error" showIcon message="模型达到单次输出 Token 上限，片段结果已截断" />}
                </div> : <Empty description="流式结束后显示" /> },
              { key:'raw', label:'④ AI 原始返回', children: fragmentRaw ? <pre style={{ whiteSpace:'pre-wrap', maxHeight:480, overflow:'auto', background:'#f6f6f6', padding:10 }}>{fragmentRaw}</pre> : <Empty description="流式结束后显示" /> },
            ]} />
            <div style={{ marginTop:12, textAlign:'right' }}><Space>
              {fragmentStreaming && <Tag color="processing">拆解中…</Tag>}
              {!fragmentStreaming && fragmentDiagnostics?.truncated && <Tag color="error">输出已截断</Tag>}
              {!fragmentStreaming && fragmentRaw && !fragmentDiagnostics?.truncated && <Tag color="success">已完成</Tag>}
              <Button disabled={fragmentStreaming} onClick={()=>setFragmentModalOpen(false)}>关闭</Button>
            </Space></div>
          </Modal>

          {/* 流式拆解弹窗：Tabs 切换"请求/实时/原始" */}
          <Modal title={streaming ? '🔄 AI 资产拆解中…' : '✅ 资产拆解结果'}
                 open={streamModalOpen}
                 onCancel={()=>{ if (!streaming) setStreamModalOpen(false); }}
                 width={860} footer={null} destroyOnClose
                 maskClosable={!streaming}>
            <Tabs defaultActiveKey="stream"
                  items={[
                    { key:'stream', label:'② AI 实时返回',
                      children: (
                        <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:480, overflow:'auto', margin:0, fontFamily:'inherit', fontSize:13, lineHeight:1.7, background:'#fafafa', padding:12, borderRadius:4 }}>
                          {streamText || (streaming ? '（等待输出…）' : '（无）')}
                        </pre>
                      )
                    },
                    { key:'meta', label:'① 请求了什么',
                      children: streamMeta ? (
                        <Tabs activeKey={metaTab} onChange={setMetaTab} size='small'
                              items={[
                                { key:'overview', label:'概览',
                                  children: (
                                    <div>
                                      <Space wrap style={{ marginBottom:12 }}>
                                        <Tag color="blue">模型：{streamMeta.model || '—'}</Tag>
                                        <Tag>剧本长度：{streamMeta.script_len} 字符</Tag>
                                        <Tag>分集数：{streamMeta.episodes}</Tag>
                                        <Tag color="purple">{streamMeta.request_mode === 'single' ? '完整剧本单次请求' : `分 ${streamMeta.batches} 批拆解`}</Tag>
                                        {streamMeta.prompt_len && <Tag>完整请求：{streamMeta.prompt_len} 字符</Tag>}
                                        <Tag>模板长度：{streamMeta.template_len} 字符</Tag>
                                        <Tag>temperature：{streamMeta.temperature}</Tag>
                                        {streamBatch && <Tag color="processing">当前：{streamBatch.label || `第 ${streamBatch.index}/${streamBatch.total} 批`}</Tag>}
                                      </Space>
                                      <div style={{ fontSize:12, color:'#888', margin:'6px 0' }}>系统提示词：</div>
                                      <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:140, overflow:'auto', margin:0, fontSize:12, background:'#fff', padding:8, borderRadius:4 }}>
                                        {streamMeta.system || '（无）'}
                                      </pre>
                                    </div>
                                  )
                                },
                                { key:'template', label:'模板全文（' + (streamMeta.template_len || 0) + ' 字符）',
                                  children: (
                                    <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:520, overflow:'auto', margin:0, fontSize:12, background:'#fff', padding:8, borderRadius:4 }}>
                                      {streamMeta.template || '（无）'}
                                    </pre>
                                  )
                                },
                                { key:'batch', label:(
                                    <span>{streamMeta.request_mode === 'single' ? '完整请求 prompt' : '本批完整 prompt'}{streamPrompts[streamPromptIdx] ? '（' + streamPrompts[streamPromptIdx].length + ' 字符）' : ''}</span>
                                  ),
                                  children: (
                                    <div>
                                      <Space wrap style={{ marginBottom:8 }}>
                                        {Object.keys(streamPrompts).map(idx => (
                                          <Button key={idx} size='small'
                                                  type={Number(idx) === streamPromptIdx ? 'primary' : 'default'}
                                                  onClick={()=>setStreamPromptIdx(Number(idx))}>
                                            第 {idx} 批
                                          </Button>
                                        ))}
                                      </Space>
                                      <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:520, overflow:'auto', margin:0, fontSize:12, background:'#fff', padding:8, borderRadius:4 }}>
                                        {streamPrompts[streamPromptIdx] || '（等待该批 prompt 推送…）'}
                                      </pre>
                                    </div>
                                  )
                                },
                              ]} />
                      ) : <Empty description="尚未发起请求" />
                    },
                    { key:'diagnostics', label:'③ 输出诊断',
                      children: streamDiagnostics ? (
                        <div>
                          <Space wrap style={{ marginBottom:12 }}>
                            <Tag color={streamDiagnostics.truncated ? 'error' : 'success'}>
                              {streamDiagnostics.truncated ? '已达到输出上限' : `停止原因：${streamDiagnostics.finish_reason || '未返回'}`}
                            </Tag>
                            <Tag>实际模型：{streamDiagnostics.response_model || '—'}</Tag>
                            <Tag>输入 Token：{streamDiagnostics.usage?.prompt_tokens ?? '—'}</Tag>
                            <Tag>输出 Token：{streamDiagnostics.usage?.completion_tokens ?? '—'}</Tag>
                            <Tag>总 Token：{streamDiagnostics.usage?.total_tokens ?? '—'}</Tag>
                            <Tag>输出字符：{streamDiagnostics.output_chars ?? '—'}</Tag>
                          </Space>
                          {streamDiagnostics.truncated && (
                            <Alert type="error" showIcon message="模型因单次输出 Token 达到上限而截断（finish_reason=length）" />
                          )}
                          {streamDiagnostics.stream_error && (
                            <Alert type="error" showIcon message="流式连接异常" description={streamDiagnostics.stream_error} />
                          )}
                        </div>
                      ) : <Empty description="流式结束后显示停止原因与 Token 用量" />
                    },
                    { key:'raw', label:'④ AI 原始返回',
                      children: streamRaw ? (
                        <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:480, overflow:'auto', margin:0, fontSize:12, background:'#fff', padding:8, borderRadius:4 }}>
                          {streamRaw}
                        </pre>
                      ) : <Empty description="流式结束后显示" />
                    },
                  ]} />
            <div style={{ marginTop:12, textAlign:'right' }}>
              <Space>
                {streaming && <Tag color="processing">生成中…</Tag>}
                {!streaming && streamDiagnostics?.truncated && <Tag color="error">输出已截断</Tag>}
                {!streaming && streamText && !streamDiagnostics?.truncated && <Tag color="success">已完成</Tag>}
                <Button onClick={()=>setStreamModalOpen(false)} disabled={streaming}>关闭</Button>
              </Space>
            </div>
          </Modal>
        </Layout>
      );
    }

    function SplitTasksView({ records, details, loading, onRefresh, onLoadDetail }) {
      const statusMeta = {
        queued:{color:'default',text:'等待执行'}, running:{color:'processing',text:'执行中'},
        succeeded:{color:'success',text:'成功'}, failed:{color:'error',text:'失败'},
      };
      const formatJson = value => value ? JSON.stringify(value, null, 2) : '暂无';
      const columns = [
        {title:'项目',dataIndex:'project',width:180,ellipsis:true},
        {title:'集数',width:150,render:(_,row)=><Space direction="vertical" size={0}><Text strong>{row.episode_title || `第${row.episode}集`}</Text><Text type="secondary">第 {row.batch_position}/{row.batch_total} 个</Text></Space>},
        {title:'状态',width:105,render:(_,row)=>{const meta=statusMeta[row.status]||statusMeta.queued;return <Tag color={meta.color}>{meta.text}</Tag>;}},
        {title:'进度',width:250,render:(_,row)=><div><Progress percent={Number(row.progress||0)} status={row.status==='failed'?'exception':row.status==='succeeded'?'success':'active'} size="small"/><Text type="secondary">{row.stage || '-'}</Text></div>},
        {title:'基本信息',width:210,render:(_,row)=><Space direction="vertical" size={0}><Text>模型：{row.model || '-'}</Text><Text>输入：{row.prompt_len || 0} 字符</Text><Text>返回：{row.output_chars || 0} 字符</Text><Text>片段：{row.count || 0}</Text></Space>},
        {title:'创建时间',dataIndex:'created_at',width:190},
      ];
      return <div>
        <Space style={{marginBottom:16}}><Button onClick={()=>onRefresh()} loading={loading}>刷新</Button><Text type="secondary">任务按提交顺序逐个执行；执行记录保存在对应项目目录。</Text></Space>
        <Table rowKey="id" loading={loading} dataSource={records} columns={columns} scroll={{x:1100}} pagination={{pageSize:20}}
          expandable={{onExpand:(expanded,row)=>{if(expanded) onLoadDetail(row);},expandedRowRender:row=>{const detail=details[row.id]; return <div style={{padding:8}}>
            {row.error_message && <Alert type="error" showIcon message="失败原因" description={row.error_message} style={{marginBottom:12}}/>}
            <Descriptions bordered size="small" column={3} style={{marginBottom:12}}>
              <Descriptions.Item label="任务 ID">{row.id}</Descriptions.Item><Descriptions.Item label="批次 ID">{row.batch_id}</Descriptions.Item><Descriptions.Item label="集数">{row.episode}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{row.started_at || '-'}</Descriptions.Item><Descriptions.Item label="完成时间">{row.finished_at || '-'}</Descriptions.Item><Descriptions.Item label="总时长">{row.total_seconds ? `${row.total_seconds}秒` : '-'}</Descriptions.Item>
            </Descriptions>
            {!detail ? <Spin tip="正在加载任务详情"/> : <Collapse items={[
              {key:'request',label:'原始请求',children:<pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word',maxHeight:520,overflow:'auto'}}>{formatJson(detail.request)}</pre>},
              {key:'response',label:'真实返回',children:<pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word',maxHeight:520,overflow:'auto'}}>{detail.raw_response || '暂无'}</pre>},
              {key:'diagnostics',label:'返回诊断',children:<pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word'}}>{formatJson(detail.diagnostics)}</pre>},
              {key:'result',label:'解析结果',children:<pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word',maxHeight:520,overflow:'auto'}}>{formatJson(detail.result)}</pre>},
            ]}/>} 
          </div>;}}}
        />
      </div>;
    }

    function VideoTasksView({ records, loading, onRefresh, onOpenProject }) {
      const [requestRow, setRequestRow] = useState(null);
      const [previewRow, setPreviewRow] = useState(null);
      const statusMeta = {
        creating:['提交中','processing'], queued:['排队中','warning'], running:['生成中','processing'], processing:['生成中','processing'],
        succeeded:['已完成','success'], failed:['失败','error'], cancelled:['已取消','default'], expired:['已过期','default'],
      };
      const timeText = value => {
        if (!value) return '—';
        const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12:false });
      };
      const statusTag = status => {
        const meta = statusMeta[status] || [status || '未知','default'];
        return <Tag color={meta[1]} style={{margin:0}}>{meta[0]}</Tag>;
      };
      const requestPayload = row => {
        const request = row.request || {};
        return request.api_payload || {
          model: request.model || row.model,
          content: [{type:'text', text:request.prompt || ''}],
          resolution: request.resolution,
          ratio: request.ratio,
          duration: request.duration,
          generate_audio: request.generate_audio,
          watermark: request.watermark,
        };
      };
      const requestText = useMemo(
        () => requestRow ? JSON.stringify(requestPayload(requestRow), null, 2) : '',
        [requestRow]
      );
      const copyRequest = async () => {
        if (!requestText) return;
        try {
          if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(requestText);
          } else {
            const textarea = document.createElement('textarea');
            textarea.value = requestText;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            const copied = document.execCommand('copy');
            document.body.removeChild(textarea);
            if (!copied) throw new Error('copy failed');
          }
          message.success('完整请求信息已复制');
        } catch (error) {
          message.error('复制失败，请在浮窗中手动选择复制');
        }
      };
      return (
        <div>
          <Space style={{width:'100%',justifyContent:'space-between',marginBottom:16}}>
            <div><Title level={4} style={{margin:0}}>视频生成任务</Title><Text type="secondary">共 {records.length} 条任务，可在卡片中直接播放生成结果</Text></div>
            <Button loading={loading} onClick={()=>onRefresh(true)}>刷新</Button>
          </Space>
          <Alert style={{marginBottom:18}} type="info" showIcon message="Token 消耗以视频接口实际返回为准；接口未返回 usage 时显示“未返回”。" />
          <Spin spinning={loading}>
            {!records.length && !loading ? <Empty description="暂无视频生成任务" /> : (
              <div className="video-task-grid">
                {records.map(row=>{
                  const req = row.request || {};
                  const generating = ['creating','queued','running','processing'].includes(row.status);
                  return <Card key={row.id} className="video-task-card">
                    <div className="video-task-preview">
                      <div className="video-task-preview-status">{statusTag(row.status)}</div>
                      {row.video_url ? (<>
                        <video src={row.video_url} controls preload="metadata" playsInline />
                        <Button className="video-task-preview-action" size="small" onClick={()=>setPreviewRow(row)}>放大预览</Button>
                      </>) : (
                        <div className="video-task-preview-empty">
                          {generating ? <><Spin /><div style={{marginTop:12}}>视频正在生成</div></> : row.error_message
                            ? <Tooltip title={row.error_message}><Text type="danger">生成失败，悬停查看原因</Text></Tooltip>
                            : <Text style={{color:'#aeb5c1'}}>暂无视频结果</Text>}
                        </div>
                      )}
                    </div>
                    <div className="video-task-card-body">
                      <div className="video-task-card-title">
                        <div style={{minWidth:0}}>
                          <Button type="link" style={{padding:0,height:'auto',maxWidth:'100%',fontWeight:600}} onClick={()=>onOpenProject(row.project)}>{row.project || '未命名剧'}</Button>
                          <div><Text type="secondary">第 {row.episode || '—'} 集 · 片段 {row.fragment_index || '—'}</Text></div>
                        </div>
                        <Text type="secondary" style={{fontSize:12,whiteSpace:'nowrap'}}>{timeText(row.created_at)}</Text>
                      </div>
                      <div className="video-task-meta">
                        <div className="video-task-meta-item"><div className="video-task-meta-label">模型</div><Tooltip title={row.model}><div className="video-task-meta-value">{row.model || '—'}</div></Tooltip></div>
                        <div className="video-task-meta-item"><div className="video-task-meta-label">Token 消耗</div><div className="video-task-meta-value">{row.token_usage?.total_tokens ?? '未返回'}</div></div>
                        <div className="video-task-meta-item"><div className="video-task-meta-label">生成规格</div><div className="video-task-meta-value">{req.resolution || '—'} · {req.ratio || '—'}</div></div>
                        <div className="video-task-meta-item"><div className="video-task-meta-label">视频时长</div><div className="video-task-meta-value">{req.duration ? `${req.duration} 秒` : '—'}</div></div>
                      </div>
                      <Button type="link" style={{padding:'10px 0 0',height:'auto'}} onClick={()=>setRequestRow(row)}>完整请求信息</Button>
                      <div className="video-task-card-footer">
                        <Text type="secondary" ellipsis style={{fontSize:12,maxWidth:'100%'}}>任务 ID：{row.id || '—'}</Text>
                      </div>
                    </div>
                  </Card>;
                })}
              </div>
            )}
          </Spin>
          <Modal
            title="完整请求信息"
            open={Boolean(requestRow)}
            onCancel={()=>setRequestRow(null)}
            width="min(960px, 92vw)"
            footer={[
              <Button key="copy" type="primary" onClick={copyRequest}>复制完整请求</Button>,
              <Button key="close" onClick={()=>setRequestRow(null)}>关闭</Button>,
            ]}
          >
            {requestRow && <>
              <Descriptions size="small" bordered column={2} style={{marginBottom:12}}>
                <Descriptions.Item label="项目">{requestRow.project || '—'}</Descriptions.Item>
                <Descriptions.Item label="集数 / 片段">第 {requestRow.episode || '—'} 集 / 片段 {requestRow.fragment_index || '—'}</Descriptions.Item>
                <Descriptions.Item label="模型">{requestRow.model || '—'}</Descriptions.Item>
                <Descriptions.Item label="任务 ID">{requestRow.id || '—'}</Descriptions.Item>
              </Descriptions>
              <pre style={{margin:0,padding:14,maxHeight:'62vh',overflow:'auto',whiteSpace:'pre-wrap',wordBreak:'break-all',background:'#f6f7f9',border:'1px solid #e7e9ee',borderRadius:8,fontSize:12,lineHeight:1.55}}>{requestText}</pre>
            </>}
          </Modal>
          <Modal
            className="video-task-preview-modal"
            title={null}
            open={Boolean(previewRow)}
            onCancel={()=>setPreviewRow(null)}
            width="min(1280px, 94vw)"
            centered
            footer={null}
            destroyOnHidden
          >
            {previewRow?.video_url && <video src={previewRow.video_url} controls autoPlay playsInline />}
          </Modal>
        </div>
      );
    }

    const BASIC_SETTING_PRESETS = {
      era_background: ['现代都市','古代架空','民国','未来科幻'],
      overall_style: ['写实电影感','都市情感短剧','黑色悬疑','史诗灾难'],
      camera_equipment: ['Arri Alexa 65 + Panavision Anamorphic','ARRI Alexa Mini LF + Cooke S8/i','Sony Venice 2 + Zeiss Supreme Prime'],
      overall_tone: ['低饱和冷色','暖黄色','冷暖对比','自然中性色'],
      lighting_tone: ['高反差电影光','柔和自然光','低照度雨夜光'],
      camera_rhythm: ['克制舒缓','快节奏短剧','紧张手持','情绪慢镜'],
    };
    const DEFAULT_NEGATIVE_PROMPT = '模糊，变形，扭曲，多余手指，缺少手指，肢体融合，低质量，低分辨率，水印，字幕，文字，logo，卡通风格，动画风格，油画风格，过度曝光，欠曝光，噪点';

    function BasicSettingsView({ settings, onChange, onSave, saving, visualStyle, onAnalyzeStyle, styleAnalyzing }) {
      if (!settings) return <Spin tip="加载基本设定…" />;
      const update = (key, value) => onChange({ ...settings, [key]: value });
      const presetInput = (key, placeholder) => (
        <AutoComplete style={{ width:'100%' }} value={settings[key] || ''}
                      options={BASIC_SETTING_PRESETS[key].map(value => ({ value }))}
                      onChange={value=>update(key, value)} placeholder={placeholder}
                      filterOption={(input, option)=>(option?.value || '').toLowerCase().includes(input.toLowerCase())} />
      );
      const fieldStyle = { marginBottom:18 };
      const labelStyle = { display:'block', marginBottom:7, fontWeight:600 };
      return <Card style={{ maxWidth:1000 }}>
        <Alert type="info" showIcon style={{ marginBottom:20 }}
               message="视频比例在此统一管理，并用于 Seedance 视频生成；模型固定为 Seedance mini，清晰度固定为 480P。" />
        <Row gutter={24}>
          <Col xs={24} md={12}>
            <div style={fieldStyle}><Text style={labelStyle}>1. 年代背景</Text>{presetInput('era_background','输入或选择年代背景')}</div>
            <div style={fieldStyle}><Text style={labelStyle}>2. 整体风格</Text>{presetInput('overall_style','输入或选择整体风格')}</div>
            <div style={fieldStyle}><Text style={labelStyle}>3. 是否仿真人</Text><Radio.Group value={settings.photorealistic} onChange={e=>update('photorealistic',e.target.value)}><Radio value={true}>true</Radio><Radio value={false}>false</Radio></Radio.Group></div>
            <div style={fieldStyle}><Text style={labelStyle}>4. 视频比例（不传给 AI）</Text><Radio.Group value={settings.video_ratio} onChange={e=>update('video_ratio',e.target.value)}><Space direction="vertical"><Radio value="9:16 竖屏">9:16 竖屏</Radio><Radio value="16:9 横屏">16:9 横屏</Radio><Radio value="2.39:1 宽银幕">2.39:1 宽银幕</Radio></Space></Radio.Group></div>
            <div style={fieldStyle}><Text style={labelStyle}>5. 清晰度（不传给 AI）</Text><Radio.Group value={settings.resolution} onChange={e=>update('resolution',e.target.value)}><Radio value="1080P">1080P</Radio><Radio value="4K">4K</Radio><Radio value="8K">8K</Radio></Radio.Group></div>
            <div style={fieldStyle}><Text style={labelStyle}>6. 拍摄设备</Text>{presetInput('camera_equipment','输入或选择拍摄设备')}</div>
          </Col>
          <Col xs={24} md={12}>
            <div style={fieldStyle}><Text style={labelStyle}>7. 整体色调</Text>{presetInput('overall_tone','输入或选择整体色调')}</div>
            <div style={fieldStyle}><Text style={labelStyle}>8. 光影基调</Text>{presetInput('lighting_tone','输入或选择光影基调')}</div>
            <div style={fieldStyle}><Text style={labelStyle}>9. 镜头节奏</Text>{presetInput('camera_rhythm','输入或选择镜头节奏')}</div>
            <div style={fieldStyle}><Text style={labelStyle}>10. 解说剧形式</Text><Radio.Group value={settings.narrated_drama} onChange={e=>update('narrated_drama',e.target.value)}><Radio value={true}>true</Radio><Radio value={false}>false</Radio></Radio.Group></div>
            <div style={fieldStyle}><Text style={labelStyle}>11. 特殊要求</Text><Input.TextArea rows={3} value={settings.special_requirements || ''} onChange={e=>update('special_requirements',e.target.value)} placeholder="如：少用大特写、避免大幅度手持、突出人物微表情" /></div>
            <div style={fieldStyle}>
              <Space style={{ marginBottom:7 }}><Text strong>12. negative_prompt</Text><Button size="small" onClick={()=>update('negative_prompt',DEFAULT_NEGATIVE_PROMPT)}>填入默认内容</Button><Button size="small" onClick={()=>update('negative_prompt','')}>清空</Button></Space>
              <Input.TextArea rows={5} value={settings.negative_prompt || ''} onChange={e=>update('negative_prompt',e.target.value)} placeholder="默认为空，可输入负面提示词或使用默认内容" />
            </div>
          </Col>
        </Row>
        <Divider />
        <Space>
          <Button type="primary" loading={saving} onClick={onSave}>保存并自动更新视觉风格</Button>
          <Button loading={styleAnalyzing} disabled={saving} onClick={onAnalyzeStyle}>手动重新分析视觉风格</Button>
          {visualStyle?.unified_prompt ? <Tag color="green">风格母版已固化</Tag> : <Tag color="orange">尚未生成风格母版</Tag>}
        </Space>
        <Alert style={{marginTop:18}} type={visualStyle?.unified_prompt?'success':'warning'} showIcon
               message={visualStyle?.style_name || '保存基本设定后将自动分析并固化统一视觉风格'}
               description={visualStyle?.unified_prompt ? <div><Paragraph style={{whiteSpace:'pre-wrap',margin:'8px 0'}}>{visualStyle.summary}</Paragraph><Text strong>统一风格提示词</Text><Paragraph copyable style={{whiteSpace:'pre-wrap',marginTop:6}}>{visualStyle.unified_prompt}</Paragraph>{visualStyle.negative_prompt && <><Text strong>统一风格反向提示词</Text><Paragraph copyable style={{whiteSpace:'pre-wrap',marginTop:6}}>{visualStyle.negative_prompt}</Paragraph></>}</div> : '资产内容会先独立分析，之后系统把这份风格母版原样注入所有最终图片提示词，避免每个资产各自理解风格。'} />
      </Card>;
    }

    function ShotsView({ shots, source, onGenerate, onRefresh, generating, progress, targetDuration, onDurationChange }) {
      const available = [...(shots?.episodes || [])].sort((a,b)=>Number(a.episode)-Number(b.episode));
      const [selectedEpisode, setSelectedEpisode] = useState(Number(available[0]?.episode || 1));
      useEffect(()=>{
        if (available.length && !available.some(item=>Number(item.episode)===Number(selectedEpisode))) setSelectedEpisode(Number(available[0].episode));
      }, [shots]);
      const ep = available.find(item => Number(item.episode) === Number(selectedEpisode));
      const fragments = ep?.shots || [];
      const original = ep?.source || source || '';
      if (!ep) return <Empty description="点击“拆解片段”选择集数，任务完成后刷新查看拆解结果" />;
      const generateControls = (
        <Space wrap align="center">
          <Select value={selectedEpisode} style={{width:150}} onChange={value=>setSelectedEpisode(Number(value))} options={available.map(item=>({value:Number(item.episode),label:item.title || `第${item.episode}集`}))}/>
          <Button onClick={onRefresh}>刷新结果</Button>
          <Text>目标总时长</Text>
          <InputNumber min={1} precision={0} value={targetDuration} onChange={onDurationChange} addonAfter="秒" style={{width:130}} />
          <Button type="primary" loading={generating} disabled={!fragments.length} onClick={()=>onGenerate(selectedEpisode)}>生成 Seedance 提示词</Button>
        </Space>
      );
      return <div>
        {(generating || progress.completed > 0) && <Card size="small" style={{marginBottom:12}}>
          <Space wrap style={{marginBottom:8}}>
            <Tag>总片段数：{progress.total || fragments.length}</Tag>
            <Tag color="green">已完成片段数：{progress.completed || 0}</Tag>
            <Tag color="blue">当前正在处理：{progress.fragment_index || progress.current || 0}{progress.label ? `（${progress.label}）` : ''}</Tag>
          </Space>
          <Progress percent={progress.percent || 0} status={generating ? 'active' : 'normal'} />
        </Card>}
        <Row gutter={16} align="top">
          <Col xs={24} lg={12}>
            <Card title={`${ep.title || `第 ${selectedEpisode} 集`}原文`} styles={{ body:{ maxHeight:'68vh', overflow:'auto' } }}>
              <pre style={{ whiteSpace:'pre-wrap', wordBreak:'break-word', margin:0, fontFamily:'inherit', lineHeight:1.8 }}>{original}</pre>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title={`拆解片段（${fragments.length}）`} extra={generateControls} styles={{ body:{ maxHeight:'68vh', overflow:'auto' } }}>
              {fragments.map((item, index) => (
                <Card size="small" key={item.id || index} style={{ marginBottom:12 }} title={
                  <Space wrap><Text strong>{item.id || `片段${index+1}`}</Text><Tag>{item.scene}</Tag><Tag color="blue">{item.time}</Tag></Space>
                } extra={<Button size="small" loading={generating && progress.fragment_index===index+1} disabled={generating} onClick={()=>onGenerate(selectedEpisode, index+1)}>生成 Seedance 提示词</Button>}>
                  <Space wrap style={{ marginBottom:8 }}>
                    {(item.characters || []).map(name => <Tag color="purple" key={name}>{name}</Tag>)}
                  </Space>
                  <Paragraph style={{ whiteSpace:'pre-wrap' }}>{item.text}</Paragraph>
                  <Text type="secondary">拆解原因：{item.reason}</Text>
                </Card>
              ))}
            </Card>
          </Col>
        </Row>
      </div>;
    }

    function SeedanceVideoStudio({ project, data, assets=[], onAssetsChange=null, settings={}, episodes=[], onEpisodeChange, shots=null, onSplitNeeded, onOpenPromptSettings=null, onRegenerateFragment=null, generatingFragment=false, activeFragmentIndex=null, progress=null, exchanges=null, exchangeIndex=null, modalOpen=false, onCloseModal=null }) {
      const api = async (url, opt={}) => {
        const response = await fetch(url, { headers:{'Content-Type':'application/json'}, ...opt });
        const result = await response.json();
        if (!response.ok) throw new Error(result?.detail || `请求失败（${response.status}）`);
        return result;
      };
      const list = data?.prompts || [];
      const currentEpisode = Number(data?.episode || (list[0]?.episode) || 1);
      const episodeOptions = (episodes || []).filter(ep => Number(ep.index) > 0).map(ep => ({ key: String(ep.index), label: `第 ${ep.index} 集 · ${ep.title || ''}` }));
      const currentShots = (shots?.episodes || []).find(item => Number(item.episode) === currentEpisode)?.shots || [];
      const [episodeMenuOpen, setEpisodeMenuOpen] = useState(false);
      const buildFragmentPromptText = (resultItem) => {
        const meta = (resultItem && resultItem.meta) || {};
        const fragments = (resultItem && resultItem.fragments) || [];
        const lines = [];
        if (meta['整体风格']) lines.push(`【整体风格】：${meta['整体风格']}`);
        const metaOrder = ['时代背景','拍摄设备','仿真人','解说剧形式'];
        metaOrder.forEach(key => {
          if (meta[key] !== undefined && meta[key] !== null && meta[key] !== '') lines.push(`【${key}】：${meta[key]}`);
        });
        Object.keys(meta).forEach(key => {
          if (['整体风格','时代背景','拍摄设备','仿真人','解说剧形式'].includes(key)) return;
          if (['duration','duration_sec','negative_prompt'].includes(key)) return;
          if (meta[key] !== undefined && meta[key] !== null && meta[key] !== '') lines.push(`【${key}】：${meta[key]}`);
        });
        const neg = (resultItem && (resultItem.negative_prompt || (meta && meta.negative_prompt))) || '';
        if (neg) lines.push(`【negative_prompt】：${neg}`);
        const shotBlocks = [];
        fragments.forEach((fragment) => {
          (fragment.shots || []).forEach((shot, shotIndex) => {
            const block = [`镜头${shotIndex + 1}`];
            const normalizedShot = Object.entries(shot || {}).reduce((fields, [rawKey, value]) => {
              const key = String(rawKey || '').trim().replace(/^[【\[]|[】\]]$/g, '').replace(/[：:]$/, '').trim();
              fields[key] = value;
              return fields;
            }, {});
            const visualAliases = ['画面内容','画面描述','视觉内容','镜头内容','画面'];
            const visualContent = visualAliases.map(key => normalizedShot[key]).find(value => value !== undefined && value !== null && value !== '')
              || ['画面首帧','画面中段','画面尾帧'].map(key => normalizedShot[key]).filter(Boolean).join(' ');
            if (visualContent) normalizedShot['画面内容'] = visualContent;
            ['景别','运镜','画面内容','焦点','光影','音效','画面首帧','画面构图','画面中段','画面尾帧','人物站位','人物状态','台词'].forEach(key => {
              if (normalizedShot[key] !== undefined && normalizedShot[key] !== null && normalizedShot[key] !== '') block.push(`【${key}】：${normalizedShot[key]}`);
            });
            if (normalizedShot.时长 !== undefined && normalizedShot.时长 !== null && normalizedShot.时长 !== '') block.push(`【时长】：${normalizedShot.时长}秒`);
            shotBlocks.push(block.join('\n'));
          });
        });
        if (shotBlocks.length) lines.push(shotBlocks.join('\n\n'));
        return lines.join('\n\n');
      };
      const switchEpisode = value => {
        if (!value || value === currentEpisode) { setEpisodeMenuOpen(false); return; }
        if (typeof onEpisodeChange === 'function') onEpisodeChange(value);
        setEpisodeMenuOpen(false);
      };
      const [selected, setSelected] = useState(0);
      const [promptDrafts, setPromptDrafts] = useState({});
      const [fragmentAssets, setFragmentAssets] = useState([]);
      const [fragmentAssetsLoading, setFragmentAssetsLoading] = useState(false);
      const [smartMatching, setSmartMatching] = useState(false);
      const [assetLibraryOpen, setAssetLibraryOpen] = useState(false);
      const [libraryAssetIds, setLibraryAssetIds] = useState([]);
      const [newAssetOpen, setNewAssetOpen] = useState(false);
      const [newAssetSaving, setNewAssetSaving] = useState(false);
      const [newAssetForm, setNewAssetForm] = useState({category:'character',parent_id:null,parent_name:'',item_name:'',file:null});
      const [assetLinkOpen, setAssetLinkOpen] = useState(false);
      const [assetLinkAsset, setAssetLinkAsset] = useState(null);
      const [assetLinkUrl, setAssetLinkUrl] = useState('');
      const [assetLinkMaterialId, setAssetLinkMaterialId] = useState('');
      const [assetLinkSaving, setAssetLinkSaving] = useState(false);
      const model = 'Seedance mini';
      const quality = '480P';
      const ratio = String(settings?.video_ratio || '9:16').split(' ')[0];
      const [videoTasks, setVideoTasks] = useState({});
      const [latestVideos, setLatestVideos] = useState({});
      const [videoLastFrameEnabled, setVideoLastFrameEnabled] = useState(true);
      const videoPollRefs = React.useRef({});
      const previewVideoRef = React.useRef(null);
      const [historyOpen, setHistoryOpen] = useState(false);
      const [historyLoading, setHistoryLoading] = useState(false);
      const [historyRecords, setHistoryRecords] = useState([]);
      const [historyFragment, setHistoryFragment] = useState(null);
      const [sequenceOpen, setSequenceOpen] = useState(false);
      const [sequenceIndex, setSequenceIndex] = useState(0);
      const sequenceVideoRef = React.useRef(null);
      const [quickCutContext, setQuickCutContext] = useState(null);
      const [quickCutOpen, setQuickCutOpen] = useState(false);
      const [quickCutStep, setQuickCutStep] = useState('select');
      const [availableVideos, setAvailableVideos] = useState([]);
      const [quickVideo, setQuickVideo] = useState(null);
      const [duration, setDuration] = useState(0);
      const [selection, setSelection] = useState([0,0]);
      const [deletedRanges, setDeletedRanges] = useState([]);
      const [exporting, setExporting] = useState(false);
      const [previewOnlyKeep, setPreviewOnlyKeep] = useState(true);
      const videoRef = React.useRef(null);
      const userPausedRef = React.useRef(false);
      const selectionRef = React.useRef([0,0]);
      const promptSourceRefs = React.useRef({});
      const selectedShot = currentShots[selected] || null;
      const currentFragmentIndex = Number(selectedShot?.fragment_index) || selected + 1;
      const item = list.find(entry => Number(entry?.fragment_index) === currentFragmentIndex) || null;
      const result = item?.result || {};
      const currentVideoTaskKey = `${currentEpisode}:${currentFragmentIndex}`;
      const videoTask = videoTasks[currentVideoTaskKey] || null;
      const previousFragmentVideo = currentFragmentIndex > 1 ? latestVideos[`${currentEpisode}:${currentFragmentIndex - 1}`] : null;
      const previousLastFrameUrl = previousFragmentVideo?.local_last_frame_url || previousFragmentVideo?.last_frame_url || '';
      const videoGenerating = ['creating','queued','running','processing'].includes(videoTask?.status);
      const previewVideoUrl = videoTask?.edited_file || videoTask?.video_url || videoTask?.content?.video_url || '';
      const sequenceVideos = currentShots.map((shot,index)=>{
        const fragmentIndex = Number(shot?.fragment_index) || index + 1;
        const task = videoTasks[`${currentEpisode}:${fragmentIndex}`] || {};
        const videoUrl = task.edited_file || task.video_url || task.content?.video_url;
        return videoUrl ? {fragmentIndex,videoUrl,label:`片段 ${String(index+1).padStart(2,'0')}`} : null;
      }).filter(Boolean);
      const currentSequenceVideo = sequenceVideos[sequenceIndex] || null;
      const openSequencePreview = () => {
        if (!sequenceVideos.length) return message.warning('当前集暂无已生成的视频片段');
        setSequenceIndex(0);
        setSequenceOpen(true);
      };
      const playNextSequenceVideo = () => {
        if (sequenceIndex < sequenceVideos.length - 1) setSequenceIndex(index=>index+1);
      };
      useEffect(()=>{
        if (!sequenceOpen || !sequenceVideoRef.current || !currentSequenceVideo) return;
        sequenceVideoRef.current.load();
        const playPromise = sequenceVideoRef.current.play();
        if (playPromise && playPromise.catch) playPromise.catch(()=>{});
      }, [sequenceOpen, sequenceIndex, currentSequenceVideo?.videoUrl]);
      const sourcePromptText = (() => {
        if (!item) return '';
        if (Array.isArray(result.fragments) && result.fragments.length) return buildFragmentPromptText(result);
        if (typeof result.prompt === 'string' && result.prompt) return result.prompt;
        if (typeof item.final_prompt === 'string' && item.final_prompt) return item.final_prompt;
        if (item.seedance && typeof item.seedance.prompt === 'string') return item.seedance.prompt;
        return buildFragmentPromptText(result);
      })();
      useEffect(() => {
        const previousSource = promptSourceRefs.current[currentVideoTaskKey];
        promptSourceRefs.current[currentVideoTaskKey] = sourcePromptText;
        if (previousSource === undefined || previousSource === sourcePromptText) return;
        setPromptDrafts(prev => {
          if (prev[currentVideoTaskKey] === undefined) return prev;
          const next = { ...prev };
          delete next[currentVideoTaskKey];
          return next;
        });
      }, [currentVideoTaskKey, sourcePromptText]);
      const promptText = promptDrafts[currentVideoTaskKey] !== undefined
        ? promptDrafts[currentVideoTaskKey]
        : sourcePromptText;
      const fragmentTime = (() => {
        if (!item) return '';
        const meta = result.meta || {};
        const fromFragment = (result.fragments || []).reduce((sum, fragment) => {
          if (typeof fragment.time === 'string') {
            const matched = fragment.time.match(/(\d+(?:\.\d+)?)/);
            if (matched) return sum + Number(matched[1]);
          }
          return sum + (fragment.shots || []).reduce((sub, shot) => sub + (Number(shot.时长) || 0), 0);
        }, 0);
        if (fromFragment) return String(fromFragment);
        if (typeof meta.duration === 'number') return String(meta.duration);
        if (typeof meta.duration_sec === 'number') return String(meta.duration_sec);
        if (typeof meta.time === 'string') return meta.time;
        if (typeof result.duration === 'number') return String(result.duration);
        return '';
      })();
      const currentAssetIds = fragmentAssets.map(asset=>Number(asset.id));
      const matchedAudioCharacters = fragmentAssets.filter(asset=>asset.category==='character').map(asset=>asset.parent_id ? assets.find(parent=>parent.id===asset.parent_id) : asset).filter((asset,index,list)=>asset?.audio_path && list.findIndex(item=>item?.id===asset.id)===index);
      const updatePrompt = value => setPromptDrafts(prev=>({...prev,[currentVideoTaskKey]:value}));
      const roleForAsset = asset => asset.category==='character' ? 'character' : asset.category;
      const fragmentAssetDisplayName = asset => {
        const name = String(asset?.name||'').trim();
        const state = String(asset?.state||'').trim();
        if (asset?.category==='character' && state && !isExtraCharacter(asset)) {
          return state===name || state.startsWith(`${name}-`) ? state : `${name}-${state.replace(/^-+/, '')}`;
        }
        return state || name || asset?.key || `资产${asset?.id||''}`;
      };
      const persistFragmentAssets = async nextAssets => {
        const payload = nextAssets.map(asset=>({asset_id:Number(asset.id),role:asset.role||roleForAsset(asset),mapping_text:asset.mapping_text||''}));
        await api(`/api/projects/${encodeURIComponent(project)}/episodes/${currentEpisode}/fragments/${currentFragmentIndex}/assets`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({assets:payload})});
        setFragmentAssets(nextAssets);
      };
      const loadFragmentAssets = async () => {
        if (!project || !currentFragmentIndex) return;
        setFragmentAssetsLoading(true);
        try {
          const response = await api(`/api/projects/${encodeURIComponent(project)}/episodes/${currentEpisode}/fragments/${currentFragmentIndex}/assets`);
          setFragmentAssets(response.assets || []);
        } catch (error) {
          message.error(error.message || String(error));
          setFragmentAssets([]);
        } finally { setFragmentAssetsLoading(false); }
      };
      useEffect(()=>{ loadFragmentAssets(); }, [project,currentEpisode,currentFragmentIndex]);
      const appendAssetMapping = (mappingText, sourcePrompt=promptText) => {
        if (!mappingText) return;
        const mappingSection = /\n*【(?:角色|场景|道具)资产映射】：[\s\S]*?(?=\n\s*【(?!(?:角色|场景|道具)资产映射)[^\n]+】|$)/g;
        const stripped = String(sourcePrompt||'').replace(mappingSection,'').trimEnd();
        updatePrompt(`${stripped}\n\n${mappingText}`.trim());
      };
      const smartMatchAssets = async () => {
        if (!promptText.trim()) return message.warning('当前片段镜头提示词为空');
        setSmartMatching(true);
        try {
          const response = await api(`/api/projects/${encodeURIComponent(project)}/episodes/${currentEpisode}/fragments/${currentFragmentIndex}/assets/smart-match`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shot_prompt:promptText})});
          setFragmentAssets(response.assets || []);
          appendAssetMapping(response.mapping_text || '');
          message.success(`已智能匹配 ${(response.assets||[]).length} 个本片段资产`);
        } catch (error) { message.error(error.message || String(error)); }
        finally { setSmartMatching(false); }
      };
      const removeFragmentAsset = async assetId => {
        const next = fragmentAssets.filter(asset=>Number(asset.id)!==Number(assetId));
        try { await persistFragmentAssets(next); message.success('已从本片段移除，不影响资产库'); }
        catch (error) { message.error(error.message || String(error)); }
      };
      const openFragmentAssetLink = asset => {
        setAssetLinkAsset(asset);
        setAssetLinkUrl(asset.image_url && /^https?:\/\//i.test(asset.image_url) ? asset.image_url : '');
        setAssetLinkMaterialId(asset.seedance_asset_id ? String(asset.seedance_asset_id).replace(/^asset:\/\//i,'') : '');
        setAssetLinkOpen(true);
      };
      const saveFragmentAssetLink = async () => {
        const imageUrl = assetLinkUrl.trim();
        const materialId = assetLinkMaterialId.trim();
        if (!/^https?:\/\/\S+$/i.test(imageUrl)) return message.warning('请输入有效的 http 或 https 公网图片链接');
        if (materialId && /\s/.test(materialId)) return message.warning('素材 ID 不能包含空格');
        setAssetLinkSaving(true);
        try {
          const seedanceAssetId = materialId.replace(/^asset:\/\//i,'');
          await api(`/api/projects/${encodeURIComponent(project)}/assets/${assetLinkAsset.id}/image-url`, {method:'POST',body:JSON.stringify({image_url:imageUrl,seedance_asset_id:seedanceAssetId})});
          setFragmentAssets(current=>current.map(asset=>Number(asset.id)===Number(assetLinkAsset.id)?{...asset,image_url:imageUrl,seedance_asset_id:seedanceAssetId,image_path:null,status:'ready'}:asset));
          await onAssetsChange?.(); await loadFragmentAssets();
          setAssetLinkOpen(false); message.success(seedanceAssetId ? '链接和素材 ID 已更新，生成时优先使用素材 ID' : '公网链接已更新，生成时使用该链接');
        } catch (error) { message.error(error.message||String(error)); }
        finally { setAssetLinkSaving(false); }
      };
      const uploadFragmentAssetImage = async (assetId,file) => {
        if (!file) return false;
        const form = new FormData(); form.append('file',file);
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/assets/${assetId}/images/upload`,{method:'POST',body:form});
          const result = await response.json(); if (!response.ok) throw new Error(result.detail||'上传失败');
          const freshImageUrl = `${result.image?.image_url||`/api/projects/${encodeURIComponent(project)}/assets/${assetId}/image`}?v=${result.image?.id||Date.now()}`;
          setFragmentAssets(current=>current.map(asset=>Number(asset.id)===Number(assetId)?{...asset,image_path:result.image?.image_path||asset.image_path,image_url:freshImageUrl}:asset));
          await onAssetsChange?.(); await loadFragmentAssets(); message.success('本片段资产图片已更换');
        } catch (error) { message.error(error.message||String(error)); }
        return false;
      };
      const addLibraryAssets = async () => {
        const selectedAssets = assets.filter(asset=>libraryAssetIds.includes(Number(asset.id)));
        const merged = [...fragmentAssets];
        selectedAssets.forEach(asset=>{ if (!merged.some(item=>Number(item.id)===Number(asset.id))) merged.push({...asset,role:roleForAsset(asset),mapping_text:''}); });
        try { await persistFragmentAssets(merged); setAssetLibraryOpen(false); setLibraryAssetIds([]); message.success('已添加到本片段资产'); }
        catch (error) { message.error(error.message||String(error)); }
      };
      const createFragmentAsset = async () => {
        const category = newAssetForm.category;
        const parentName = String(newAssetForm.parent_name||'').trim();
        const itemName = String(newAssetForm.item_name||'').trim();
        if (!itemName || !newAssetForm.file) return message.warning('请填写名称并上传图片');
        setNewAssetSaving(true);
        try {
          let parentId = newAssetForm.parent_id ? Number(newAssetForm.parent_id) : null;
          if ((category==='character'||category==='scene') && !parentId) {
            if (!parentName) throw new Error(`请填写${category==='character'?'人物主图':'主场景'}名称`);
            const parent = await api(`/api/projects/${encodeURIComponent(project)}/assets`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category,name:parentName,state:'',episodes:[]})});
            parentId = Number(parent.id);
          }
          const parentAsset = assets.find(asset=>Number(asset.id)===parentId);
          const resolvedParentName = String(parentAsset?.name||parentName||'').trim();
          const resolvedItemName = category==='character' && resolvedParentName && !itemName.startsWith(`${resolvedParentName}-`)
            ? `${resolvedParentName}-${itemName.replace(/^-+/, '')}` : itemName;
          const childBody = category==='prop'
            ? {category:'prop',name:itemName,state:'',episodes:[currentEpisode]}
            : {category,name:resolvedParentName,state:resolvedItemName,parent_id:parentId,level:'secondary',episodes:[currentEpisode]};
          const created = await api(`/api/projects/${encodeURIComponent(project)}/assets`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(childBody)});
          const form = new FormData(); form.append('file',newAssetForm.file);
          const uploadResponse = await fetch(`/api/projects/${encodeURIComponent(project)}/assets/${created.id}/upload`,{method:'POST',body:form});
          const uploaded = await uploadResponse.json(); if (!uploadResponse.ok) throw new Error(uploaded.detail||'上传失败');
          await onAssetsChange?.();
          const fullAsset = {...created,...(uploaded.asset||{}),image_url:uploaded.image_url||created.image_url,role:roleForAsset(created),mapping_text:''};
          await persistFragmentAssets([...fragmentAssets,fullAsset]);
          setNewAssetOpen(false); setNewAssetForm({category:'character',parent_id:null,parent_name:'',item_name:'',file:null});
          message.success('新资产已创建并添加到本片段');
        } catch (error) { message.error(error.message||String(error)); }
        finally { setNewAssetSaving(false); }
      };
      const modelId = value => ({
        'Seedance mini': 'doubao-seedance-2-0-mini-260615',
        'Seedance 2.0 Fast': 'doubao-seedance-2-0-fast-260128',
        'Seedance 2.0': 'doubao-seedance-2-0-260128',
      }[value] || value);
      const parseVideoDuration = () => {
        const matched = String(fragmentTime || '').match(/(\d+(?:\.\d+)?)/);
        return Math.max(2, Math.min(12, Math.round(matched ? Number(matched[1]) : 5)));
      };
      const pollVideoTask = async (taskId, taskKey) => {
        window.clearTimeout(videoPollRefs.current[taskKey]);
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/videos/tasks/${encodeURIComponent(taskId)}`);
          const task = await response.json();
          if (!response.ok) throw new Error(task.detail || '查询视频任务失败');
          setVideoTasks(prev=>({...prev,[taskKey]:task}));
          if (task.status === 'succeeded') {
            delete videoPollRefs.current[taskKey];
            setLatestVideos(prev=>({...prev,[taskKey]:task}));
            message.success(`片段 ${String(task.fragment_index || '').padStart(2,'0')} 视频生成完成，已自动设为默认${task.local_last_frame_url || task.last_frame_url ? '，尾帧已保存' : ''}`);
            return;
          }
          if (['failed','cancelled','expired'].includes(task.status)) {
            delete videoPollRefs.current[taskKey];
            const detail = task.error && (task.error.message || task.error.code);
            message.error(`视频生成失败${detail ? `：${detail}` : ''}`);
            return;
          }
          videoPollRefs.current[taskKey] = window.setTimeout(()=>pollVideoTask(taskId, taskKey), 5000);
        } catch (error) {
          setVideoTasks(prev=>({...prev,[taskKey]:{...(prev[taskKey] || {}),status:'failed',error:{message:error.message}}}));
          delete videoPollRefs.current[taskKey];
          message.error(error.message);
        }
      };
      const generateVideo = async () => {
        if (!item) { message.warning('请先选择片段'); return; }
        if (!promptText.trim()) { message.warning('请先填写 Seedance 提示词'); return; }
        const episode = currentEpisode;
        const fragmentIndex = item.fragment_index || selected + 1;
        const taskKey = `${episode}:${fragmentIndex}`;
        setVideoTasks(prev=>({...prev,[taskKey]:{status:'creating',episode,fragment_index:fragmentIndex}}));
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/videos/generate`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
              episode,
              fragment_index:fragmentIndex,
              prompt:promptText,
              model:modelId(model),
              resolution:String(quality || '720P').toLowerCase(),
              ratio:String(ratio || '9:16').split(' ')[0],
              duration:parseVideoDuration(),
              generate_audio:true,
              watermark:false,
              use_last_frame:videoLastFrameEnabled,
              character_asset_ids:matchedAudioCharacters.map(asset=>Number(asset.id)),
              asset_ids:currentAssetIds,
            }),
          });
          const task = await response.json();
          if (!response.ok) throw new Error(task.detail || '创建视频任务失败');
          setVideoTasks(prev=>({...prev,[taskKey]:task}));
          message.success('视频生成任务已提交');
          pollVideoTask(task.id, taskKey);
        } catch (error) {
          setVideoTasks(prev=>({...prev,[taskKey]:{status:'failed',episode,fragment_index:fragmentIndex,error:{message:error.message}}}));
          message.error(error.message);
        }
      };
      useEffect(()=>()=>{
        Object.values(videoPollRefs.current).forEach(timer=>window.clearTimeout(timer));
      }, []);
      useEffect(()=>{
        let cancelled = false;
        fetch(`/api/projects/${encodeURIComponent(project)}/videos/latest-success?episode=${currentEpisode}`)
          .then(response=>response.ok ? response.json() : Promise.reject(new Error('加载历史视频失败')))
          .then(tasks=>{
            if (!cancelled) {
              setLatestVideos(tasks);
              setVideoTasks(prev=>({...tasks,...prev}));
            }
          })
          .catch(error=>{ if (!cancelled) message.error(error.message); });
        return ()=>{ cancelled = true; };
      }, [project, currentEpisode]);
      useEffect(()=>{
        if (previewVideoRef.current) {
          previewVideoRef.current.pause();
          previewVideoRef.current.currentTime = 0;
        }
      }, [currentVideoTaskKey, previewVideoUrl]);
      const formatTime = value => `${String(Math.floor(value/60)).padStart(2,'0')}:${String(Math.floor(value%60)).padStart(2,'0')}.${Math.floor((value%1)*10)}`;
      const loadVideos = async () => {
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/quick-cut/videos`);
          if (!response.ok) throw new Error(await response.text());
          const videos = await response.json();
          setAvailableVideos(videos);
          return videos;
        } catch (error) { message.error(error.message); return []; }
      };
      const openQuickCut = async (fragmentIndex=null, sourceTask=null) => {
        setQuickCutOpen(true);
        const videos = await loadVideos();
        const localName = sourceTask?.content?.local_video;
        const matched = localName ? videos.find(video=>video.name===localName) : null;
        if (fragmentIndex && matched) {
          setQuickCutContext({episode:currentEpisode,fragment_index:fragmentIndex});
          chooseVideo(matched);
          setQuickCutStep('edit');
        } else if (videos.length) {
          setQuickCutContext(null);
          chooseVideo(matched || videos[0]);
          setQuickCutStep('edit');
        } else {
          setQuickCutContext(null);
          setQuickCutStep('select');
        }
      };
      const chooseVideo = video => {
        setQuickVideo(video);
        setDuration(0);
        setSelection([0,0]);
        selectionRef.current = [0,0];
        setDeletedRanges([]);
      };
      const uploadVideo = async options => {
        const form = new FormData();
        form.append('file', options.file);
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/quick-cut/upload`, {method:'POST',body:form});
          if (!response.ok) throw new Error(await response.text());
          const video = await response.json();
          chooseVideo(video);
          setAvailableVideos([]);
          setQuickCutStep('edit');
          options.onSuccess(video);
        } catch (error) { options.onError(error); message.error(`上传失败：${error.message}`); }
      };
      const onVideoReady = event => {
        const value = Number(event.currentTarget.duration || 0);
        setDuration(value);
        setSelection([0,value]);
        const first = keepRanges()[0];
        if (first) {
          event.currentTarget.currentTime = first[0];
          setSelection([first[0],first[1]]);
        }
      };
      const seekTo = time => {
        const player = videoRef.current;
        if (!player) return;
        const target = Math.max(0, Math.min(Number(time||0), player.duration || duration || 0));
        if (Math.abs(player.currentTime - target) > 0.05) player.currentTime = target;
      };
      const onSelectionChange = next => {
        const previous = selectionRef.current;
        setSelection(next);
        selectionRef.current = next;
        if (Math.abs(next[0] - previous[0]) > 0.001) seekTo(next[0]);
        else if (Math.abs(next[1] - previous[1]) > 0.001) seekTo(next[1]);
      };
      const onSelectionCommit = next => {
        setSelection(next);
        selectionRef.current = next;
        seekTo(next[0]);
      };
      const onTimeUpdate = event => {
        const player = event.currentTarget;
        const time = player.currentTime;
        const keep = keepRanges();
        if (!keep.length) return;
        if (!previewOnlyKeep) return;
        if (time < keep[0][0]) {
          player.currentTime = keep[0][0];
          return;
        }
        const last = keep[keep.length-1];
        if (time >= last[1]) {
          player.currentTime = keep[0][0];
          return;
        }
        for (const [start,end] of keep) {
          if (time >= start && time < end) return;
        }
        let target = keep[0][0];
        for (const [start,end] of keep) {
          if (time < start) { target = start; break; }
          target = end;
        }
        player.currentTime = target;
      };
      const onPlay = () => { userPausedRef.current = false; };
      const onPause = () => { userPausedRef.current = true; };
      const mergeRanges = ranges => ranges.sort((a,b)=>a[0]-b[0]).reduce((all,current)=>{
        const last = all[all.length-1];
        if (last && current[0] <= last[1]) last[1] = Math.max(last[1],current[1]);
        else all.push([...current]);
        return all;
      },[]);
      const deleteSelection = () => {
        if (selection[1]-selection[0] < 0.05) return message.warning('请选择需要删除的时间段');
        setDeletedRanges(prev=>mergeRanges([...prev,selection]));
        const next = keepRanges();
        if (next.length) {
          const target = next.find(([start])=>start >= selection[0]) || next[0];
          seekTo(target[0]);
        }
      };
      const keepOnlySelection = () => {
        const [start,end] = selection;
        if (end-start < 0.05) return message.warning('请选择需要保留的时间段');
        const removed = [];
        if (start >= 0.05) removed.push([0,start]);
        if (duration-end >= 0.05) removed.push([end,duration]);
        setDeletedRanges(removed);
        seekTo(start);
        message.success('已设置为仅保留所选片段');
      };
      const keepRanges = () => {
        const deleted = mergeRanges(deletedRanges.map(range=>[...range]));
        const keep = [];
        let cursor = 0;
        deleted.forEach(([start,end])=>{
          if (start > cursor) keep.push([cursor,Math.min(start,duration)]);
          cursor = Math.max(cursor,end);
        });
        if (cursor < duration) keep.push([cursor,duration]);
        return keep.filter(range=>range[1]-range[0]>=0.05 && range[0] >= 0);
      };
      const saveQuickCut = async () => {
        const ranges = keepRanges();
        if (!ranges.length) return message.warning('不能删除整个视频');
        setExporting(true);
        try {
          if (quickCutContext) {
            const response = await fetch(`/api/projects/${encodeURIComponent(project)}/videos/quick-cut`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video_id:quickVideo.id,keep_ranges:ranges,output_name:'',episode:quickCutContext.episode,fragment_index:quickCutContext.fragment_index})});
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || '保存片段剪辑失败');
            const key = `${quickCutContext.episode}:${quickCutContext.fragment_index}`;
            setVideoTasks(prev=>({...prev,[key]:{...(prev[key] || {}),original_video_url:prev[key]?.video_url || prev[key]?.content?.video_url,video_url:result.video_url,edited_file:result.edited_file}}));
            setQuickCutOpen(false);
            message.success('剪辑结果已应用到当前片段');
            return;
          }
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/quick-cut/export`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video_id:quickVideo.id,keep_ranges:ranges,output_name:`${quickVideo.name.replace(/\.[^.]+$/,'')}-快剪.mp4`})});
          if (!response.ok) throw new Error(await response.text());
          const blob = await response.blob();
          const fileName = `${quickVideo.name.replace(/\.[^.]+$/,'')}-快剪.mp4`;
          if (window.showSaveFilePicker) {
            const handle = await window.showSaveFilePicker({suggestedName:fileName,types:[{description:'MP4 视频',accept:{'video/mp4':['.mp4']}}]});
            const writable = await handle.createWritable();
            await writable.write(blob);
            await writable.close();
          } else {
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a'); link.href=url; link.download=fileName; link.click();
            setTimeout(()=>URL.revokeObjectURL(url),1000);
          }
          message.success('裁剪视频已保存');
        } catch (error) {
          if (error.name !== 'AbortError') message.error(`保存失败：${error.message}`);
        } finally { setExporting(false); }
      };
      const openHistory = async fragmentIndex => {
        setHistoryFragment(fragmentIndex);
        setHistoryOpen(true);
        setHistoryLoading(true);
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/videos/history?episode=${currentEpisode}&fragment_index=${fragmentIndex}`);
          const result = await response.json();
          if (!response.ok) throw new Error(result.detail || '加载生成历史失败');
          setHistoryRecords(result.records || []);
        } catch (error) { message.error(error.message); }
        finally { setHistoryLoading(false); }
      };
      const setDefaultVideo = async record => {
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/videos/default`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({episode:currentEpisode,fragment_index:historyFragment,task_id:record.id})});
          const task = await response.json();
          if (!response.ok) throw new Error(task.detail || '设置默认视频失败');
          const request = task.request || {};
          const targetIndex = list.findIndex(entry=>Number(entry.fragment_index || 0)===Number(historyFragment));
          const targetKey = `${currentEpisode}:${historyFragment}`;
          setVideoTasks(prev=>({...prev,[targetKey]:task}));
          setHistoryRecords(prev=>prev.map(item=>({...item,is_default:item.id===record.id})));
          if (targetIndex >= 0) {
            setSelected(targetIndex);
            if (request.prompt !== undefined) setPromptDrafts(prev=>({...prev,[targetKey]:request.prompt}));
          }
          message.success('已设为默认并回填提示词');
        } catch (error) { message.error(error.message); }
      };
      const restoreQuickCut = async fragmentIndex => {
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/videos/quick-cut?episode=${currentEpisode}&fragment_index=${fragmentIndex}`, {method:'DELETE'});
          const result = await response.json();
          if (!response.ok) throw new Error(result.detail || '还原失败');
          setVideoTasks(prev=>{ const current=prev[`${currentEpisode}:${fragmentIndex}`] || {}; return {...prev,[`${currentEpisode}:${fragmentIndex}`]:{...current,video_url:current.original_video_url || current.content?.video_url,edited_file:null,original_video_url:null}}; });
          message.success('已删除剪辑视频并还原原视频');
        } catch (error) { message.error(error.message); }
      };
      const timelineShots = currentShots;
      const timelineEmpty = !timelineShots.length;
      const showSplitHint = timelineEmpty && list.length === 0;
      return <div className="video-studio">
        <div className="video-studio-toolbar">
          <Dropdown
            trigger={['click']}
            open={episodeMenuOpen}
            onOpenChange={setEpisodeMenuOpen}
            menu={{
              items: episodeOptions.length ? episodeOptions : [{ key: String(currentEpisode), label: `第 ${currentEpisode} 集` }],
              selectable: true,
              selectedKeys: [String(currentEpisode)],
              onClick: ({ key }) => switchEpisode(Number(key)),
            }}>
            <div className="studio-episode-switch">
              <Text strong>第 {currentEpisode} 集 · Seedance 视频生成</Text>
              <Tag color="purple">{timelineShots.length} 个片段</Tag>
              <span className={`studio-episode-caret ${episodeMenuOpen?'open':''}`}>▾</span>
            </div>
          </Dropdown>
          <div className="video-studio-toolbar-right">
            <Tag>Seedance mini</Tag>
            <Tag>480P</Tag>
            <Tag>{fragmentTime ? `${fragmentTime}s` : '默认时长'}</Tag>
            <Tag>{ratio}</Tag>
            <Button onClick={onOpenPromptSettings}>设置Seedance生成提示词</Button><Button type="primary" onClick={()=>message.info('请在片段中逐个生成视频')}>合成全集</Button><Button onClick={openQuickCut}>快剪</Button>
          </div>
        </div>
        <div className="video-studio-body">
          <aside className="video-studio-sidebar">
            <div className="studio-section-title"><span>本片段资产</span><span>{fragmentAssets.length}</span></div>
            {currentFragmentIndex > 1 && <div style={{marginBottom:12,padding:10,border:'1px solid #d9d9d9',borderRadius:10,background:'#fafafa'}}><div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8,marginBottom:8}}><Text strong>上一片段尾帧</Text><Switch size="small" checked={videoLastFrameEnabled} onChange={setVideoLastFrameEnabled} checkedChildren="开启" unCheckedChildren="关闭" /></div><Space align="start"><div style={{width:64,height:64,borderRadius:8,overflow:'hidden',background:'#eee',display:'flex',alignItems:'center',justifyContent:'center',flex:'0 0 auto',opacity:videoLastFrameEnabled?1:.45}}>{previousLastFrameUrl?<img src={previousLastFrameUrl} alt="上一片段尾帧" style={{width:'100%',height:'100%',objectFit:'cover'}}/>:<Text type="secondary">无尾帧</Text>}</div><div><Text type="secondary">{!videoLastFrameEnabled?'已关闭，生成时不会使用上一片段尾帧':previousLastFrameUrl?'生成时作为临时参考图（不是当前片段首帧），不加入资产库':'上一片段尚无可用尾帧，将仅使用本片段资产'}</Text></div></Space></div>}
            <Space size={6} wrap style={{marginBottom:12}}><Button size="small" type="primary" loading={smartMatching} onClick={smartMatchAssets}>智能匹配资产</Button><Button size="small" onClick={()=>{setLibraryAssetIds(currentAssetIds);setAssetLibraryOpen(true);}}>从资产库新增</Button><Button size="small" onClick={()=>setNewAssetOpen(true)}>新建资产</Button></Space>
            <Spin spinning={fragmentAssetsLoading}>
              <div className="studio-fragment-assets">{fragmentAssets.length ? fragmentAssets.map(asset=>{
                const displayName=fragmentAssetDisplayName(asset);
                const typeLabel=asset.category==='character'?'角色':asset.category==='scene'?'场景':'道具';
                return <div className="studio-fragment-asset" key={asset.id}><Text strong className="studio-fragment-asset-name" title={displayName}>{displayName}</Text><Upload className="studio-fragment-asset-upload" accept="image/png,image/jpeg,image/webp" showUploadList={false} beforeUpload={file=>uploadFragmentAssetImage(asset.id,file)}><div className="studio-asset-thumb">{asset.image_url?<img src={asset.image_url}/>:<span>{typeLabel[0]}</span>}<span className="studio-fragment-asset-upload-mask">换图</span></div></Upload><div className="studio-fragment-asset-info"><Space size={4} wrap><Tag color={asset.category==='character'?'purple':asset.category==='scene'?'blue':'gold'}>{typeLabel}</Tag>{asset.image_url?<Tag color="green">有图</Tag>:<Tag>待传图</Tag>}<Button type="link" size="small" style={{padding:0,height:'auto'}} onClick={()=>openFragmentAssetLink(asset)}>链接换图</Button></Space>{asset.mapping_text?<Text type="secondary" ellipsis title={asset.mapping_text}>{asset.mapping_text}</Text>:null}</div><Popconfirm title="确认从当前片段移除该资产？" description="只会从当前片段移除，不会删除资产库中的资产。" okText="确认移除" cancelText="取消" onConfirm={()=>removeFragmentAsset(asset.id)}><Button className="studio-fragment-asset-delete" type="text" aria-label="移除资产" title="移除资产"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg></Button></Popconfirm></div>;
              }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前片段暂无资产" />}</div>
            </Spin>
          </aside>
          <main className="video-studio-main">
            <div className="studio-prompt-box">
              <div className="studio-prompt-editor">
                <Input.TextArea value={promptText} onChange={e=>updatePrompt(e.target.value)} bordered={false} placeholder={list.length ? '输入视频生成提示词' : '该集尚未生成 Seedance 提示词'} />
              </div>
              <div className="studio-prompt-actions">
                <Button size="small" type="link" loading={generatingFragment && activeFragmentIndex === currentFragmentIndex} disabled={!timelineShots[selected] || generatingFragment} onClick={()=>onRegenerateFragment && onRegenerateFragment(currentFragmentIndex)}>重新生成提示词</Button>
                <Button type="primary" onClick={generateVideo} loading={videoGenerating}>生成视频</Button>
              </div>
              {matchedAudioCharacters.length ? <Alert type="info" showIcon style={{margin:'0 12px 12px'}} message={`将引用人物参考音：${matchedAudioCharacters.map(asset=>asset.name).join('、')}`} /> : null}
              {generatingFragment ? <div className="studio-prompt-progress"><Progress percent={progress?.percent || 0} size="small" status="active"/><Text type="secondary">{progress?.label || '正在生成…'} {progress?.completed || 0}/{progress?.total || 0}</Text></div> : null}
            </div>
          </main>
          <aside className="video-studio-preview">
            <div className="studio-preview-stage">
              {previewVideoUrl
                ? <>
                    <video ref={previewVideoRef} src={previewVideoUrl} controls preload="metadata" playsInline />
                    {videoTask?.edited_file && <Button className="studio-preview-restore" size="small" onClick={()=>restoreQuickCut(currentFragmentIndex)}>还原</Button>}
                  </>
                : <div className="studio-preview-empty">
                    {videoGenerating ? <Spin size="large" /> : <div style={{fontSize:36,marginBottom:8}}>▶</div>}
                    <div style={{marginTop:videoGenerating?14:0}}>片段 {String(currentFragmentIndex).padStart(2,'0')}</div>
                    <Text type="secondary">{videoGenerating ? `视频任务${videoTask?.status === 'queued' ? '排队中' : '生成中'}，系统正在自动查询结果` : '视频生成后将在这里预览'}</Text>
                  </div>}
            </div>
          </aside>
        </div>
        <div className="video-studio-timeline">
          <div className="studio-section-title" style={{marginBottom:6}}><span>片段时间线</span><Space size={10}><Text type="secondary">{timelineShots.length ? `当前集 ${timelineShots.length} 个片段` : '尚未为该集拆分片段'}</Text><Button size="small" type="primary" ghost disabled={!sequenceVideos.length} onClick={openSequencePreview}>依次播放{sequenceVideos.length ? ` (${sequenceVideos.length})` : ''}</Button></Space></div>
          {timelineEmpty ? <div className="studio-timeline-empty"><Text type="secondary">第 {currentEpisode} 集共 0 个片段，</Text>{typeof onSplitNeeded === 'function' ? <Button size="small" type="link" onClick={onSplitNeeded}>请在“片段”中先拆分片段</Button> : <Text type="secondary">请在“片段”中先拆分片段</Text>}</div> : <div className="studio-timeline-track">{timelineShots.map((shot,index)=>{
            const fragmentIndex = Number(shot?.fragment_index) || index + 1;
            const fragmentTask = videoTasks[`${currentEpisode}:${fragmentIndex}`];
            const thumbnailUrl = fragmentTask?.video_url || fragmentTask?.content?.video_url;
            return <div className={`studio-timeline-card ${selected===index?'active':''}`} key={`${currentEpisode}-${shot.id || index}`} onClick={()=>setSelected(index)}><div className="studio-timeline-thumb">{thumbnailUrl ? <video src={thumbnailUrl} preload="metadata" muted playsInline /> : <span>{selected===index?'▶':'片段'}</span>}{thumbnailUrl && <div className="studio-timeline-actions"><Tooltip title="生成历史"><button className="studio-timeline-action" aria-label="生成历史" onClick={event=>{event.stopPropagation();openHistory(fragmentIndex);}}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></button></Tooltip><Tooltip title="快剪"><button className="studio-timeline-action" aria-label="快剪" onClick={event=>{event.stopPropagation();openQuickCut(fragmentIndex,fragmentTask);}}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="7" r="3"/><circle cx="6" cy="17" r="3"/><path d="m8.7 8.3 10.3 7.2M8.7 15.7 19 8.5"/></svg></button></Tooltip></div>}</div><div className="studio-timeline-label">片段 {String(index+1).padStart(2,'0')} · {shot.time || (shot.duration ? `${shot.duration}s` : '10s')}</div></div>;
          })}</div>}
        </div>
        <Modal width={620} open={assetLinkOpen} onCancel={()=>setAssetLinkOpen(false)} title={assetLinkAsset ? `${fragmentAssetDisplayName(assetLinkAsset)} · 公网图片与素材 ID` : '更新资产公网图片与素材 ID'} okText="保存并换图" confirmLoading={assetLinkSaving} onOk={saveFragmentAssetLink} okButtonProps={{disabled:!assetLinkUrl.trim()}} destroyOnClose>
          <Space direction="vertical" size={12} style={{width:'100%'}}>
            <Alert type="info" showIcon message="素材 ID 可选：填写后生成时优先提交 asset:// 素材 ID；未填写则直接使用公网图片链接。" />
            <Input value={assetLinkUrl} onChange={event=>setAssetLinkUrl(event.target.value)} placeholder="公网图片链接：https://example.com/image.jpg" />
            <Input addonBefore="asset://" value={assetLinkMaterialId} onChange={event=>setAssetLinkMaterialId(event.target.value.replace(/^asset:\/\//i,''))} onPressEnter={saveFragmentAssetLink} placeholder="<ASSET_ID>（选填）" />
            {/^https?:\/\//i.test(assetLinkUrl) && <div style={{textAlign:'center',padding:12,background:'#f5f5f5',borderRadius:10}}><img src={assetLinkUrl} alt="公网资产预览" style={{maxWidth:'100%',maxHeight:360,objectFit:'contain'}} /></div>}
          </Space>
        </Modal>
        <Modal width={820} open={assetLibraryOpen} onCancel={()=>setAssetLibraryOpen(false)} title="从资产库新增到本片段" okText="添加所选资产" onOk={addLibraryAssets} okButtonProps={{disabled:!libraryAssetIds.length}}>
          <Select mode="multiple" showSearch optionFilterProp="label" style={{width:'100%'}} placeholder="选择人物、场景或道具资产" value={libraryAssetIds} onChange={setLibraryAssetIds} options={assets.map(asset=>({value:Number(asset.id),label:`${asset.category==='character'?'人物':asset.category==='scene'?'场景':'道具'} · ${fragmentAssetDisplayName(asset)}${asset.image_url?' · 已有图片':' · 待上传图片'}`}))}/>
          <Alert type="info" showIcon style={{marginTop:14}} message="仅影响当前片段，不会改变同集其他片段。已选择的资产不会重复添加。" />
        </Modal>
        <Modal width={620} open={newAssetOpen} onCancel={()=>setNewAssetOpen(false)} title="新建资产并添加到本片段" okText="创建并添加" confirmLoading={newAssetSaving} onOk={createFragmentAsset}>
          <Space direction="vertical" size={14} style={{width:'100%'}}>
            <div><Text strong>资产类型</Text><Segmented block style={{marginTop:6}} value={newAssetForm.category} onChange={category=>setNewAssetForm({category,parent_id:null,parent_name:'',item_name:'',file:null})} options={[{label:'人物',value:'character'},{label:'场景',value:'scene'},{label:'道具',value:'prop'}]}/></div>
            {newAssetForm.category!=='prop' && <div><Text strong>{newAssetForm.category==='character'?'人物主图':'主场景'}</Text><Select allowClear showSearch optionFilterProp="label" style={{width:'100%',marginTop:6}} placeholder={`选择已有${newAssetForm.category==='character'?'人物主图':'主场景'}，或在下方新建名称`} value={newAssetForm.parent_id} onChange={parent_id=>setNewAssetForm(prev=>({...prev,parent_id}))} options={assets.filter(asset=>asset.category===newAssetForm.category&&!asset.parent_id&&!asset.state).map(asset=>({value:Number(asset.id),label:asset.name||asset.key}))}/>{!newAssetForm.parent_id&&<Input style={{marginTop:8}} placeholder={`新建${newAssetForm.category==='character'?'人物主图':'主场景'}名称`} value={newAssetForm.parent_name} onChange={event=>setNewAssetForm(prev=>({...prev,parent_name:event.target.value}))}/>}</div>}
            <div><Text strong>{newAssetForm.category==='character'?'造型名称':newAssetForm.category==='scene'?'子场景名称':'道具名称'}</Text><Input style={{marginTop:6}} value={newAssetForm.item_name} onChange={event=>setNewAssetForm(prev=>({...prev,item_name:event.target.value}))} placeholder={newAssetForm.category==='character'?'输入破衣服，自动保存为“人物名-破衣服”':newAssetForm.category==='scene'?'例如：灾荒荒野河畔':'例如：瓷碗'}/></div>
            <div><Text strong>资产图片</Text><Upload.Dragger style={{marginTop:6}} accept="image/png,image/jpeg,image/webp" maxCount={1} beforeUpload={file=>{setNewAssetForm(prev=>({...prev,file}));return false;}} onRemove={()=>setNewAssetForm(prev=>({...prev,file:null}))}><p>点击或拖拽上传图片</p><Text type="secondary">支持 PNG、JPG、WEBP，最大 20MB</Text></Upload.Dragger></div>
          </Space>
        </Modal>
        <Modal width={860} open={sequenceOpen} onCancel={()=>setSequenceOpen(false)} destroyOnClose title={`连续预览 · 第 ${currentEpisode} 集`} footer={null}>
          {currentSequenceVideo ? <div className="sequence-preview">
            <div className="sequence-preview-stage"><video ref={sequenceVideoRef} key={currentSequenceVideo.videoUrl} src={currentSequenceVideo.videoUrl} controls autoPlay playsInline preload="auto" onEnded={playNextSequenceVideo}/></div>
            <div className="sequence-preview-info"><Space><Tag color="purple">{currentSequenceVideo.label}</Tag><Text type="secondary">{sequenceIndex+1} / {sequenceVideos.length}</Text>{videoTasks[`${currentEpisode}:${currentSequenceVideo.fragmentIndex}`]?.edited_file && <Tag color="green">已剪辑</Tag>}</Space><Space><Button disabled={sequenceIndex===0} onClick={()=>setSequenceIndex(index=>index-1)}>上一段</Button><Button disabled={sequenceIndex>=sequenceVideos.length-1} onClick={()=>setSequenceIndex(index=>index+1)}>下一段</Button></Space></div>
          </div> : <Empty description="当前集暂无可播放视频" />}
        </Modal>
        <Modal width={760} open={historyOpen} onCancel={()=>setHistoryOpen(false)} title={`片段 ${String(historyFragment || '').padStart(2,'0')} · 生成记录`} footer={null}>
          <Spin spinning={historyLoading}>
            {!historyRecords.length && !historyLoading ? <Empty description="暂无生成记录" /> : <div className="fragment-history-grid">{historyRecords.map(record=><Card key={record.id} className="fragment-history-card" cover={record.video_url ? <video src={record.video_url} controls preload="metadata" playsInline /> : <div style={{height:180,display:'flex',alignItems:'center',justifyContent:'center'}}><Text type={record.status==='failed'?'danger':'secondary'}>{record.error_message || record.status}</Text></div>}><Space direction="vertical" size={8} style={{width:'100%'}}><Space wrap>{record.is_default && <Tag color="blue">默认</Tag>}<Tag>{record.request?.resolution || '—'} · {record.request?.ratio || '—'} · {record.request?.duration || '—'}秒</Tag></Space><Tooltip title={record.request?.prompt}><Text ellipsis style={{maxWidth:'100%'}}>{record.request?.prompt || '无提示词记录'}</Text></Tooltip><Button type={record.is_default?'default':'primary'} disabled={record.is_default || record.status!=='succeeded'} block onClick={()=>setDefaultVideo(record)}>{record.is_default?'当前默认':'设为默认'}</Button></Space></Card>)}</div>}
          </Spin>
        </Modal>
        <Modal className="quick-cut-modal" width={quickCutStep==='edit'?1180:620} open={quickCutOpen} onCancel={()=>setQuickCutOpen(false)} title={quickCutStep==='edit'?'快剪 · 删除不需要的时间段':'选择快剪视频'} footer={quickCutStep==='edit'?[!quickCutContext && <Button key="change" onClick={()=>setQuickCutStep('select')}>更换视频</Button>,<Button key="save" type="primary" loading={exporting} disabled={!duration} onClick={saveQuickCut}>{quickCutContext?'应用到当前片段':'保存到本地'}</Button>]:[<Button key="cancel" onClick={()=>setQuickCutOpen(false)}>取消</Button>,<Button key="next" type="primary" disabled={!quickVideo} onClick={()=>setQuickCutStep('edit')}>下一步</Button>]}>
          {quickCutStep==='select' ? <div className="quick-cut-select"><Upload.Dragger accept="video/mp4,video/quicktime,video/webm,video/x-matroska" showUploadList={false} customRequest={uploadVideo}><p className="quick-cut-upload-icon">＋</p><p>点击或拖拽上传本地视频</p><Text type="secondary">支持 MP4、MOV、M4V、WEBM、MKV</Text></Upload.Dragger></div> : <Spin spinning={exporting} tip="正在裁剪并合并视频…"><div className="quick-cut-editor"><div className="quick-cut-player"><video ref={videoRef} src={quickVideo?.url} controls loop onLoadedMetadata={onVideoReady} onTimeUpdate={onTimeUpdate} onPlay={onPlay} onPause={onPause}/></div><div className="quick-cut-panel"><div><Text strong>{quickVideo?.name}</Text><div><Text type="secondary">总时长 {formatTime(duration)} · 已删除 {deletedRanges.reduce((sum,range)=>sum+range[1]-range[0],0).toFixed(1)} 秒</Text></div></div><Divider/><Space style={{marginBottom:8}}><Switch checked={previewOnlyKeep} onChange={setPreviewOnlyKeep}/><Text>仅在保留区间内循环预览</Text></Space><Text strong>选择操作区间</Text><Slider range min={0} max={duration||1} step={0.05} value={selection} tooltip={{formatter:formatTime}} onChange={onSelectionChange} onAfterChange={onSelectionCommit}/><Space><InputNumber min={0} max={duration} step={0.1} value={selection[0]} onChange={value=>{const next=[Number(value||0),selection[1]]; setSelection(next); seekTo(next[0]);}} addonBefore="入点" addonAfter="秒"/><InputNumber min={0} max={duration} step={0.1} value={selection[1]} onChange={value=>setSelection([selection[0],Number(value||0)])} addonBefore="出点" addonAfter="秒"/></Space><Space.Compact block style={{marginTop:14}}><Button danger style={{width:'50%'}} onClick={deleteSelection}>删除所选时间段</Button><Button type="primary" ghost style={{width:'50%'}} onClick={keepOnlySelection}>仅保留所选片段</Button></Space.Compact><Divider/><div className="quick-cut-deleted"><Text strong>已删除区间</Text>{deletedRanges.length ? deletedRanges.map((range,index)=><Tag closable key={`${range[0]}-${range[1]}`} onClose={()=>setDeletedRanges(prev=>prev.filter((_,i)=>i!==index))}>{formatTime(range[0])} - {formatTime(range[1])}</Tag>) : <Text type="secondary"> 暂无，导出时将保留完整视频</Text>}</div></div><div className="quick-cut-timeline"><div className="quick-cut-ruler">{Array.from({length:9},(_,index)=><span key={index}>{formatTime(duration*index/8)}</span>)}</div><div className="quick-cut-track">{deletedRanges.map((range,index)=><div key={index} className="quick-cut-deleted-block" style={{left:`${range[0]/duration*100}%`,width:`${(range[1]-range[0])/duration*100}%`}}>已删除</div>)}</div></div></div></Spin>}
        </Modal>
      </div>;
    }

    ReactDOM.createRoot(document.getElementById('root')).render(<App />);
  </script>
</body>
</html>
"""
