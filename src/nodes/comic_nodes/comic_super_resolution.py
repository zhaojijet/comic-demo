from typing import Any, Dict
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicSuperResolutionInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Upscale video; skip: Skip upscale; default: default",
    )


class ComicSuperResolutionOutput(BaseModel):
    final_video: str = Field(description="Path to the final super-resolution video")


@NODE_REGISTRY.register()
class ComicSuperResolutionNode(BaseNode):
    meta = NodeMeta(
        name="comic_super_resolution",
        description="Upscale the final video for better quality. This is the '视频超分' phase.",
        node_id="comic_super_resolution",
        node_kind="comic_super_resolution",
        require_prior_kind=["comic_post_production"],
        default_require_prior_kind=["comic_post_production"],
        next_available_node=[],  # Final node in the pipeline
    )

    input_schema = ComicSuperResolutionInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"final_video": "default_final_4k_video.mp4"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "正在为您精湛画质，进行视频超大分辨率重绘..."
        )
        video_url = inputs.get("comic_post_production", {}).get("edited_video", "")

        if not video_url:
            return {"final_video": ""}

        prompt = "请对该视频进行画质提升与超分（Super Resolution），输出4K高清版本。\n【重要限制】：保持生成的视频片段时长在 10秒以内！ --duration 5"

        import os
        from mcp_custom.sampling_requester import LLMClient

        from pathlib import Path

        save_dir = Path("outputs/comic_super_resolution")
        save_dir.mkdir(parents=True, exist_ok=True)

        try:
            final_video = await node_state.llm.generate_video(
                prompt=prompt, video_url=video_url
            )
            filename = f"{node_state.session_id}_{node_state.artifact_id}_final_super_resolution.mp4"
            save_path = str(save_dir / filename)

            if final_video:
                await LLMClient.download_media(final_video, save_path)
                node_state.node_summary.info_for_user(
                    f"视频超分完成，并在本地保存为: {filename}"
                )
                return {"final_video": str(save_path)}
        except Exception as e:
            node_state.node_summary.warning_for_user(f"视频超分失败: {e}")
            filename = f"{node_state.session_id}_{node_state.artifact_id}_final_super_resolution.mp4"
            save_path = str(save_dir / filename)

        # Fallback to dummy
        try:
            import os, shutil

            dummy_src = os.path.join(".comic_demo", "dummy.mp4")
            if os.path.exists(dummy_src):
                shutil.copy(dummy_src, save_path)
            else:
                os.system(f"touch {save_path}")
            node_state.node_summary.info_for_user("写回了占位超分视频完成。")
        except Exception:
            pass
        return {"final_video": str(save_path)}
