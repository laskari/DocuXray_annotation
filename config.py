"""
config.py  –  Edit your paths and model sources here.
Replaces "Cell 3" from the original Colab notebook.
"""
from pathlib import Path
import os
import json
# ── Project root ────────────────────────────────────────────────────────────
# Change this to wherever your annotation project lives on your machine.
# PROJECT_ROOT = Path(__file__).resolve().parent / "DocuXray_annotation"
# On Mac/Linux use a plain forward-slash path, e.g.:        
PROJECT_ROOT = Path(__file__).resolve().parent

# ── One entry per model ─────────────────────────────────────────────────────
# Key   = display name shown in the UI
# Value = folder that contains <doc_id>/ sub-folders with 1_extraction.json
MODEL_SOURCES: dict[str, Path] = {
    "Gemini": PROJECT_ROOT / "extraction_img_2"
}

# ── Images directory ────────────────────────────────────────────────────────
# Set to None if you have no invoice images.
IMAGES_DIR: Path | None = PROJECT_ROOT / "invoices_img_2"

IMAGES_DIR = PROJECT_ROOT / "invoices_img_2"

# Read all filenames
images = sorted(os.listdir(IMAGES_DIR))

# Write as JSON list
with open("data.json", "w") as f:
    json.dump(images, f, indent=4)

print(f"Saved {len(images)} filenames to data.json")
# ── Allowed Documents JSON ──────────────────────────────────────────────────
# Filter list of images/documents to consider (only those listed in this JSON)
ALLOWED_DOCS_JSON: Path | None = Path(__file__).resolve().parent / "data.json"

# ALLOWED_DOCS_JSON: Path | None = Path(__file__).resolve().parent / "data4.json"

# ── Where annotations are written ──────────────────────────────────────────
ANNOTATIONS_DIR: Path = PROJECT_ROOT / "annotations"

# ── UI default ─────────────────────────────────────────────────────────────
# Show keys where every model returned null?
SHOW_ALL_NULL_KEYS: bool = False


# ── Validation (printed on import) ─────────────────────────────────────────
def _validate():
    print(f"Project root : {PROJECT_ROOT}  (exists={PROJECT_ROOT.exists()})")
    for label, p in MODEL_SOURCES.items():
        n = len([x for x in p.iterdir() if x.is_dir()]) if p.exists() else 0
        print(f"  {'OK     ' if p.exists() else 'MISSING'} {label}: {p}  ({n} docs)")
    if IMAGES_DIR:
        n = len(list(IMAGES_DIR.iterdir())) if IMAGES_DIR.exists() else 0
        print(f"  Images : {IMAGES_DIR}  ({n} files)")
    else:
        print("  Images : (disabled)")


if __name__ == "__main__":
    _validate()