import asyncio
import os
import sys

# Add src to python path to import our client wrapper
sys.path.insert(0, os.path.abspath("src"))

from config import load_settings, default_config_path
from llm_client import LLMClient


async def run_test_chat(client: LLMClient, test_name: str, kwargs: dict):
    print(f"\\n{'='*50}\\nRunning Test: {test_name}\\n{'='*50}")
    try:
        response = await client.chat(**kwargs)
        print("Response received:")
        print(response)
        if "content" in response:
            print(f"\\nAssistant: {response['content']}")
    except Exception as e:
        print(f"ERROR in {test_name}: {e}")


async def run_test_stream_chat(client: LLMClient, test_name: str, kwargs: dict):
    print(f"\\n{'='*50}\\nRunning Test: {test_name}\\n{'='*50}")
    try:
        kwargs["stream"] = True
        response = await client.chat(**kwargs)
        print("Stream finished, collected response:")
        print(response)
        if "content" in response:
            print(f"\\nAssistant: {response['content']}")
    except Exception as e:
        print(f"ERROR in {test_name}: {e}")


async def main():
    cfg = load_settings(default_config_path())
    llm_cfg = cfg.llm

    if not llm_cfg.api_key or llm_cfg.api_key == "sk-643873dc6a6a4283813143c2b048df9b":
        print(
            "WARN: API key may be default. If it fails, please check your config.toml."
        )

    client = LLMClient(llm_cfg)
    print(f"Initialized SDK wrapper for Text model {llm_cfg.model}")

    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ]

    # Case 1: Standard Chat (Sync/Non-Stream)
    await run_test_chat(
        client, "1. 标准对话 (Non-Stream)", {"messages": messages, "stream": False}
    )

    # Case 2: Streaming Chat
    await run_test_stream_chat(
        client, "2. 流式对话 (Stream)", {"messages": messages, "stream": True}
    )


if __name__ == "__main__":
    asyncio.run(main())
