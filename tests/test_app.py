"""
Unit & Integration Tests for Defuse the Downloads
===================================================
Tests core gameplay APIs, deep file classification, auto-lint repairs,
undo transactional history, and path traversal security guards.
"""

from __future__ import annotations

import json
import os
import shutil
import pytest
from pathlib import Path

# Add project root to path for imports
import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app import app, MESSY_DIR, ORGANIZED_DIR, TRASH_DIR, SUBFOLDERS


@pytest.fixture
def client():
    """Create Flask test client with clean isolated state."""
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        # Seed files before testing
        test_client.post("/seed")
        yield test_client


def test_serve_index(client):
    """Verify single-server frontend delivery on GET /."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Defuse the Downloads" in response.data or b"root" in response.data


def test_health_check(client):
    """Verify GET /health probe endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert "version" in data


def test_seed_files(client):
    """Verify POST /seed creates all 14 realistic demo targets."""
    response = client.post("/seed")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["count"] == 14
    assert len(data["files_created"]) == 14
    assert "mystery_note_123.txt" in data["files_created"]
    assert "buggy_script.py" in data["files_created"]


def test_get_files_deep_inspection(client):
    """Verify GET /files returns classifications with deep content scanning."""
    response = client.get("/files")
    assert response.status_code == 200
    files = response.get_json()
    assert isinstance(files, list)
    assert len(files) == 14

    # Verify deep inspection on mystery_note_123.txt (classified as Receipts despite .txt ext)
    mystery = next((f for f in files if f["filename"] == "mystery_note_123.txt"), None)
    assert mystery is not None
    assert mystery["subfolder"] == "Receipts"
    assert mystery["recommended_action"] == "organize"
    assert mystery["deep_scanned"] is True

    # Verify deep inspection on buggy_script.py
    buggy = next((f for f in files if f["filename"] == "buggy_script.py"), None)
    assert buggy is not None
    assert buggy["subfolder"] == "Code"
    assert buggy["deep_scanned"] is True


def test_action_trash(client):
    """Verify Left-Click TRASH physically moves file to Trash_Bin."""
    target_file = "temp_cache_dump.log"
    assert (MESSY_DIR / target_file).is_file()

    response = client.post("/action", json={"filename": target_file, "action": "trash"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True

    # Verify physical file locations
    assert not (MESSY_DIR / target_file).exists()
    assert (TRASH_DIR / target_file).is_file()


def test_action_organize_and_lint_fix(client):
    """Verify Right-Click ORGANIZE formats Python lint errors and stamps header."""
    target_file = "buggy_script.py"
    assert (MESSY_DIR / target_file).is_file()

    response = client.post(
        "/action",
        json={"filename": target_file, "action": "organize", "subfolder": "Code"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["lint_fixed"] is True

    # Verify file is moved and cleaned
    organized_file = ORGANIZED_DIR / "Code" / target_file
    assert organized_file.is_file()
    assert not (MESSY_DIR / target_file).exists()

    content = organized_file.read_text(encoding="utf-8")
    assert "[AI LINT FIXER]" in content
    assert "def calculate_messy_sum(a, b):" in content


def test_action_undo(client):
    """Verify UNDO restores last moved file back into Messy_Downloads."""
    target_file = "untitled_meme_final.jpg"
    assert (MESSY_DIR / target_file).is_file()

    # Move to trash first
    client.post("/action", json={"filename": target_file, "action": "trash"})
    assert not (MESSY_DIR / target_file).exists()

    # Perform undo
    response = client.post("/action", json={"action": "undo"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["filename"] == target_file

    # Verify file restored to Messy_Downloads
    assert (MESSY_DIR / target_file).is_file()


def test_stats_telemetry(client):
    """Verify GET /stats returns live accurate counts across folders."""
    response = client.get("/stats")
    assert response.status_code == 200
    stats = response.get_json()
    assert "messy_downloads" in stats
    assert "trash_bin" in stats
    assert "organized_safe" in stats
    assert "total_organized" in stats
    assert isinstance(stats["organized_safe"], dict)


def test_security_path_traversal_blocked(client):
    """Security Test: Verify path traversal attempts are strictly intercepted with HTTP 400."""
    malicious_inputs = [
        "../../etc/passwd",
        "..\\..\\Windows\\System32\\calc.exe",
        "../secret.key",
        "subfolder/file.txt",
        "..",
        "/etc/shadow",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
    ]

    for attack in malicious_inputs:
        response = client.post("/action", json={"filename": attack, "action": "trash"})
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data


def test_security_invalid_subfolder_blocked(client):
    """Security Test: Verify illegal subfolder destinations are rejected."""
    response = client.post(
        "/action",
        json={"filename": "mystery_note_123.txt", "action": "organize", "subfolder": "../../System32"}
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_security_invalid_action_rejected(client):
    """Verify unknown action strings are cleanly rejected."""
    response = client.post(
        "/action",
        json={"filename": "mystery_note_123.txt", "action": "format_c_drive"}
    )
    assert response.status_code == 400
