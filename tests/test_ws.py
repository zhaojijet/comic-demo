import asyncio
import websockets
import json


async def test_ws():
    uri = "ws://localhost:8002/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WS")

            # Send prompt
            await websocket.send(
                "A tiny robot exploring a giant library filled with glowing books"
            )

            # Stream response
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    event_type = data.get("type", "")

                    if event_type == "node_start":
                        print(f"\n▶ Starting node: {data.get('node')}")
                    elif event_type == "node_complete":
                        print(
                            f"✔ Completed node: {data.get('node')} - {data.get('content', '')}"
                        )
                    elif event_type == "artifact_update":
                        print(
                            f"  [Artifact] id={data.get('artifact_id')}, category={data.get('category')}"
                        )
                        if data.get("category") == "video":
                            print(f"  >> Video path: {data.get('data', {}).get('url')}")
                    elif event_type == "pipeline_info":
                        print(f"ℹ Pipeline Info: {data.get('content')}")
                    elif event_type == "system":
                        print(f"⚙ System: {data.get('content')}")
                    elif event_type == "pipeline_complete":
                        print(f"\n🎉 Pipeline Finished!")
                        break
                    elif event_type == "error":
                        print(f"\n❌ Error: {data.get('content')}")
                        break
                    else:
                        print(f"Received unknown event: {event_type}")
                except Exception as e:
                    print(f"WS Recv Error: {e}")
                    break
    except Exception as e:
        print(f"Connection Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_ws())
