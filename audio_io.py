import sounddevice as sd
import logging
import queue
import numpy as np
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class AudioIO:
    def __init__(
        self,
        input_sample_rate: int = 16000,
        output_sample_rate: int = 24000,
        input_device: Optional[int] = None,
        output_device: Optional[int] = None,
        dtype: str = "float32",
    ):
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.input_device = input_device
        self.output_device = output_device
        self.dtype = dtype
        
        self.input_stream = None
        self.output_stream = None
        self.play_queue = queue.Queue()
        self.is_running = False

    def start(self, callback: Callable[[np.ndarray], None]):
        """Start audio input stream."""
        if self.is_running:
            return

        self.is_running = True
        
        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio input status: {status}")
            callback(indata.copy())

        try:
            self.input_stream = sd.InputStream(
                samplerate=self.input_sample_rate,
                device=self.input_device,
                channels=1,
                dtype=self.dtype,
                callback=audio_callback,
                blocksize=int(self.input_sample_rate * 0.032), # 32ms chunks
            )
            self.input_stream.start()
            logger.info(f"Audio input started on device {self.input_device or 'default'}")
            
        except Exception as e:
            logger.error(f"Failed to start audio input: {e}")
            self.is_running = False
            raise

    def play(self, audio_chunk: np.ndarray):
        """Play audio chunk."""
        try:
            sd.play(audio_chunk, samplerate=self.output_sample_rate, device=self.output_device)
            sd.wait() # Blocking for simplicity in this MVP, ideally use OutputStream
        except Exception as e:
            logger.error(f"Error playing audio: {e}")

    def stop(self):
        """Stop all audio streams."""
        self.is_running = False
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
        sd.stop()

def list_devices():
    """Print available audio devices."""
    print(sd.query_devices())
