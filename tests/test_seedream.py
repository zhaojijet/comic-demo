import asyncio
import os
import sys

# Add src to python path to import our client wrapper
sys.path.insert(0, os.path.abspath("src"))

from config import load_settings, default_config_path
from llm_client import LLMClient


async def run_test_stream(client: LLMClient, test_name: str, kwargs: dict):
    print(f"\\n{'='*50}\\nRunning Test: {test_name}\\n{'='*50}")
    try:
        kwargs["stream"] = True
        images_response = await client.generate_image(**kwargs)

        # Async stream handling (matches the Volcengine SDK example)
        print("Waiting for streaming events...")
        async for event in images_response:
            if event is None:
                continue
            if event.type == "image_generation.partial_failed":
                print(f"[Error] Stream generate images error: {event.error}")
                if (
                    event.error is not None
                    and event.error.code == "InternalServerError"
                ):
                    break
            elif event.type == "image_generation.partial_succeeded":
                url = event.url if event.url else "No URL"
                size = event.size if event.size else "Unknown"
                if url != "No URL":
                    import time

                    save_path = f"outputs/test_seedream/{test_name.split('.')[0]}_{int(time.time() * 1000)}.jpg"
                    await client.download_image(url, save_path)
                    print(f"[Success] recv.Size: {size}, saved to: {save_path}")
                else:
                    print(f"[Success] recv.Size: {size}, recv.Url: {url}")
            elif event.type == "image_generation.completed":
                print("[Completed] Final completed event.")
                if event.usage:
                    print(f"[Usage] {event.usage}")
    except Exception as e:
        print(f"ERROR in {test_name}: {e}")


async def run_test_sync(client: LLMClient, test_name: str, kwargs: dict):
    print(f"\\n{'='*50}\\nRunning Test: {test_name}\\n{'='*50}")
    try:
        kwargs["stream"] = False
        urls = await client.generate_image(**kwargs)
        print("Generated URLs:")
        for i, url in enumerate(urls):
            save_path = f"outputs/test_seedream/{test_name.split('.')[0]}_{i}.jpg"
            await client.download_image(url, save_path)
            print(f"- Saved {url} to {save_path}")
    except Exception as e:
        print(f"ERROR in {test_name}: {e}")


async def main():
    cfg = load_settings(default_config_path())
    img_cfg = cfg.image_llm

    if not img_cfg.api_key:
        print("WARN: API key not set in config.toml. Skipping live generation.")
        print("Please configure image_llm api_key to fully test.")
        # We can still proceed to see if the SDK initializes correctly without API key
        # but real api calls will fail with 401.

    # Initialize the LLMClient (which will use AsyncArk natively internally)
    client = LLMClient(img_cfg)
    print(f"Initialized Ark SDK wrapper for model {img_cfg.model}")

    # Case 1: 文生图-生成单张图
    await run_test_sync(
        client,
        "1. 文生图-生成单张图",
        {
            "prompt": "星际穿越，黑洞，黑洞里冲出一辆快支离破碎的复古列车，抢视觉冲击力，电影大片，末日既视感，动感，对比色，oc渲染，光线追踪，动态模糊，景深，超现实主义，深蓝，画面通过细腻的丰富的色彩层次塑造主体与场景，质感真实，暗黑风背景的光影效果营造出氛围，整体兼具艺术幻想感，夸张的广角透视效果，耀光，反射，极致的光影，强引力，吞噬",
            "is_batch": False,
        },
    )

    # Case 2: 文生图-生成一组图
    await run_test_stream(
        client,
        "2. 文生图-生成一组图",
        {
            "prompt": "生成一组共4张连贯插画，核心为同一庭院一角的四季变迁，以统一风格展现四季独特色彩、元素与氛围",
            "is_batch": True,
            "batch_size": 4,
        },
    )

    # Case 3: 图生图-单张图生成单张图
    await run_test_sync(
        client,
        "3. 图生图-单张图生成单张图",
        {
            "prompt": "生成狗狗趴在草地上的近景画面",
            "reference_images": [
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imageToimage.png"
            ],
            "is_batch": False,
        },
    )

    # Case 4: 图生图-单张图生成一组图
    await run_test_stream(
        client,
        "4. 图生图-单张图生成一组图",
        {
            "prompt": "参考这个LOGO，做一套户外运动品牌视觉设计，品牌名称为GREEN，包括包装袋、帽子、纸盒、手环、挂绳等。绿色视觉主色调，趣味、简约现代风格",
            "reference_images": [
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imageToimages.png"
            ],
            "is_batch": True,
            "batch_size": 5,
        },
    )

    # Case 5: 图生图-多张参考图生成单张图
    await run_test_sync(
        client,
        "5. 图生图-多张参考图生成单张图",
        {
            "prompt": "将图1的服装换为图2的服装",
            "reference_images": [
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimage_1.png",
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimage_2.png",
            ],
            "is_batch": False,
        },
    )

    # Case 6: 图生图-多张参考图生成一组图
    await run_test_stream(
        client,
        "6. 图生图-多张参考图生成一组图",
        {
            "prompt": "生成3张女孩和奶牛玩偶在游乐园开心地坐过山车的图片，涵盖早晨、中午、晚上",
            "reference_images": [
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimages_1.png",
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimages_2.png",
            ],
            "is_batch": True,
            "batch_size": 3,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
