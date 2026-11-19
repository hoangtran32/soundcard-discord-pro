from contextlib import closing, contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4


class AlbumLibrary:
    def __init__(self, path=Path("data/albums.sqlite3")):
        self.path = path

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            yield db

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS profiles (
                    username TEXT PRIMARY KEY,
                    salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS albums (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES profiles(username),
                    name TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS albums_by_owner ON albums(username);
                CREATE TABLE IF NOT EXISTS album_tracks (
                    position INTEGER PRIMARY KEY,
                    id TEXT NOT NULL UNIQUE,
                    album_id TEXT NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    track_json TEXT NOT NULL,
                    UNIQUE(album_id, url)
                );
            """)

    @staticmethod
    def password_hash(password, salt):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)

    def register(self, username, password):
        salt = secrets.token_bytes(16)
        password_hash = self.password_hash(password, salt)
        with self.connect() as db:
            return bool(db.execute(
                "INSERT OR IGNORE INTO profiles VALUES (?, ?, ?)", (username, salt, password_hash)
            ).rowcount)

    def verify(self, username, password):
        with self.connect() as db:
            profile = db.execute("SELECT * FROM profiles WHERE username = ?", (username,)).fetchone()
        salt = profile["salt"] if profile else bytes(16)
        digest = self.password_hash(password, salt)
        return profile is not None and hmac.compare_digest(digest, profile["password_hash"])

    def list_albums(self, username):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT albums.id, albums.name, count(album_tracks.position) AS track_count
                FROM albums LEFT JOIN album_tracks ON albums.id = album_tracks.album_id
                WHERE username = ?
                GROUP BY albums.id
                ORDER BY albums.rowid
            """, (username,))]

    def get_album(self, username, album_id):
        with self.connect() as db:
            album = db.execute(
                "SELECT id, name FROM albums WHERE username = ? AND id = ?", (username, album_id)
            ).fetchone()
            if album is None:
                return None
            tracks = db.execute(
                "SELECT id, track_json FROM album_tracks WHERE album_id = ? ORDER BY position", (album_id,)
            ).fetchall()
            return {**dict(album), "tracks": [{**json.loads(row["track_json"]), "id": row["id"]} for row in tracks]}

    def create_album(self, username, name):
        album_id = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO albums VALUES (?, ?, ?)", (album_id, username, name))
        return {"id": album_id, "name": name, "tracks": []}

    def delete_album(self, username, album_id):
        with self.connect() as db:
            return bool(db.execute(
                "DELETE FROM albums WHERE username = ? AND id = ?", (username, album_id)
            ).rowcount)

    def add_tracks(self, username, album_id, tracks):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM albums WHERE username = ? AND id = ?", (username, album_id)
            ).fetchone():
                return None
            rows = [(uuid4().hex, album_id, track["url"], json.dumps(track, ensure_ascii=False))
                    for track in tracks]
            return db.executemany(
                "INSERT OR IGNORE INTO album_tracks (id, album_id, url, track_json) VALUES (?, ?, ?, ?)", rows
            ).rowcount

    def delete_track(self, username, album_id, track_id):
        with self.connect() as db:
            return bool(db.execute("""
                DELETE FROM album_tracks
                WHERE album_id IN (SELECT id FROM albums WHERE username = ? AND id = ?)
                AND id = ?
            """, (username, album_id, track_id)).rowcount)


album_library = AlbumLibrary()
