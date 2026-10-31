"""
Mock Flask server for "Defuse the Downloads"
--------------------------------------------
Run:  python mock_server.py
Requires:  pip install flask flask-cors

Endpoints:
  GET  /files   → returns a list of fake file objects
  POST /action  → logs the action and returns a confirmation
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json, datetime

app = Flask(__name__)
CORS(app)   # allow requests from file:// or localhost

# ── Fake file data ──────────────────────────────────────────────
MOCK_FILES = [
    {"filename": "homework_FINAL_v3.pdf",        "ai_summary": "Boring essay about photosynthesis",          "recommended_folder": "School"},
    {"filename": "Screenshot 2024-01-14 093221.png", "ai_summary": "Random screenshot of a meme",            "recommended_folder": "Screenshots"},
    {"filename": "project_backup_OLD.zip",        "ai_summary": "Old project backup from 2 years ago",       "recommended_folder": "Archives"},
    {"filename": "funny_cat_video.mp4",           "ai_summary": "Cat falls off a shelf, very relatable",     "recommended_folder": "Videos"},
    {"filename": "taxes_2023_DRAFT.xlsx",         "ai_summary": "Incomplete tax spreadsheet",                "recommended_folder": "Finance"},
    {"filename": "setup_legacy_app.exe",          "ai_summary": "Installer for software you no longer use",  "recommended_folder": "Installers"},
    {"filename": "meeting_notes_june.docx",       "ai_summary": "Meeting notes from June — long outdated",   "recommended_folder": "Work"},
    {"filename": "unnamed_song_draft.mp3",        "ai_summary": "15-second guitar loop, never finished",     "recommended_folder": "Music"},
    {"filename": "resume_2019.pdf",               "ai_summary": "Your old resume, several jobs behind",      "recommended_folder": "Personal"},
    {"filename": "invoice_unpaid.pdf",            "ai_summary": "An invoice — might still matter!",          "recommended_folder": "Finance"},
    {"filename": "vacation_photos_raw.zip",       "ai_summary": "2,340 unedited RAW photos from Bali trip",  "recommended_folder": "Photos"},
    {"filename": "minecraft_mod_v1.jar",          "ai_summary": "Mod you downloaded, never installed",       "recommended_folder": "Games"},
    {"filename": "database_backup_dev.sql",       "ai_summary": "Dev DB dump from a project you shipped",    "recommended_folder": "Dev"},
    {"filename": "design_mockup_FINAL2.psd",      "ai_summary": "Client mockup — project was cancelled",     "recommended_folder": "Design"},
    {"filename": "random_notes.txt",              "ai_summary": "'buy milk' written 47 times",              "recommended_folder": "Notes"},
]

log_entries = []

@app.get("/files")
def get_files():
    print(f"[{ts()}] GET /files — returning {len(MOCK_FILES)} files")
    return jsonify(MOCK_FILES)

@app.post("/action")
def post_action():
    body = request.get_json(silent=True) or {}
    filename = body.get("filename", "unknown")
    action   = body.get("action",   "unknown")

    entry = {"time": ts(), "filename": filename, "action": action}
    log_entries.append(entry)

    emoji = "💥" if action == "trash" else "🛡️"
    dest  = "Trash" if action == "trash" else "organised folder"
    print(f"[{ts()}] POST /action  {emoji}  {action.upper():8s}  {filename}")

    return jsonify({
        "ok": True,
        "message": f"{filename} sent to {dest}",
        "log": entry,
    })

@app.get("/log")
def get_log():
    """Bonus endpoint: view all processed actions."""
    return jsonify(log_entries)

def ts():
    return datetime.datetime.now().strftime("%H:%M:%S")

if __name__ == "__main__":
    print("=" * 55)
    print("  🎮  Defuse the Downloads  —  Mock Server")
    print("=" * 55)
    print(f"  Serving {len(MOCK_FILES)} fake files")
    print(f"  GET  http://127.0.0.1:5000/files")
    print(f"  POST http://127.0.0.1:5000/action")
    print(f"  GET  http://127.0.0.1:5000/log   (audit trail)")
    print("=" * 55)
    app.run(host="127.0.0.1", port=5000, debug=True)
