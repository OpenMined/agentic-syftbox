import base64
import os
import random
import threading
import time
from datetime import datetime

import requests
from fastsyftbox.simple_client import SimpleRPCClient

from notes_mcp import db
from notes_mcp.models.file import FilesToSyncResponse, FileToSync

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]


# file_path = HOME / ".screenpipe" / "data" / "MacBook Pro Microphone (input)_2025-06-03_14-30-45.mp4"
# FILE_PATH = 'path/to/your/audio.wav'  # Local WAV file (16kHz sample rate)


def add_transcription_to_db(
    conn, bts, audio_chunk_id: int, device: str, timestamp: datetime
):
    transcript = transcribe(bts)
    text_length = len(transcript)
    # TODO: FIX
    # start_time and end_time are not set
    # offset_index is not set
    # speaker_id is not set
    # timestamp is not set
    transcription_id = random.randint(0, 1000000)
    db.insert_transcription(
        conn,
        transcription_id=transcription_id,
        audio_chunk_id=audio_chunk_id,
        offset_index=0,
        timestamp=timestamp,
        transcription=transcript,
        device=device,
        is_input_device=True,
        speaker_id=0,
        transcription_engine="deepgram",
        start_time=0,
        end_time=0,
        text_length=text_length,
    )


def poll_for_new_audio_chunks(stop_event: threading.Event):
    while not stop_event.is_set():
        client = SimpleRPCClient(app_name="data-syncer", dev_mode=True)
        print("Polling for new audio chunks")
        try:
            result = client.post("/get_latest_file_to_sync")
            result.raise_for_status()
            file = FilesToSyncResponse.model_validate_json(result.json()).file
            if file is not None:
                print("Got file to transcribe and upload", file)
                bts = base64.b64decode(file.encoded_bts)
                transcript = transcribe(bts)
                print("transcription succesful, uploading to data-syncer")
                upload_transcription_to_data_syncer(client, transcript, file)
            else:
                print("No file to sync")

        except Exception as e:
            print(
                f"Could not reach user {client.app_owner} on {client.app_name}/get_latest_file_to_sync: {e}"
            )

        time.sleep(10)


def upload_transcription_to_data_syncer(
    client: SimpleRPCClient, transcription: str, file: FileToSync
):
    # Prepare the payload for the data_syncer API
    payload = {
        "transcription": transcription,  # No transcription yet, just the audio chunk info
        "id": file.id,
        "timestamp": file.timestamp,
        "user_email": file.user_email,
        "device": file.device,
    }

    res = client.post("/submit_transcription", json=payload)
    print("sucesffully uploaded to data-syncer")
    res.raise_for_status()


def transcribe(bytes_data: bytes):
    response = requests.post(
        "https://api.deepgram.com/v1/listen",
        headers={
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "audio/wav",
        },
        params={"model": "nova-2", "smart_format": "true", "sample_rate": "16000"},
        data=bytes_data,
    )
    res = response.json()
    transcript = res["results"]["channels"][0]["alternatives"][0]["transcript"]
    return transcript
