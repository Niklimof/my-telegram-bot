# core/services/transcriber.py
import whisper
import logging

logger = logging.getLogger(__name__)

class Transcriber:
    def __init__(self, model_size="base"):
        logger.info(f"Loading Whisper model: {model_size}")
        self.model = whisper.load_model(model_size)
    
    async def transcribe(self, audio_path: str):
        logger.info(f"Transcribing audio: {audio_path}")
        
        result = self.model.transcribe(
            audio_path,
            language="ru",
            task="transcribe"
        )
        
        return {
            "text": result["text"],
            "language": "ru"
        }