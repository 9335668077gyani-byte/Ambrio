import msgpack, pytest
from ambrio.ui.ipc.message_protocol import Frame, MsgType

def test_frame_roundtrip():
    frame = Frame(session_id='s1', type=MsgType.CHAT_REQUEST, payload={'content': 'hello'})
    packed = msgpack.packb(frame.model_dump())
    unpacked = Frame.model_validate(msgpack.unpackb(packed, raw=False))
    assert unpacked.session_id == 's1'
    assert unpacked.type == MsgType.CHAT_REQUEST
    assert unpacked.payload['content'] == 'hello'

def test_frame_auto_id():
    f1 = Frame(session_id='s', type=MsgType.CHAT_DONE, payload={})
    f2 = Frame(session_id='s', type=MsgType.CHAT_DONE, payload={})
    assert f1.id != f2.id
