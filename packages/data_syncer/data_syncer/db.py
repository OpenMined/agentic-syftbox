from datetime import datetime
from pathlib import Path
import sqlite3

from notes_mcp.models.audio import AudioChunk

HOME = Path.home()

MEETINGS_DB_PATH = HOME / ".screenpipe" / "db.sqlite"
# MEETINGS_DB_PATH = HOME / ".meeting-notes-mcp" / "db.sqlite"
MEETINGS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Connect to the SQLite database
conn = sqlite3.connect(MEETINGS_DB_PATH)
conn.row_factory = sqlite3.Row


def get_db():
    try:
        conn = sqlite3.connect(MEETINGS_DB_PATH)
        conn.row_factory = sqlite3.Row
        create_tables(conn)
        yield conn
    finally:
        conn.close()


def create_tables(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meeting_meta (
            meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meeting_audio_chunks (
            meeting_id INTEGER,
            chunkid INTEGER,  
            FOREIGN KEY (meeting_id) REFERENCES meeting_meta(meeting_id),
            PRIMARY KEY (meeting_id, chunkid)
        );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audio_transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_chunk_id INTEGER NOT NULL,
    offset_index INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    transcription TEXT NOT NULL,
    device TEXT NOT NULL DEFAULT '',
    is_input_device BOOLEAN NOT NULL DEFAULT TRUE,
    speaker_id INTEGER,
    transcription_engine TEXT NOT NULL DEFAULT 'Whisper',
    start_time REAL,
    end_time REAL,
    text_length INTEGER)
""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audio_chunks (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    user_email TEXT NOT NULL)
""")
    conn.commit()


def insert_audio_chunk(
    conn, chunk_id: int, file_path: str, timestamp: datetime, user_email: str
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO audio_chunks (id, file_path, timestamp, user_email)
        VALUES (?, ?, ?, ?)
    """,
        (chunk_id, file_path, timestamp, user_email),
    )
    conn.commit()


def get_transcription_chunks(conn) -> tuple[list[AudioChunk], list[bool]]:
    cursor = conn.cursor()
    cursor.execute("""SELECT audio_transcriptions.*, meeting_audio_chunks.chunkid is NOT NULL as indexed  
                   FROM audio_transcriptions
                   LEFT JOIN meeting_audio_chunks on audio_transcriptions.audio_chunk_id = meeting_audio_chunks.chunkid""")
    rows = cursor.fetchall()
    chunks = [AudioChunk.from_sql_row(row) for row in rows]
    indexed = [row["indexed"] for row in rows]
    return chunks, indexed


def insert_meeting(conn, filename: str, chunks_ids: list[int]):
    """
    Insert meeting notes into the database.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO meeting_meta (filename)
        VALUES (?)
    """,
        (filename,),
    )
    meeting_id = cursor.lastrowid
    conn.commit()
    for chunk_id in chunks_ids:
        cursor.execute(
            """
            INSERT INTO meeting_audio_chunks (meeting_id, chunkid)
            VALUES (?, ?)
        """,
            (meeting_id, chunk_id),
        )
    conn.commit()


def insert_transcription(
    conn,
    transcription_id: int,
    audio_chunk_id: int,
    offset_index: int,
    timestamp: datetime,
    transcription: str,
    device: str,
    is_input_device: bool,
    speaker_id: int,
    transcription_engine: str,
    start_time: float,
    end_time: float,
    text_length: int,
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO audio_transcriptions (id, audio_chunk_id, offset_index, timestamp, transcription, device, is_input_device, speaker_id, transcription_engine, start_time, end_time, text_length)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            transcription_id,
            audio_chunk_id,
            offset_index,
            timestamp,
            transcription,
            device,
            is_input_device,
            speaker_id,
            transcription_engine,
            start_time,
            end_time,
            text_length,
        ),
    )
    conn.commit()


def get_meeting_meta(conn) -> list[dict[str, str]]:
    cursor = conn.cursor()
    get_all_meeting_notes_query = """
WITH meetings AS (
  SELECT
    mm.filename,
    MIN(at.timestamp) AS datetime,
  FROM (
    SELECT * FROM meeting_audio_chunks ORDER BY chunkid
  ) mc
  JOIN meeting_meta mm ON mc.meeting_id = mm.meeting_id
  JOIN audio_transcriptions at ON mc.chunkid = at.audio_chunk_id
  GROUP BY mc.meeting_id
  ORDER BY at.timestamp
)
SELECT *
FROM meetings;
"""
    cursor.execute(get_all_meeting_notes_query)
    return [dict(row) for row in cursor.fetchall()]


def get_meeting_notes_by_filename(conn, filename: str):
    cursor = conn.cursor()
    get_meeting_notes_by_filename_query = """
WITH meetings AS (
  SELECT
    mc.meeting_id,
    mm.filename,
    MIN(at.timestamp) AS start_date,
    MAX(at.timestamp) AS end_date,
    GROUP_CONCAT(at.transcription, ' ') AS full_text
  FROM (
    SELECT * FROM meeting_audio_chunks ORDER BY chunkid
  ) mc
  JOIN meeting_meta mm ON mc.meeting_id = mm.meeting_id
  JOIN audio_transcriptions at ON mc.chunkid = at.audio_chunk_id
  WHERE mm.filename = ?
  GROUP BY mc.meeting_id
  ORDER BY at.timestamp
)
SELECT *
FROM meetings;
"""
    cursor.execute(get_meeting_notes_by_filename_query, (filename,))
    return cursor.fetchone()["fulltext"]


def get_all_meeting_notes(conn):
    cursor = conn.cursor()
    get_all_meeting_notes_query = """
WITH meetings AS (
  SELECT
    mc.meeting_id,
    mm.filename,
    MIN(at.timestamp) AS start_date,
    MAX(at.timestamp) AS end_date,
    GROUP_CONCAT(at.transcription, ' ') AS full_text
  FROM (
    SELECT * FROM meeting_audio_chunks ORDER BY chunkid
  ) mc
  JOIN meeting_meta mm ON mc.meeting_id = mm.meeting_id
  JOIN audio_transcriptions at ON mc.chunkid = at.audio_chunk_id
  GROUP BY mc.meeting_id
  ORDER BY at.timestamp
)
SELECT *
FROM meetings;
"""
    cursor.execute(get_all_meeting_notes_query)
    return cursor.fetchall()
