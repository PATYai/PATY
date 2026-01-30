import logging
import os
from litellm import completion
from typing import Generator, Optional

logger = logging.getLogger(__name__)

class VertexLLM:
    def __init__(
        self,
        project: Optional[str] = None,
        location: str = "us-central1",
        system_prompt: Optional[str] = None,
        model_name: str = "vertex_ai/gemini-2.5-flash"
    ):
        self.project = project or os.getenv("VERTEX_PROJECT")
        self.location = location
        self.system_prompt = system_prompt
        self.model_name = model_name
        
        if not self.project:
            logger.warning("VERTEX_PROJECT not set, Vertex AI calls might fail")
        
        # Configure litellm
        os.environ["VERTEX_PROJECT"] = self.project
        os.environ["VERTEX_LOCATION"] = self.location

    def generate_streaming(self, text: str) -> Generator[str, None, None]:
        """Generate response streaming."""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        
        messages.append({"role": "user", "content": text})
        
        try:
            response = completion(
                model=self.model_name,
                messages=messages,
                stream=True,
                temperature=0.7,
            )
            
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
                    
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            yield f"I apologize, but I encountered an error: {e}"

class MockLLM:
    def __init__(self):
        pass

    def generate_streaming(self, text: str) -> Generator[str, None, None]:
        """Mock streaming response."""
        response = f"This is a mock response to: {text}. Thank you for asking."
        
        # Artificial streaming
        import time
        for word in response.split():
            yield word + " "
            time.sleep(0.05)
