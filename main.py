import os
from mcp.server.fastmcp import FastMCP
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

# Initialize the MCP Server
mcp = FastMCP("PATY Vertex Agent")

# 1. SETUP: Configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1") # fast region
MODEL_NAME = "gemini-1.5-flash-002" # Flash = Low Latency

if not PROJECT_ID:
    raise ValueError("Please set GOOGLE_CLOUD_PROJECT environment variable.")

# 2. INIT: Vertex AI with PATY System Instruction
vertexai.init(project=PROJECT_ID, location=LOCATION)

# We define the "Please and Thank You" behavior here.
# This ensures the model never forgets its manners, regardless of the user prompt.
paty_instruction = """
You are a helpful, low-latency AI assistant. 
You strictly adhere to the PATY protocol (Please And Thank You):
1. Always maintain a warm, extremely polite, and courteous tone.
2. If you need to ask the user for more info, start with 'Please'.
3. End your responses with 'Thank you' or a variation of gratitude.
4. Keep responses concise to maintain low latency, but never sacrifice manners.
"""

model = GenerativeModel(
    MODEL_NAME,
    system_instruction=paty_instruction
)

@mcp.tool()
async def polite_chat(message: str) -> str:
    """
    Sends a message to the Vertex AI agent which replies with 
    low latency and extreme politeness (PATY protocol).
    """
    
    # Configuration for speed
    # We lower the token count slightly to encourage brevity (faster network transfer)
    config = GenerationConfig(
        temperature=0.7,
        max_output_tokens=500, 
    )

    try:
        # Use async generation for non-blocking performance
        response = await model.generate_content_async(
            message,
            generation_config=config
        )
        return response.text
    except Exception as e:
        return f"Please forgive the error, but I encountered an issue: {str(e)}. Thank you for your patience."

if __name__ == "__main__":
    mcp.run()