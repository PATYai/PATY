"""
HTTP integration tests for the PATY Call Composer interface.

Tests the bot's FastAPI endpoints with the new call schema:
  target (phone_number + who), goal, impersonate, persona, secrets

Asserts that first-message transcripts reflect the parameters correctly.
"""

import asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TARGET = {"phone_number": "+14155551234", "who": "Acme Dental"}
BASE_START = {
    "room_url": "https://test.daily.co/test-room",
    "token": "test-token",
    "target": BASE_TARGET,
    "room_name": "test-room",
}


async def wait_for_events(client, room_name, count=1, max_wait=2.0):
    """Poll /transcript until at least `count` events appear or timeout."""
    deadline = asyncio.get_event_loop().time() + max_wait
    body = {}
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(f"/transcript/{room_name}")
        body = r.json()
        if len(body.get("events", [])) >= count:
            return body
        await asyncio.sleep(0.02)
    return body


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_start_missing_target(client):
    """target is required — omitting it should return 422."""
    resp = await client.post(
        "/start",
        json={
            "room_url": "https://test.daily.co/room",
            "token": "tok",
        },
    )
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "target") in locs


async def test_start_impersonation_no_persona(client):
    """impersonate=True without persona should return 422."""
    resp = await client.post(
        "/start",
        json={
            **BASE_START,
            "impersonate": True,
            # persona intentionally omitted
        },
    )
    assert resp.status_code == 422
    detail_str = str(resp.json()["detail"]).lower()
    assert "persona" in detail_str


# ---------------------------------------------------------------------------
# Transcript not found
# ---------------------------------------------------------------------------


async def test_transcript_not_found(client):
    resp = await client.get("/transcript/nonexistent-room")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# First-message transcript assertions
# ---------------------------------------------------------------------------


async def test_start_basic_goal(client):
    """First assistant message should reference the goal."""
    goal = "Confirm the Tuesday 3pm appointment"
    resp = await client.post(
        "/start",
        json={**BASE_START, "goal": goal, "room_name": "room-basic-goal"},
    )
    assert resp.status_code == 200
    assert resp.json()["room_name"] == "room-basic-goal"

    body = await wait_for_events(client, "room-basic-goal")
    assistant = [e for e in body["events"] if e.get("role") == "assistant"]
    assert len(assistant) >= 1
    assert goal in assistant[0]["text"]


async def test_start_basic_goal_includes_who(client):
    """First message should address the target by name."""
    resp = await client.post(
        "/start",
        json={
            **BASE_START,
            "room_name": "room-who",
            "goal": "Check on order status",
        },
    )
    assert resp.status_code == 200

    body = await wait_for_events(client, "room-who")
    assistant = [e for e in body["events"] if e.get("role") == "assistant"]
    assert len(assistant) >= 1
    assert BASE_TARGET["who"] in assistant[0]["text"]


async def test_start_impersonation(client):
    """With impersonate=True, first message should name the persona, not PATY."""
    persona = "Dr. Chen's scheduling assistant"
    resp = await client.post(
        "/start",
        json={
            **BASE_START,
            "room_name": "room-impersonation",
            "impersonate": True,
            "persona": persona,
            "goal": "Schedule an appointment",
        },
    )
    assert resp.status_code == 200

    body = await wait_for_events(client, "room-impersonation")
    assistant = [e for e in body["events"] if e.get("role") == "assistant"]
    assert len(assistant) >= 1
    first = assistant[0]["text"]
    assert persona in first
    assert "PATY" not in first


async def test_start_with_secrets(client):
    """Secrets should be available to the bot but not echoed in the greeting."""
    secrets = {"account_pin": "9876", "dob": "1985-03-12"}
    resp = await client.post(
        "/start",
        json={
            **BASE_START,
            "room_name": "room-secrets",
            "goal": "Verify account details",
            "secrets": secrets,
        },
    )
    assert resp.status_code == 200

    body = await wait_for_events(client, "room-secrets")
    assistant = [e for e in body["events"] if e.get("role") == "assistant"]
    assert len(assistant) >= 1
    first = assistant[0]["text"]
    assert "Verify account details" in first
    assert "9876" not in first
    assert "1985-03-12" not in first


# ---------------------------------------------------------------------------
# Transcript structure
# ---------------------------------------------------------------------------


async def test_transcript_structure(client):
    """Transcript response must have the correct shape and support incremental polling."""
    resp = await client.post(
        "/start",
        json={**BASE_START, "room_name": "room-structure", "goal": "Test structure"},
    )
    assert resp.status_code == 200

    body = await wait_for_events(client, "room-structure")

    # Top-level keys
    assert {"active", "events", "next_index"} <= body.keys()
    assert isinstance(body["active"], bool)
    assert isinstance(body["events"], list)
    assert isinstance(body["next_index"], int)
    assert body["next_index"] >= 0

    # Each transcript event has required fields
    for event in body["events"]:
        assert "type" in event
        if event["type"] == "transcript":
            assert event["role"] in ("user", "assistant")
            assert isinstance(event["text"], str)
            assert isinstance(event["turn"], int)

    # Incremental poll: since=next_index returns empty events
    next_index = body["next_index"]
    poll = await client.get(
        "/transcript/room-structure", params={"since": next_index}
    )
    assert poll.status_code == 200
    poll_body = poll.json()
    assert poll_body["events"] == []
    assert poll_body["next_index"] == next_index
