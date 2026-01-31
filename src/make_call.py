"""
Simple script to trigger an outbound call.
Run this after starting the agent with: uv run python src/agent.py dev
"""

import asyncio
import json
import os

from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

# Load dial info from participant.json
with open("participant.json") as f:
    dial_info = json.load(f)


async def make_call():
    lkapi = api.LiveKitAPI()

    room_name = dial_info.get("room_name", "outbound-call-room")
    phone_number = dial_info["sip_call_to"]

    print(f"Dispatching agent to call {phone_number}...")

    # Create a dispatch to start the agent in the room
    dispatch = await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            agent_name="outbound-caller",
            room=room_name,
            metadata=json.dumps(dial_info),
        )
    )

    print(f"Dispatch created: {dispatch}")
    print(f"The agent will now dial {phone_number}")

    await lkapi.aclose()


if __name__ == "__main__":
    asyncio.run(make_call())
