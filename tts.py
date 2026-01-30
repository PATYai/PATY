import logging
import numpy as np
import soundfile as sf
import os
import urllib.request
from kokoro_onnx import Kokoro
from typing import List, Generator

logger = logging.getLogger(__name__)

class TextToSpeech:
    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        
        # Ensure model files exist
        self.model_path = "kokoro-v1.0.onnx"
        self.voices_path = "voices-v1.0.bin"
        self._ensure_models()
        
        try:
            self.kokoro = Kokoro(self.model_path, self.voices_path)
            # Warmup
            # self.kokoro.create("Hello", voice=self.voice, speed=self.speed, lang="en-us")
            logger.info(f"TTS initialized with voice {voice}")
        except Exception as e:
            logger.error(f"Failed to initialize TTS: {e}")
            raise

    def _ensure_models(self):
        """Download model files if missing."""
        if not os.path.exists(self.model_path):
            logger.info("Downloading Kokoro ONNX model...")
            url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
            urllib.request.urlretrieve(url, self.model_path)
            
        if not os.path.exists(self.voices_path):
            logger.info("Downloading Voices BIN...")
            url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
            urllib.request.urlretrieve(url, self.voices_path)

    def synthesize(self, text: str) -> np.ndarray:
        """Synthesize text to audio."""
        if not text.strip():
            return np.array([], dtype=np.float32)
            
        try:
            audio, sample_rate = self.kokoro.create(
                text, 
                voice=self.voice, 
                speed=self.speed, 
                lang="en-us"
            )
            return audio
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return np.array([], dtype=np.float32)

class StreamingTTS:
    def __init__(self, tts: TextToSpeech, chunk_ms: int = 200):
        self.tts = tts
        self.chunk_ms = chunk_ms
        self.buffer = ""
        self.audio_queue = []
        
        # Simple sentence splitter
        self.delimiters = [".", "!", "?", "\n"]

    def feed(self, text_chunk: str):
        """Feed text chunk and process ready sentences."""
        self.buffer += text_chunk
        
        while True:
            # Find first delimiter
            min_index = -1
            for delimiter in self.delimiters:
                idx = self.buffer.find(delimiter)
                if idx != -1:
                    if min_index == -1 or idx < min_index:
                        min_index = idx
            
            if min_index == -1:
                break
                
            # We have a sentence end at min_index
            sentence = self.buffer[:min_index+1].strip()
            self.buffer = self.buffer[min_index+1:]
            
            if sentence:
                audio = self.tts.synthesize(sentence)
                if len(audio) > 0:
                    self.audio_queue.append(audio)

    def get_audio(self) -> Generator[np.ndarray, None, None]:
        """Yield ready audio chunks."""
        while self.audio_queue:
            yield self.audio_queue.pop(0)

    def flush(self) -> Generator[np.ndarray, None, None]:
        """Flush remaining text."""
        if self.buffer.strip():
            audio = self.tts.synthesize(self.buffer.strip())
            if len(audio) > 0:
                yield audio
        self.buffer = ""
