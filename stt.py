import logging
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

class SpeechToText:
    def __init__(
        self,
        model_size: str = "small.en",
        device: str = "cuda",
        compute_type: str = "float16",
        beam_size: int = 1,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        
        try:
            # Auto-fallback to cpu/int8 if cuda/float16 unavailable
            if device == "cuda":
                try:
                    import torch
                    if not torch.cuda.is_available():
                        logger.warning("CUDA not available, falling back to CPU")
                        self.device = "cpu"
                        self.compute_type = "int8"
                except ImportError:
                     self.device = "cpu"
                     self.compute_type = "int8"

            logger.info(f"Loading Whisper model {model_size} on {self.device} ({self.compute_type})...")
            self.model = WhisperModel(
                model_size, 
                device=self.device, 
                compute_type=self.compute_type,
                cpu_threads=4 
            )
            logger.info("Whisper model loaded")
        except Exception as e:
            logger.error(f"Failed to load STT model: {e}")
            raise

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio chunk to text."""
        try:
            # Faster-whisper expects float32
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # Ensure 1D array
            if audio.ndim > 1:
                audio = audio.flatten()

            logger.info(f"STT Input: shape={audio.shape}, max={np.max(np.abs(audio)):.4f}")

            segments, info = self.model.transcribe(
                audio, 
                beam_size=self.beam_size,
                language="en",
                condition_on_previous_text=False
            )
            
            text = " ".join([segment.text for segment in segments]).strip()
            return text
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""
