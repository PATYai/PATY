#!/usr/bin/env python3
"""
Real-time voice assistant with low-latency streaming.

Pipeline: VAD → STT → LLM → TTS → Speaker
"""

import argparse
import logging
import numpy as np
import threading
import time
from typing import Optional

from vad import VoiceActivityDetector, StreamingVAD
from stt import SpeechToText
from tts import TextToSpeech, StreamingTTS
from llm import VertexLLM, MockLLM
from audio_io import AudioIO, list_devices
from dotenv import load_dotenv
from prompts import paty_instruction

# Load stage.env before anything else
load_dotenv("stage.env")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class VoiceAssistant:
    """
    Real-time voice assistant orchestrator.

    Handles the full pipeline with streaming optimizations:
    1. VAD detects when user stops speaking
    2. STT transcribes the utterance
    3. LLM generates response (streaming)
    4. TTS synthesizes speech (starts on first sentence)
    5. Audio plays to speaker
    """

    def __init__(
        self,
        whisper_model: str = "small.en",
        voice: str = "af_heart",
        project: Optional[str] = None,
        location: str = "us-central1",
        system_prompt: Optional[str] = None,
        input_device: Optional[int] = None,
        output_device: Optional[int] = None,
        use_mock_llm: bool = False,
    ):
        logger.info("Initializing Voice Assistant...")

        # Audio I/O
        self.audio = AudioIO(
            input_sample_rate=16000,
            output_sample_rate=24000,
            input_device=input_device,
            output_device=output_device,
        )

        # VAD
        self.vad = VoiceActivityDetector(
            sample_rate=16000,
            threshold=0.5,
            min_silence_ms=500,
            min_speech_ms=250,
        )
        self.streaming_vad = StreamingVAD(self.vad, chunk_ms=32)

        # STT
        self.stt = SpeechToText(
            model_size=whisper_model,
            device="cuda",
            compute_type="float16",
            beam_size=1,
        )

        # LLM
        if use_mock_llm:
            self.llm = MockLLM()
            logger.info("Using mock LLM")
        else:
            self.llm = VertexLLM(
                project=project,
                location=location,
                system_prompt=system_prompt,
            )

        # TTS
        self.tts = TextToSpeech(voice=voice, speed=1.0)
        self.streaming_tts = StreamingTTS(self.tts, chunk_ms=200)

        # State
        self.is_running = False
        self.is_processing = False
        self.lock = threading.Lock()

        logger.info("Voice Assistant initialized")

    def _on_audio_chunk(self, audio_chunk: np.ndarray):
        """Handle incoming audio chunk from microphone."""
        if not self.is_running:
            return

        # Skip if we're currently processing/speaking
        if self.is_processing:
            return

        # Process through VAD
        results = self.streaming_vad.feed(audio_chunk)

        for result in results:
            if result["speech_end"]:
                # Speech ended - process the utterance
                logger.info("Speech detected, processing...")
                threading.Thread(
                    target=self._process_utterance,
                    args=(result["audio"],),
                    daemon=True,
                ).start()

    def _process_utterance(self, audio: np.ndarray):
        """Process a complete utterance through STT → LLM → TTS."""
        with self.lock:
            if self.is_processing:
                return
            self.is_processing = True

        try:
            start_time = time.time()

            # STT
            stt_start = time.time()
            text = self.stt.transcribe(audio)
            stt_time = time.time() - stt_start
            
            if not text.strip():
                print("\n(No speech detected)")
                logger.info("No speech detected, skipping")
                return

            print(f"\nUser: {text}")
            logger.info(f"User: {text} (STT: {stt_time*1000:.0f}ms)")

            # LLM with streaming TTS
            llm_start = time.time()
            first_token_time = None
            first_audio_time = None
            full_response = ""

            print("\nAssistant: ", end="", flush=True)

            for chunk in self.llm.generate_streaming(text):
                if first_token_time is None:
                    first_token_time = time.time() - llm_start
                    logger.info(f"LLM first token: {first_token_time*1000:.0f}ms")

                full_response += chunk
                print(chunk, end="", flush=True)

                # Feed to streaming TTS
                self.streaming_tts.feed(chunk)

                # Play any ready audio
                for audio_chunk in self.streaming_tts.get_audio():
                    if first_audio_time is None:
                        first_audio_time = time.time() - start_time
                        logger.info(f"First audio: {first_audio_time*1000:.0f}ms from start")
                    self.audio.play(audio_chunk)
            
            print() # Newline after response
            logger.info(f"Assistant: {full_response}")

            # Flush remaining TTS
            for audio_chunk in self.streaming_tts.flush():
                self.audio.play(audio_chunk)

            total_time = time.time() - start_time
            logger.info(f"Total processing: {total_time*1000:.0f}ms")

        except Exception as e:
            logger.error(f"Error processing utterance: {e}", exc_info=True)

        finally:
            with self.lock:
                self.is_processing = False

    def run(self):
        """Run the voice assistant (blocking)."""
        self.is_running = True

        print("\n" + "=" * 50)
        print("Voice Assistant Ready")
        print("=" * 50)
        print("Speak to interact. Press Ctrl+C to exit.")
        print("=" * 50 + "\n")

        try:
            self.audio.start(self._on_audio_chunk)

            # Keep main thread alive
            while self.is_running:
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n\nShutting down...")

        finally:
            self.stop()

    def stop(self):
        """Stop the voice assistant."""
        self.is_running = False
        self.audio.stop()
        logger.info("Voice Assistant stopped")


def main():
    parser = argparse.ArgumentParser(
        description="Real-time voice assistant with low-latency streaming"
    )

    # Model options
    parser.add_argument(
        "--whisper-model",
        type=str,
        default="small.en",
        help="Whisper model size (tiny.en, base.en, small.en, medium.en)",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="af_heart",
        help="Kokoro voice ID",
    )

    # Vertex AI options
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="GCP project ID (uses GOOGLE_CLOUD_PROJECT env var if not set)",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="us-central1",
        help="Vertex AI location",
    )
    parser.add_argument(
        "--system-prompt",
        type=str,
        default=paty_instruction,
        help="Custom system prompt for the assistant",
    )

    # Audio options
    parser.add_argument(
        "--input-device",
        type=int,
        default=None,
        help="Input device index (use --list-devices to see available)",
    )
    parser.add_argument(
        "--output-device",
        type=int,
        default=None,
        help="Output device index",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio devices and exit",
    )

    # Debug options
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM for testing without API calls",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list_devices:
        list_devices()
        return

    assistant = VoiceAssistant(
        whisper_model=args.whisper_model,
        voice=args.voice,
        project=args.project,
        location=args.location,
        system_prompt=args.system_prompt,
        input_device=args.input_device,
        output_device=args.output_device,
        use_mock_llm=args.mock_llm,
    )

    assistant.run()


if __name__ == "__main__":
    main()