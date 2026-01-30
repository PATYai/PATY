import numpy as np
import torch
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class VoiceActivityDetector:
    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_silence_ms: int = 500,
        min_speech_ms: int = 250,
    ):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_silence_ms = min_silence_ms
        self.min_speech_ms = min_speech_ms
        
        try:
            self.model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True
            )
            (self.get_speech_timestamps, _, self.read_audio, _, _) = utils
            logger.info("Silero VAD model loaded")
        except Exception as e:
            logger.error(f"Failed to load Silero VAD: {e}")
            raise

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Check if current chunk contains speech."""
        # Silero expects torch tensor (batch, time) or (time,)
        # Sounddevice gives (frames, channels), e.g. (512, 1)
        if isinstance(audio_chunk, np.ndarray):
            audio_tensor = torch.from_numpy(audio_chunk)
        else:
            audio_tensor = audio_chunk
            
        # Squeeze channel dim if present implies (N, 1) -> (N,)
        if audio_tensor.ndim == 2 and audio_tensor.shape[1] == 1:
            audio_tensor = audio_tensor.squeeze(1)
            
        # Ensure we have enough samples
        if audio_tensor.numel() < 512:
            return False

        params = {"sampling_rate": self.sample_rate, "threshold": self.threshold}
        
        # Note: This is a simplified check. Streaming usage is handled in StreamingVAD
        return self.model(audio_tensor, self.sample_rate).item() > self.threshold

class StreamingVAD:
    def __init__(self, vad: VoiceActivityDetector, chunk_ms: int = 32):
        self.vad = vad
        self.chunk_ms = chunk_ms
        self.buffer = []
        self.speaking = False
        self.silence_counter = 0
        self.speech_buffer = []
        
        # Convert ms to frames
        self.min_silence_frames = int(vad.min_silence_ms / chunk_ms)
        self.min_speech_frames = int(vad.min_speech_ms / chunk_ms)

    def feed(self, audio_chunk: np.ndarray) -> List[Dict[str, Any]]:
        """
        Feed audio chunk and return events.
        
        Returns list of events:
        [{"speech_end": True, "audio": np.ndarray}]
        """
        results = []
        
        is_speech = self.vad.is_speech(audio_chunk)
        
        if is_speech:
            self.speaking = True
            self.silence_counter = 0
            self.speech_buffer.append(audio_chunk)
        else:
            if self.speaking:
                self.silence_counter += 1
                self.speech_buffer.append(audio_chunk) # Keep trailing silence
                
                if self.silence_counter >= self.min_silence_frames:
                    # End of speech detected
                    self.speaking = False
                    
                    full_audio = np.concatenate(self.speech_buffer)
                    
                    # Filter short noises
                    if len(self.speech_buffer) >= self.min_speech_frames:
                        results.append({
                            "speech_end": True, 
                            "audio": full_audio
                        })
                    
                    self.speech_buffer = []
                    self.silence_counter = 0
        
        return results
