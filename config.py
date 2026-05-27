"""
config.py  –  Edit your paths and model sources here.
Replaces "Cell 3" from the original Colab notebook.
"""
from pathlib import Path

# ── Project root ────────────────────────────────────────────────────────────
# Change this to wherever your annotation project lives on your machine.
# PROJECT_ROOT = Path(__file__).resolve().parent / "DocuXray_annotation"
# On Mac/Linux use a plain forward-slash path, e.g.:        
PROJECT_ROOT = Path(__file__).resolve().parent

# ── One entry per model ─────────────────────────────────────────────────────
# Key   = display name shown in the UI
# Value = folder that contains <doc_id>/ sub-folders with postprocessing.json
MODEL_SOURCES: dict[str, Path] = {}
_model_outputs_dir = PROJECT_ROOT / "model_outputs"
if _model_outputs_dir.exists():
    for _p in sorted(_model_outputs_dir.iterdir()):
        if _p.is_dir() and not _p.name.startswith('.'):
            _name_map = {
                "claude_opus_4_7_batch": "Claude",
                "gemini_pro_3_1": "Gemini",
                "openai_gpt_5_4_batch": "GPT"
            }
            _display_name = _name_map.get(_p.name, _p.name.replace("_", " ").title())
            MODEL_SOURCES[_display_name] = _p

# ── Images directory ────────────────────────────────────────────────────────
# Set to None if you have no invoice images.
IMAGES_DIR: Path | None = PROJECT_ROOT / "sks_50"

# ── Allowed Documents JSON ──────────────────────────────────────────────────
# Filter list of images/documents to consider (only those listed in this JSON)
ALLOWED_DOCS_JSON: Path | None = Path(__file__).resolve().parent / "data3.json"

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