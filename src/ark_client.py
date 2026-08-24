"""火山方舟统一调用封装。

文本模型 Evolving latest、Seedream 5.0 pro 与 Seedance 2.0 均走火山方舟，
共用一个 ARK_API_KEY。本模块封装：
  - chat(): 文本生成（剧本分析、提示词生成）
  - generate_image(): 图片生成（资产图片）
  - create_video_task(): 创建 Seedance 视频生成任务
  - get_video_task(): 查询 Seedance 视频生成任务
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import yaml
from volcenginesdkarkruntime import Ark


def load_config(config_path: str = "config.yaml") -> dict:
    """读取 config.yaml。"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ArkClient:
    """火山方舟调用客户端。"""

    def __init__(self, config: dict | None = None, config_path: str = "config.yaml"):
        self.config = config or load_config(config_path)
        ark_cfg = self.config.get("ark", {})
        api_key = ark_cfg.get("api_key") or os.getenv("ARK_API_KEY")
        if not api_key or api_key.startswith("YOUR_"):
            raise ValueError("请在 config.yaml 或环境变量 ARK_API_KEY 中配置火山方舟 Key")
        base_url = ark_cfg.get("base_url", "https://ark.cn-beijing.volces.com/api/v3")
        self.client = Ark(api_key=api_key, base_url=base_url)
        self.models = self.config.get("models", {})

    # ---------- 文本生成 ----------
    def _llm_model(self) -> str:
        """文本任务固定使用 Evolving latest，避免 endpoint 覆盖为其他模型。"""
        model = self.models.get("llm", {}).get("model_id")
        expected = "doubao-seed-evolving-latest-version"
        if model != expected:
            raise ValueError(f"文本模型必须配置为 {expected}，当前为 {model or '未配置'}")
        return model

    def chat(self, prompt: str, system: str = "", temperature: float = 0.4) -> str:
        """调用 doubao-seed-evolving-latest-version 生成文本。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat.completions.create(
            model=self._llm_model(),
            messages=messages,
            temperature=temperature,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return resp.choices[0].message.content or ""

    def chat_stream(self, prompt: str, system: str = "", temperature: float = 0.4,
                    diagnostics: dict | None = None, json_mode: bool = False):
        """流式调用文本模型，并将停止原因与 Token 用量写入 diagnostics。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        request_options = {
            "model": self._llm_model(),
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
            "extra_body": {"thinking": {"type": "disabled"}},
        }
        if json_mode:
            request_options["response_format"] = {"type": "json_object"}
        stream = self.client.chat.completions.create(**request_options)
        for chunk in stream:
            if diagnostics is not None:
                diagnostics["response_model"] = getattr(chunk, "model", None) or diagnostics.get("response_model")
                usage = getattr(chunk, "usage", None)
                if usage:
                    diagnostics["usage"] = {
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    }
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if diagnostics is not None and choice.finish_reason:
                diagnostics["finish_reason"] = choice.finish_reason
            delta = choice.delta
            if delta and delta.content:
                yield delta.content

    # ---------- 图片生成 ----------
    def generate_image(self, prompt: str, size: str = "1024x1024",
                       reference_images: list[str] | None = None) -> bytes | None:
        """调用 Seedream 生图；reference_images 非空时执行参考图生图。"""
        model_cfg = self.models.get("image", {})
        kwargs = {
            "model": model_cfg.get("endpoint") or model_cfg.get("model_id"),
            "prompt": prompt,
            "size": size,
            "response_format": "b64_json",
        }
        if reference_images:
            kwargs["image"] = reference_images
        resp = self.client.images.generate(**kwargs)
        data = resp.data
        if not data:
            return None
        # Seedream 返回 b64_json 或 url
        item = data[0]
        if getattr(item, "b64_json", None):
            return base64.b64decode(item.b64_json)
        # 若返回 url，需额外下载（兜底）
        if getattr(item, "url", None):
            import requests
            r = requests.get(item.url, timeout=60)
            r.raise_for_status()
            return r.content
        return None

    # ---------- 视频生成 ----------
    def create_video_task(
        self,
        prompt: str,
        model: str | None = None,
        resolution: str = "720p",
        ratio: str = "9:16",
        duration: int = 5,
        generate_audio: bool = True,
        watermark: bool = False,
        return_last_frame: bool = True,
        reference_content: list[dict] | None = None,
    ) -> dict:
        """创建 Seedance 视频生成任务，返回序列化后的任务信息。"""
        model_cfg = self.models.get("video", {})
        model_id = model or model_cfg.get("endpoint") or model_cfg.get("model_id")
        if not model_id:
            raise ValueError("请在 config.yaml 的 models.video.model_id 中配置 Seedance 模型 ID")
        content = [{"type": "text", "text": prompt}, *(reference_content or [])]
        task = self.client.content_generation.tasks.create(
            model=model_id,
            content=content,
            resolution=resolution,
            ratio=ratio,
            duration=duration,
            generate_audio=generate_audio,
            watermark=watermark,
            return_last_frame=return_last_frame,
        )
        return task.model_dump(exclude_none=True)

    def get_video_task(self, task_id: str) -> dict:
        """查询 Seedance 视频生成任务，返回状态、结果或错误信息。"""
        task = self.client.content_generation.tasks.get(task_id=task_id)
        return task.model_dump(exclude_none=True)
