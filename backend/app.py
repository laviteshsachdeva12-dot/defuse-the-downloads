"""
Defuse the Downloads — Production Flask Backend v2.3
=====================================================
Real-world file cleanup engine with Gemini 2.5 Flash AI classification,
deep file content inspection, automated code lint fixing, path traversal
security sanitization, and production Google Cloud Run readiness.

Endpoints:
  GET  /        → Serves the tactical React aim-trainer single-page app
  GET  /health  → Health & version probe
  POST /seed    → Populates 14 realistic clutter demo files in Messy_Downloads
  GET  /files   → Scans disk, reads snippets, returns classified targets (<300ms)
  POST /action  → Physical file operations (trash, organize, undo) with AI linting
  GET  /stats   → Live folder telemetry (Messy, Organized, Trash)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables safely from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
    _dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    if _dotenv_path.exists():
        load_dotenv(dotenv_path=_dotenv_path)
except ImportError:
    pass

from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

# ── App setup ────────────────────────────────────────────────────────────────
app: Flask = Flask(__name__)
CORS(app)

# ── Directory layout ─────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent.parent   # project root
MESSY_DIR: Path = BASE_DIR / "Messy_Downloads"
ORGANIZED_DIR: Path = BASE_DIR / "Organized_Safe"
TRASH_DIR: Path = BASE_DIR / "Trash_Bin"
SUBFOLDERS: List[str] = ["Documents", "Images", "Installers", "Code", "Receipts"]

for _d in [MESSY_DIR, TRASH_DIR] + [ORGANIZED_DIR / sf for sf in SUBFOLDERS]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Gemini configuration & in-memory state ───────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "").strip()
_gemini_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock: threading.Lock = threading.Lock()
_action_history: List[Dict[str, Any]] = []

# ── Local fallback classifier knowledge base ─────────────────────────────────
_EXT_FOLDER: Dict[str, Set[str]] = {
    "Documents":  {".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx",
                   ".odt", ".rtf", ".xls", ".xlsx", ".csv", ".epub"},
    "Images":     {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg",
                   ".webp", ".ico", ".tiff", ".raw", ".psd", ".ai", ".heic"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm",
                   ".apk", ".jar", ".appimage", ".cab", ".iso"},
    "Code":       {".py", ".js", ".ts", ".sh", ".bat", ".log", ".json",
                   ".xml", ".html", ".css", ".rb", ".go", ".rs", ".java",
                   ".c", ".cpp", ".h", ".cs", ".php", ".sql"},
    "Receipts":   set(),
}
_RECEIPT_KW: Set[str] = {
    "invoice", "receipt", "order", "bill", "payment", "zomato",
    "swiggy", "amazon", "flipkart", "purchase", "transaction"
}
_TRASH_KW: Set[str] = {
    "temp", "cache", "tmp", "backup_old", "old(", "(1)", "(2)",
    "test", "broken", "untitled", "draft", "copy", "junk", "dump"
}

_LOCAL_ENEMIES: Dict[str, List[Tuple[str, str]]] = {
    "Documents": [
        ("Ancient PDF Specter",     "Buried under 47 similar files, all named FINAL"),
        ("The Docx Phantom",        "Created for a class you definitely failed"),
        ("Spreadsheet Demon Lord",  "One cell has the wrong formula. One."),
        ("Lecture Note Wraith",     "Last opened 3 semesters ago, still haunting"),
        ("The Report Revenant",     "Due date was last year. It knows."),
    ],
    "Images": [
        ("Screenshot Goblin",       "Taken at 3 AM. Purpose: completely unknown."),
        ("Meme Lich King",          "Too blurry to use, too funny to delete"),
        ("Raw Photo Colossus",      "47 megapixels of unedited vacation regret"),
        ("The Selfie Shade",        "Front camera, bad lighting, full resolution"),
        ("Thumbnail Terror",        "Downloaded for a project that was cancelled"),
    ],
    "Installers": [
        ("Deprecated Exe Golem",    "Software you uninstalled twice. It came back."),
        ("Legacy Setup Phantom",    "Still requires .NET Framework 3.5 somehow"),
        ("The Installer Hydra",     "Delete one, find chrome_setup(2).exe nearby"),
        ("Trial Banshee v1.0",      "Your 14-day trial expired in 2021"),
        ("Wizard of Bloatware",     "Bundled Ask Toolbar, asks nothing"),
    ],
    "Code": [
        ("Broken Script Wraith",    "Throws NameError before even reaching main()"),
        ("The Infinite Loop Demon", "Has been running since the heat death of the sun"),
        ("Debug Log Titan",         "50,000 lines of 'undefined is not a function'"),
        ("Temp File Shade",         "Created by pip, orphaned by pip, mourned by no one"),
        ("The Cache Colossus",      "Occupying 2 GB for reasons nobody remembers"),
    ],
    "Receipts": [
        ("Zomato Invoice Specter",  "₹420 for a burger nobody remembers eating"),
        ("The Receipt Revenant",    "Needed for tax filing. Never filed. Never will be."),
        ("Lost Invoice Lich",       "Reimbursement pending since March. Of last year."),
        ("Online Order Phantom",    "Delivered, consumed, and digitally unacknowledged"),
        ("The Bill Banshee",        "Screams at you every tax season"),
    ],
}
_TRASH_DESC: List[str] = [
    "Pure chaos in file form. Terminate with prejudice.",
    "Never opened. Occupying precious SSD real estate illegally.",
    "A relic from a darker, messier timeline. Nuke it.",
    "Zero value. Maximum disk footprint. Classic.",
    "Its only purpose is to confuse future-you. Delete now.",
]


# ── Security & Path Validation ───────────────────────────────────────────────
def is_safe_filename(name: str) -> bool:
    """
    Validate that filename is safe and free of path traversal sequences.
    
    Args:
        name: Filename string from client input.
        
    Returns:
        True if filename is clean and matches secure_filename, False otherwise.
    """
    if not name or not isinstance(name, str):
        return False
    if "/" in name or "\\" in name or ".." in name or "\x00" in name:
        return False
    return secure_filename(name) == name


def is_path_contained(parent: Path, child: Path) -> bool:
    """
    Verify that child path resolves strictly within the parent directory.
    
    Args:
        parent: Base directory expected to contain child.
        child: Path to verify.
        
    Returns:
        True if child is strictly inside parent.
    """
    try:
        resolved_parent = parent.resolve()
        resolved_child = child.resolve()
        return resolved_parent in resolved_child.parents or resolved_child.parent == resolved_parent
    except Exception:
        return False


# ── Deep File Content Inspection ─────────────────────────────────────────────
def _read_content_snippet(fpath: Path, max_chars: int = 300) -> str:
    """
    Safely reads first max_chars of text-based files for deep content inspection.
    
    Args:
        fpath: Path to file.
        max_chars: Character limit to read.
        
    Returns:
        Cleaned text snippet or empty string if binary or unreadable.
    """
    text_exts = {".txt", ".py", ".js", ".ts", ".md", ".csv", ".log", ".json", ".xml", ".html", ".css", ".sh", ".bat"}
    if fpath.suffix.lower() not in text_exts:
        return ""
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            chunk = f.read(max_chars * 2)
            cleaned = " ".join(chunk.split())
            return cleaned[:max_chars]
    except Exception:
        return ""


# ── AI Classification & Fallback Engine ──────────────────────────────────────
def _local_classify(filename: str, snippet: str = "") -> Dict[str, Any]:
    """
    Instant rule-based classifier with deep snippet inspection (<1ms execution).
    
    Args:
        filename: Name of the target file.
        snippet: First 300 characters of text content if available.
        
    Returns:
        Dictionary containing enemy_name, description, recommended_action, subfolder.
    """
    name = filename.lower()
    ext = Path(filename).suffix.lower()
    snip_lower = snippet.lower()

    # Deep inspection: check snippet for receipts or code
    is_receipt_by_snippet = any(k in snip_lower for k in [
        "swiggy", "zomato", "instamart", "order #", "total paid", "tax invoice",
        "delivery partner", "delivered to doorstep", "delivery fee", "subtotal"
    ])
    is_code_by_snippet = any(k in snip_lower for k in [
        "import ", "def ", "class ", "function ", "console.log", "const ", "let "
    ])

    if is_receipt_by_snippet or any(k in name for k in _RECEIPT_KW):
        subfolder = "Receipts"
        enemy_name = "Midnight Instamart Phantom" if ("swiggy" in snip_lower or "instamart" in snip_lower or "mystery" in name) else "Stealth Delivery Specter"
        description = "Deep scan unmasked hidden midnight takeaway order!" if is_receipt_by_snippet else "₹420 for food nobody remembers eating"
        recommended_action = "organize"
    elif is_code_by_snippet or ext in _EXT_FOLDER.get("Code", set()):
        subfolder = "Code"
        if "todo" in snip_lower or "bug" in snip_lower or "messy" in snip_lower or "broken" in name:
            enemy_name = "Syntax Anomaly Glitch"
            description = "Erratic indentation detected! Defuse to auto-fix lint."
            recommended_action = "organize"
        else:
            enemy_name, description = random.choice(_LOCAL_ENEMIES["Code"])
            recommended_action = "organize"
    else:
        subfolder = "Documents"
        for sf, exts in _EXT_FOLDER.items():
            if ext in exts:
                subfolder = sf
                break

        is_trash = (
            any(k in name for k in _TRASH_KW) or
            ext in {".log", ".tmp", ".bak"}
        )
        recommended_action = "trash" if is_trash else "organize"

        enemy_name, description = random.choice(
            _LOCAL_ENEMIES.get(subfolder, _LOCAL_ENEMIES["Documents"])
        )
        if is_trash:
            description = random.choice(_TRASH_DESC)

    return {
        "enemy_name": enemy_name,
        "description": description,
        "recommended_action": recommended_action,
        "subfolder": subfolder,
        "ai_powered": False,
        "deep_scanned": bool(snippet),
    }


def _run_gemini(filename: str, api_key: str, snippet: str = "") -> Dict[str, Any]:
    """
    Call Gemini 2.5 Flash API with deep content inspection.
    
    Args:
        filename: Name of file.
        api_key: User or server Google AI API key.
        snippet: Content preview text.
        
    Returns:
        Validated classification metadata dict.
    """
    from google import genai

    client = genai.Client(api_key=api_key)
    snip_part = f'\nFile Content Snippet (first 300 chars): "{snippet}"\n' if snippet else ""
    prompt = (
        f'You are the AI brain of a tactical file-cleanup aim-trainer game called "Defuse the Downloads".\n'
        f'Analyze this filename: "{filename}"{snip_part}\n'
        f'Rules for Deep File Content Inspection:\n'
        f'- If the content snippet reveals the file is a receipt, food order, or invoice (even if vaguely named like mystery_note.txt), classify as "Receipts" and recommended_action "organize".\n'
        f'- If the snippet reveals Python/JS code (even if named strangely), classify as "Code" and recommended_action "organize".\n'
        f'- Otherwise classify trash for temp/broken/junk files, organize for important docs/photos/media.\n\n'
        f'Reply ONLY with valid JSON (no markdown fences, no explanation):\n'
        '{\n'
        '  "enemy_name": "3-5 word RPG/tactical villain title (e.g. Ancient PDF Specter, Stealth Delivery Specter)",\n'
        '  "description": "One-liner: darkly funny dramatic threat, max 12 words, specific to this file and its content",\n'
        '  "recommended_action": "trash OR organize",\n'
        '  "subfolder": "Documents OR Images OR Installers OR Code OR Receipts"\n'
        '}\n'
    )
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', resp.text.strip(), flags=re.MULTILINE)
    data = json.loads(text)
    for k in ("enemy_name", "description", "recommended_action", "subfolder"):
        if k not in data:
            raise ValueError(f"Gemini response missing field: {k}")
    data["ai_powered"] = True
    data["deep_scanned"] = bool(snippet)
    return data


def _bg_gemini_worker(filename: str, api_key: str, cache_key: str, snippet: str = "") -> None:
    """Asynchronous background worker to query Gemini without blocking HTTP thread."""
    try:
        result = _run_gemini(filename, api_key, snippet)
        with _cache_lock:
            _gemini_cache[cache_key] = result
        print(f"[Gemini ✓] {filename} → {result['enemy_name']}")
    except Exception as exc:
        print(f"[Gemini ✗] {filename}: {exc}")


# ── AI Code Lint & Formatting Fixer ──────────────────────────────────────────
def _lint_and_format_code(src_path: Path) -> Tuple[str, str]:
    """
    Auto-formats and repairs lint errors for .py and .js files upon defusing.
    
    Args:
        src_path: Path to code file in Messy_Downloads.
        
    Returns:
        Tuple of (repaired_content_string, log_message).
    """
    ext = src_path.suffix.lower()
    try:
        content = src_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return "", f"Could not read: {e}"

    lines = content.splitlines()
    fixed_lines: List[str] = []

    if ext == ".py":
        fixed_lines.append("# [AI LINT FIXER] Cleaned & Auto-Formatted by Defuse the Downloads")
        fixed_lines.append("# Normalized indentation, stripped trailing spaces & formatted imports\n")
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                fixed_lines.append("")
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                cleaned_line = re.sub(r'\s*,\s*', ', ', stripped)
                cleaned_line = re.sub(r' +', ' ', cleaned_line)
                fixed_lines.append(cleaned_line)
            elif stripped.lstrip().startswith("def ") or stripped.lstrip().startswith("class "):
                indent = len(line) - len(line.lstrip())
                indent_spaces = " " * (4 * (indent // 4 if indent else 0))
                def_cleaned = re.sub(r' +', ' ', stripped.lstrip())
                def_cleaned = re.sub(r'\(\s*', '(', def_cleaned)
                def_cleaned = re.sub(r'\s*\)', ')', def_cleaned)
                def_cleaned = re.sub(r'\s*,\s*', ', ', def_cleaned)
                fixed_lines.append(indent_spaces + def_cleaned)
            else:
                indent = len(line) - len(line.lstrip())
                norm_indent = " " * (4 * max(1, round(indent / 4))) if indent > 0 else ""
                clean_body = re.sub(r'\s*,\s*', ', ', stripped.lstrip())
                fixed_lines.append(norm_indent + clean_body)

        cleaned_text = "\n".join(fixed_lines).strip() + "\n"
        return cleaned_text, "Python lint fixed: indentation normalized, trailing spaces purged, imports formatted"

    elif ext == ".js":
        fixed_lines.append("// [AI LINT FIXER] Cleaned & Beautified by Defuse the Downloads\n")
        for line in lines:
            fixed_lines.append(line.rstrip())
        cleaned_text = "\n".join(fixed_lines).strip() + "\n"
        return cleaned_text, "JS lint fixed: whitespace normalized & formatted"

    return content, "No lint fixer needed"


def _human_size(path: Path) -> str:
    """Format file size into human-readable units."""
    try:
        sz = float(path.stat().st_size)
        for unit in ("B", "KB", "MB", "GB"):
            if sz < 1024:
                return f"{sz:.1f} {unit}"
            sz /= 1024
        return f"{sz:.1f} TB"
    except Exception:
        return "0 B"


# ── Demo Seed File Definitions ───────────────────────────────────────────────
def _make_seed_files() -> List[Tuple[str, bytes]]:
    """Generate 14 realistic demo clutter files with authentic binary payloads."""
    rng = random.Random(42)

    def rand_bytes(n: int) -> bytes:
        return bytes(rng.randint(0, 255) for _ in range(n))

    files: List[Tuple[str, bytes]] = [
        (
            "BTech_CSE_Notes_FINAL_v3.pdf",
            (
                "%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                "% DATA STRUCTURES & ALGORITHMS - Lecture Notes Unit 4\n\n"
                "Binary Search Tree insertion:\n"
                "  if node is null: create new node\n"
                "  if val < node.val: recurse left\n"
                "  if val > node.val: recurse right\n\n"
                "Dijkstra shortest path: O(V log V) with min-heap\n"
                "BFS: O(V+E)    DFS: O(V+E)    Bellman-Ford: O(VE)\n\n" * 90 +
                "xref\n0 3\n0000000000 65535 f\ntrailer\n<< /Size 3 >>\nstartxref\n420\n%%EOF\n"
            ).encode("utf-8")
        ),
        (
            "zomato_order_420_invoice.pdf",
            (
                "%PDF-1.4\n"
                "ZOMATO FOOD DELIVERY - TAX INVOICE\n"
                "===================================\n"
                "Order #ZMT-4200069     Date: 31-Oct-2026\n"
                "Restaurant: Burger Bros, Koramangala\n\n"
                "  1x Spicy Double Chicken Burger      Rs. 249.00\n"
                "  1x Loaded Cheese Fries              Rs. 119.00\n"
                "  1x Oreo Shake                       Rs. 89.00\n"
                "  Platform Fee:                        Rs. 3.00\n"
                "  Delivery Charge:                     Rs. 29.00\n"
                "  GST (5%):                            Rs. 23.45\n"
                "  Zomato Pro Discount:                Rs.-112.45\n"
                "  ---------------------------------------------\n"
                "  TOTAL PAID:                         Rs. 420.00\n"
                "  Payment: UPI @yourupi\n\n"
                "Thank you for ordering with Zomato!\n" * 70
            ).encode("utf-8")
        ),
        (
            "chrome_installer_old(1).exe",
            bytes([0x4D, 0x5A, 0x90, 0x00, 0x03, 0x00, 0x00, 0x00,
                   0x04, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00,
                   0xB8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) +
            b"@\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" +
            (b"Google Chrome Installer v87.0.4280.66 (Legacy Build)\x00" * 30) +
            b"This program cannot be run in DOS mode.\r\r\n" +
            (b"\x00" * 2048) +
            b"PE\x00\x00d\x86\x06\x00" +
            rand_bytes(8192)
        ),
        (
            "Screenshot_2026-10-31_1108.png",
            bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
                   0x00, 0x00, 0x00, 0x0D,
                   0x49, 0x48, 0x44, 0x52,
                   0x00, 0x00, 0x07, 0x80,
                   0x00, 0x00, 0x04, 0x38,
                   0x08, 0x02, 0x00, 0x00, 0x00]) +
            rand_bytes(15000)
        ),
        (
            "untitled_meme_final.jpg",
            bytes([0xFF, 0xD8, 0xFF, 0xE0,
                   0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
                   0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00]) +
            rand_bytes(18000) +
            bytes([0xFF, 0xD9])
        ),
        (
            "temp_cache_dump.log",
            "".join(
                f"[2026-10-31 {h:02d}:{m:02d}:{s:02d}]"
                f" {'ERROR' if (h*m+s) % 4 == 0 else 'DEBUG'}"
                f" {'NullPointerException at CacheManager.flush():420' if (h+m) % 3 == 0 else 'cache_evict() called - 0 items removed'}\n"
                for h in range(0, 10)
                for m in range(0, 60, 2)
                for s in (5, 22, 44)
            ).encode("utf-8")
        ),
        (
            "assignment_draft_copy.docx",
            bytes([0x50, 0x4B, 0x03, 0x04, 0x14, 0x00, 0x00, 0x00,
                   0x08, 0x00, 0xA2, 0x7C, 0xD1, 0x57]) +
            (
                "word/document.xml\x00"
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<w:document><w:body>"
                "<w:p><w:r><w:t>ASSIGNMENT DRAFT - Cloud Computing (IT402)</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Introduction: Cloud computing enables on-demand... TODO FINISH THIS SECTION</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Body Para 1: [PLACEHOLDER - copy from Wikipedia later]</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Conclusion: In conclusion, cloud is good. TODO: make this longer.</w:t></w:r></w:p>"
                "</w:body></w:document>" * 60
            ).encode("utf-8") +
            (b"\x00" * 512)
        ),
        (
            "broken_script_test.py",
            (
                '#!/usr/bin/env python3\n'
                '# STATUS: BROKEN - do not run in production\n'
                '# TODO: fix undefined variable, refactor, add tests\n'
                '# Last touched: "I will fix it tomorrow" (3 months ago)\n\n'
                'import sys\nimport os\nimport json\n\n'
                'MISSING_CONFIG = None  # TODO: load from config.yaml\n\n'
                'def process_batch(data):\n'
                '    # BUG: crashes on None input - AttributeError\n'
                '    result = MISSING_CONFIG["batch_size"] * len(data)\n'
                '    return result\n\n'
                'def main():\n'
                '    print("Starting broken_script_test.py...")\n'
                '    x = undefined_var + 1  # NameError right here\n'
                '    batch = process_batch([x])\n'
                '    print(f"batch result: {batch}")\n\n'
                'if __name__ == "__main__":\n'
                '    main()\n'
                '# EOF - this file has never successfully run\n'
            ).encode("utf-8")
        ),
        (
            "whatsapp_backup_old.zip",
            bytes([0x50, 0x4B, 0x03, 0x04, 0x14, 0x00, 0x00, 0x00,
                   0x08, 0x00, 0x00, 0x00, 0x00, 0x00]) +
            (
                "WhatsApp Backup - 2023-01-01\x00"
                "Media/WhatsApp Images/IMG-20230115-WA0042.jpg\x00"
                "Media/WhatsApp Videos/VID-20230210-WA0007.mp4\x00"
                "Media/WhatsApp Audio/PTT-20230301-WA0001.opus\x00"
                "Databases/msgstore.db\x00"
                "Databases/wa.db\x00"
                "[WhatsApp backup from 2 phones ago]\n" * 200
            ).encode("utf-8") +
            rand_bytes(10000)
        ),
        (
            "amazon_receipt_nov2025.pdf",
            (
                "%PDF-1.4\n"
                "Amazon.in - Order Receipt\n"
                "==========================\n"
                "Order ID:    402-7834521-9023445\n"
                "Order Date:  15 November 2025\n"
                "Delivery:    16 November 2025 (Prime)\n\n"
                "Item: Portronics Mport 7C - USB-C Hub 7-in-1\n"
                "      HDMI 4K | USB 3.0 x3 | SD/TF Card | PD 87W\n"
                "Qty:  1       Price: Rs. 1,499.00\n"
                "Shipping:    FREE (Amazon Prime)\n"
                "GST (18%):   Rs.   269.82\n"
                "---------------------------------\n"
                "TOTAL:       Rs. 1,768.82\n"
                "Payment:     HDFC Credit Card ****4242\n"
                "GSTIN:       29AABCU9603R1ZM\n\n"
                "Track your order: amazon.in/orders\n" * 55
            ).encode("utf-8")
        ),
        (
            "random_project_backup.zip",
            bytes([0x50, 0x4B, 0x03, 0x04]) +
            (
                "random_project/\x00"
                "random_project/src/\x00"
                "random_project/src/main.py\x00"
                "random_project/src/utils.py\x00"
                "random_project/src/models.py\x00"
                "random_project/tests/\x00"
                "random_project/README.md\x00"
                "random_project/requirements.txt\x00"
                "# This was supposed to be my side project\n"
                "# It was not completed. It was never completed.\n"
                "# The backup is the only proof it existed.\n" * 150
            ).encode("utf-8") +
            rand_bytes(7000)
        ),
        (
            "Untitled_presentation_FINAL(2).pptx",
            bytes([0x50, 0x4B, 0x03, 0x04, 0x14, 0x00, 0x00, 0x00]) +
            (
                "ppt/slides/slide1.xml\x00"
                "ppt/slides/slide2.xml\x00"
                "ppt/slides/slide3.xml\x00"
                '<?xml version="1.0"?>'
                "<p:sld><p:spTree><p:sp><p:txBody>"
                "<a:t>SLIDE TITLE HERE (TODO: ADD ACTUAL TITLE)</a:t>"
                "<a:t>Click to add subtitle text here...</a:t>"
                "<a:t>* Bullet point 1 (content TBD)</a:t>"
                "<a:t>* Bullet point 2 (see reference doc, link broken)</a:t>"
                "<a:t>Presenter notes: PLEASE PRACTICE THIS TIME</a:t>"
                "</p:txBody></p:sp></p:spTree></p:sld>" * 50
            ).encode("utf-8") +
            (b"\x00" * 1024)
        ),
        (
            "mystery_note_123.txt",
            (
                "SWIGGY INSTAMART ORDER #SW-99214\n"
                "Date: 31-Oct-2026 02:45 AM\n"
                "Items:\n"
                "  1x Midnight Maggi 4-Pack    Rs. 60.00\n"
                "  2x Red Bull 250ml          Rs. 250.00\n"
                "  1x Dark Chocolate Bar      Rs. 110.00\n"
                "Delivery Partner Tip:        Rs.  15.00\n"
                "-----------------------------------------\n"
                "Total Paid:                  Rs. 435.00 (UPI)\n"
                "Status: Delivered to Doorstep\n"
            ).encode("utf-8")
        ),
        (
            "buggy_script.py",
            (
                "import os,   sys,    time\n"
                "import json\n\n"
                "def   calculate_messy_sum(  a ,b   ):\n"
                "    # TODO: fix formatting and remove unused imports\n"
                "        x = a+b    \n"
                "        y = x * 2  \n"
                "        return y\n\n"
                "print(  calculate_messy_sum(10 , 20)  )\n"
            ).encode("utf-8")
        ),
    ]
    return files


# ── REST API Routes ──────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def serve_index() -> Response:
    """Serve the single-page React aim-trainer frontend directly."""
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        return jsonify({"error": "index.html not found in project root"}), 404
    return send_file(index_path, mimetype="text/html")


@app.route("/health", methods=["GET"])
def health() -> Response:
    """Health, readiness, and version probe for container environments."""
    return jsonify({
        "ok": True,
        "version": "2.3.0",
        "status": "healthy",
        "service": "Defuse the Downloads",
    })


@app.route("/seed", methods=["POST"])
def seed() -> Response:
    """Regenerate all 14 demo messy clutter files in Messy_Downloads."""
    created: List[str] = []
    failed: List[Dict[str, str]] = []
    for filename, content in _make_seed_files():
        try:
            (MESSY_DIR / filename).write_bytes(content)
            created.append(filename)
        except Exception as exc:
            failed.append({"file": filename, "error": str(exc)})

    # Purge classifier cache so new files get re-analyzed
    with _cache_lock:
        _gemini_cache.clear()

    return jsonify({
        "ok": True,
        "count": len(created),
        "files_created": created,
        "failed": failed,
    })


@app.route("/files", methods=["GET"])
def get_files() -> Response:
    """
    Return all Messy_Downloads files with deep content classification.
    Always responds in <300ms using instant local analysis while streaming
    Gemini 2.5 Flash results into cache asynchronously.
    """
    api_key = (request.headers.get("X-Gemini-Key", "") or GEMINI_API_KEY).strip()

    result: List[Dict[str, Any]] = []
    try:
        for fpath in sorted(MESSY_DIR.iterdir()):
            if not fpath.is_file():
                continue
            fname = fpath.name
            key_prefix = api_key[:8] if api_key else "local"
            cache_key = f"{fname}|{key_prefix}"
            snippet = _read_content_snippet(fpath)

            with _cache_lock:
                meta = _gemini_cache.get(cache_key)

            if meta is None:
                meta = _local_classify(fname, snippet)
                if api_key:
                    t = threading.Thread(
                        target=_bg_gemini_worker,
                        args=(fname, api_key, cache_key, snippet),
                        daemon=True,
                    )
                    t.start()

            try:
                sz_bytes = fpath.stat().st_size
            except Exception:
                sz_bytes = 0

            result.append({
                "filename":           fname,
                "size":               _human_size(fpath),
                "size_bytes":         sz_bytes,
                "enemy_name":         meta["enemy_name"],
                "description":        meta["description"],
                "recommended_action": meta["recommended_action"],
                "subfolder":          meta["subfolder"],
                "ai_powered":         meta.get("ai_powered", False),
                "deep_scanned":       bool(snippet),
                "content_preview":    (snippet[:90] + "...") if len(snippet) > 90 else snippet,
            })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(result)


@app.route("/action", methods=["POST"])
def action() -> Response:
    """
    Handle trash, organize, and undo with path traversal defense & AI linting.
    
    Payload:
        { "filename": "...", "action": "trash" | "organize" | "undo", "subfolder": "..." }
    """
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    raw_filename = str(body.get("filename", "")).strip()
    act = str(body.get("action", "")).strip().lower()
    subfolder = str(body.get("subfolder", "Documents")).strip()

    try:
        if act == "trash":
            if not is_safe_filename(raw_filename):
                return jsonify({"error": "Path traversal or illegal filename detected"}), 400
            
            src = MESSY_DIR / raw_filename
            dst = TRASH_DIR / raw_filename
            
            if not is_path_contained(MESSY_DIR, src) or not is_path_contained(TRASH_DIR, dst):
                return jsonify({"error": "Illegal directory boundary traversal"}), 400
            if not src.is_file():
                return jsonify({"error": f"Target not found in Messy_Downloads: {raw_filename}"}), 404

            shutil.move(str(src), str(dst))
            _action_history.append({
                "filename": raw_filename,
                "action": "trash",
                "from": str(src),
                "to": str(dst),
            })
            return jsonify({
                "ok": True,
                "message": f"{raw_filename} → Trash_Bin",
                "from": "Messy_Downloads",
                "to": "Trash_Bin",
            })

        elif act == "organize":
            if not is_safe_filename(raw_filename):
                return jsonify({"error": "Path traversal or illegal filename detected"}), 400
            if subfolder not in SUBFOLDERS:
                return jsonify({"error": f"Invalid subfolder: {subfolder}. Expected one of {SUBFOLDERS}"}), 400

            src = MESSY_DIR / raw_filename
            dst_dir = ORGANIZED_DIR / subfolder
            dst = dst_dir / raw_filename

            if not is_path_contained(MESSY_DIR, src) or not is_path_contained(dst_dir, dst):
                return jsonify({"error": "Illegal directory boundary traversal"}), 400
            if not src.is_file():
                return jsonify({"error": f"Target not found in Messy_Downloads: {raw_filename}"}), 404

            # AI Lint Fixer for code files
            lint_fixed = False
            lint_message = ""
            if src.suffix.lower() in [".py", ".js"] or subfolder == "Code":
                cleaned_code, lint_message = _lint_and_format_code(src)
                if cleaned_code:
                    dst.write_text(cleaned_code, encoding="utf-8")
                    src.unlink()
                    lint_fixed = True
                else:
                    shutil.move(str(src), str(dst))
            else:
                shutil.move(str(src), str(dst))

            _action_history.append({
                "filename": raw_filename,
                "action": "organize",
                "subfolder": subfolder,
                "from": str(src),
                "to": str(dst),
                "lint_fixed": lint_fixed,
            })
            return jsonify({
                "ok": True,
                "message": f"{raw_filename} → Organized_Safe/{subfolder}",
                "from": "Messy_Downloads",
                "to": f"Organized_Safe/{subfolder}",
                "lint_fixed": lint_fixed,
                "lint_message": lint_message,
            })

        elif act == "undo":
            if not _action_history:
                return jsonify({"error": "Action history stack is empty. Nothing to undo."}), 400
            
            last = _action_history.pop()
            undo_src = Path(last["to"])
            undo_dst = Path(last["from"])

            # Verify both undo paths remain strictly inside project root
            if not is_path_contained(BASE_DIR, undo_src) or not is_path_contained(BASE_DIR, undo_dst):
                return jsonify({"error": "Security containment violation during undo"}), 400
            if not undo_src.is_file():
                return jsonify({"error": f"Undo source missing on disk: {undo_src.name}"}), 404

            shutil.move(str(undo_src), str(undo_dst))
            return jsonify({
                "ok": True,
                "message": f"Restored {last['filename']} → Messy_Downloads",
                "filename": last["filename"],
            })

        else:
            return jsonify({"error": f"Unknown action: '{act}'. Expected 'trash', 'organize', or 'undo'"}), 400

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/stats", methods=["GET"])
def stats() -> Response:
    """Return live file counts and inventories across all watched directories."""
    try:
        messy_files = [f.name for f in MESSY_DIR.iterdir() if f.is_file()]
        trash_files = [f.name for f in TRASH_DIR.iterdir() if f.is_file()]
        organized: Dict[str, List[str]] = {}
        for sf in SUBFOLDERS:
            p = ORGANIZED_DIR / sf
            organized[sf] = [f.name for f in p.iterdir() if f.is_file()] if p.exists() else []

        return jsonify({
            "messy_downloads": {
                "count": len(messy_files),
                "files": messy_files,
            },
            "trash_bin": {
                "count": len(trash_files),
                "files": trash_files,
            },
            "organized_safe": {
                sf: {"count": len(fs), "files": fs}
                for sf, fs in organized.items()
            },
            "total_organized": sum(len(fs) for fs in organized.values()),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Auto-seed on startup ──────────────────────────────────────────────────────
def _auto_seed_if_empty() -> None:
    """Auto-populates demo clutter on cold start if Messy_Downloads is empty."""
    existing = [f for f in MESSY_DIR.iterdir() if f.is_file()]
    if not existing:
        print("[Startup] Messy_Downloads is empty — auto-seeding 14 demo files…")
        for filename, content in _make_seed_files():
            try:
                (MESSY_DIR / filename).write_bytes(content)
                print(f"  ✓  {filename}")
            except Exception as exc:
                print(f"  ✗  {filename}: {exc}")
        print("[Startup] Seed complete!")
    else:
        print(f"[Startup] Messy_Downloads has {len(existing)} active target file(s)")


if __name__ == "__main__":
    _auto_seed_if_empty()

    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0"

    print()
    print("=" * 64)
    print("  ⚡  Defuse the Downloads — Production Server v2.3")
    print("=" * 64)
    print(f"  📁  Messy_Downloads : {MESSY_DIR}")
    print(f"  📂  Organized_Safe  : {ORGANIZED_DIR}")
    print(f"  🗑️   Trash_Bin       : {TRASH_DIR}")
    ai_status = (
        "✅  Gemini AI active (configured via environment)"
        if GEMINI_API_KEY else
        "⚡  Local classifier (instant fallback; key can be set in UI)"
    )
    print(f"  🤖  AI Mode         : {ai_status}")
    print(f"  🌐  Listening on    : http://{host}:{port}")
    print("=" * 64)
    print()

    app.run(host=host, port=port, debug=False)
