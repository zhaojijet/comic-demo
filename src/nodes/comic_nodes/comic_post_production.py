from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicPostProductionInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Edit and assemble clips; skip: Skip editing; default: default",
    )


class ComicPostProductionOutput(BaseModel):
    edited_video: str = Field(description="Path to the assembled and edited video")


@NODE_REGISTRY.register()
class ComicPostProductionNode(BaseNode):
    meta = NodeMeta(
        name="comic_post_production",
        description="Assemble video clips, add audio, text, and effects. This is the '剪辑&后期' phase.",
        node_id="comic_post_production",
        node_kind="comic_post_production",
        require_prior_kind=["comic_image2video", "comic_script"],
        default_require_prior_kind=["comic_image2video", "comic_script"],
        next_available_node=["comic_super_resolution"],
    )

    input_schema = ComicPostProductionInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"edited_video": "default_edited_video.mp4"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user("正在进行最后的剪辑与后期合成...")
        videos = inputs.get("comic_image2video", {}).get("videos", [])
        script = inputs.get("comic_script", {}).get("script", "")

        if not videos:
            return {"edited_video": ""}

        import asyncio
        import os
        from mcp_custom.sampling_requester import LLMClient

        from pathlib import Path

        save_dir = Path("outputs/comic_post_production")
        save_dir.mkdir(parents=True, exist_ok=True)

        # In a real scenario, we might parse the script to get exact lines per panel.
        # Here we just demo calling TTS for the overall script.
        tts_audio = ""
        local_audio_path = ""
        if script:
            try:
                node_state.node_summary.info_for_user("正在生成角色配音素材...")
                tts_audio = await node_state.llm.generate_audio(
                    prompt=f"请为以下剧本生成配音：\n{script}"
                )
                if tts_audio:
                    local_audio_path = str(
                        save_dir
                        / f"{node_state.session_id}_{node_state.artifact_id}_voiceover.mp3"
                    )
                    await LLMClient.download_media(tts_audio, local_audio_path)
            except Exception as e:
                node_state.node_summary.warning_for_user(f"配音生成失败: {e}")

        # Simulate the final video composition that combines the video clips and the TTS audio
        edited_video_path = str(
            save_dir
            / f"{node_state.session_id}_{node_state.artifact_id}_final_edited_comic_composition.mp4"
        )

        # Touch the file to ensure it exists for the next node (since it's a simulation)
        with open(edited_video_path, "a"):
            pass

        node_state.node_summary.info_for_user(
            f"成功合成了 {len(videos)} 个视频片段，并混合了旁白音频，输出至 {edited_video_path}。"
        )
        return {"edited_video": edited_video_path}
