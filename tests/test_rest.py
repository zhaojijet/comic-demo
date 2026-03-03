import httpx
import asyncio
import json


async def run_test():
    url = "http://localhost:8002/api/comic/generate"
    payload = {"prompt": "a cute puppy running"}

    async with httpx.AsyncClient() as client:
        print("Sending request to:", url)
        try:
            response = await client.post(url, json=payload, timeout=300.0)
            print("Status Code:", response.status_code)
            print("Response:", json.dumps(response.json(), indent=2))
        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    asyncio.run(run_test())
