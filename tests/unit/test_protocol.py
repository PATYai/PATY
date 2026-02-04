from pipecat_outbound.protocol import CallRequest, CallSession


def test_call_request_defaults():
    req = CallRequest(to="+15551234")
    assert req.to == "+15551234"
    assert req.from_ is None
    assert req.metadata is None

def test_call_request_full():
    req = CallRequest(to="+1234", from_="+5678", metadata={"foo": "bar"})
    assert req.to == "+1234"
    assert req.from_ == "+5678"
    assert req.metadata == {"foo": "bar"}

def test_call_session_defaults():
    session = CallSession(id="1", provider="test", to="+1", from_="+2")
    assert session.id == "1"
    assert session.provider == "test"
    assert session.to == "+1"
    assert session.from_ == "+2"
    assert session.status == "initiated"
    assert session.provider_data is None
