import asyncio
import os
import sys

# Add src to python path to import our client wrapper
sys.path.insert(0, os.path.abspath("src"))

from config import load_settings, default_config_path
from llm_client import LLMClient


async def run_test_video(client: LLMClient, test_name: str, kwargs: dict):
    print(f"\\n{'='*50}\\nRunning Test: {test_name}\\n{'='*50}")
    try:
        video_url = await client.generate_video(**kwargs)
        print(f"Generated Video URL: {video_url}")

        # Download the video
        import time

        save_path = f"outputs/test_seedance/{test_name.split('.')[0]}_{int(time.time() * 1000)}.mp4"
        print(f"Downloading video to {save_path} ...")
        await client.download_media(video_url, save_path)
        print(f"[Success] Saved {video_url} to {save_path}")
    except Exception as e:
        print(f"ERROR in {test_name}: {e}")


async def main():
    cfg = load_settings(default_config_path())
    video_cfg = cfg.video_llm

    if not video_cfg.api_key:
        print(
            "WARN: API key not set in config.toml for [video_llm]. Skipping live generation."
        )
        print("Please configure video_llm api_key to fully test.")

    client = LLMClient(video_cfg)
    print(f"Initialized Ark SDK wrapper for Video model {video_cfg.model}")

    # Case 1: 图生视频 (Image to Video)
    await run_test_video(
        client,
        "1. 图生视频",
        {
            "prompt": "无人机以极快速度穿越复杂障碍或自然奇观，带来沉浸式飞行体验 --duration 5 --camerafixed false --watermark true",
            "reference_image": "https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_i2v.png",
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
