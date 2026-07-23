import io

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import current_user
from app.core.errors import VoiceServiceError
from app.voice import sarvam

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(file: UploadFile, _user: str = Depends(current_user)):
    audio = await file.read()
    try:
        transcript, language = sarvam.transcribe(audio, file.filename or "audio.wav")
    except VoiceServiceError as e:
        # Degrade gracefully — the client can still type. Never 500 the turn.
        return JSONResponse(
            {"error_code": e.code, "message": "Voice service briefly unavailable — please type."},
            status_code=200,
        )
    return {"transcript": transcript, "language": language}


@router.post("/speak")
def speak(text: str = Form(...), language: str = Form("en-IN"), _user: str = Depends(current_user)):
    try:
        audio = sarvam.speak(text, language)
    except VoiceServiceError as e:
        return JSONResponse(
            {"error_code": e.code, "message": "Voice reply unavailable — here's the text."},
            status_code=200,
        )
    return StreamingResponse(io.BytesIO(audio), media_type="audio/wav")
