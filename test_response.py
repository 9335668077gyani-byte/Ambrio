"""Send a test message to the running Ambrio router and print the response."""
import asyncio, sys, msgpack

# Windows: must use SelectorEventLoop for ZMQ
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, r'C:\MY PROJECTS\Ambrio')
from ambrio.ui.ipc.message_protocol import Frame, MsgType

async def test():
    import zmq, zmq.asyncio
    ctx  = zmq.asyncio.Context()
    sock = ctx.socket(zmq.DEALER)
    sock.connect("tcp://127.0.0.1:5555")

    frame = Frame(
        session_id="test-session",
        type=MsgType.CHAT_REQUEST,
        payload={"content": "Hello! What can you do?"}
    )
    await sock.send_multipart([msgpack.packb(frame.model_dump(), use_bin_type=True)])
    print(">> Sent: 'Hello! What can you do?'")
    print(">> Ambrio: ", end="", flush=True)

    full = ""
    while True:
        try:
            parts = await asyncio.wait_for(sock.recv_multipart(), timeout=20)
            resp  = Frame.model_validate(msgpack.unpackb(parts[-1], raw=False))

            if resp.type == MsgType.CHAT_TOKEN:
                token = resp.payload.get("token", "")
                print(token, end="", flush=True)
                full += token
            elif resp.type in (MsgType.CHAT_DONE,) or resp.payload.get("done"):
                break
            elif resp.type == MsgType.ERROR:
                print(f"\n!! ERROR: {resp.payload}")
                break
        except asyncio.TimeoutError:
            print("\n!! TIMEOUT — no response in 20s")
            break

    print(f"\n\n✅ Full response ({len(full)} chars):\n{full}")
    sock.close()
    ctx.term()

asyncio.run(test())
