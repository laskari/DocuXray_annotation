"""
core.py  –  Data helpers: flatten/reconstruct, model I/O, annotation persistence,
            consensus engine, and HTML/status utilities.
Replaces "Cell 4" from the original Colab notebook.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from config import ANNOTATIONS_DIR, IMAGES_DIR, MODEL_SOURCES

IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".webp", ".tiff"]


# ── Flatten / reconstruct ────────────────────────────────────────────────────

def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """
    Recursively flatten nested dict/list to dot-path leaf keys.
      {"a": {"b": 1}}     → {"a.b": 1}
      {"x": [{"y": 2}]}   → {"x.0.y": 2}
    """
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{prefix}.{k}" if prefix else k
            out.update(flatten(v, full))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            full = f"{prefix}.{i}" if prefix else str(i)
            out.update(flatten(v, full))
    else:
        out[prefix] = obj
    return out


def set_by_path(obj: Any, path: str, value: Any) -> None:
    """Write value into obj at dot-path in-place, creating intermediaries."""
    parts = path.split(".")
    cur = obj
    for i, part in enumerate(parts[:-1]):
        nxt_key = parts[i + 1]
        nxt_is_idx = nxt_key.isdigit()
        if isinstance(cur, list):
            idx = int(part)
            while len(cur) <= idx:
                cur.append(None)
            if cur[idx] is None:
                cur[idx] = [] if nxt_is_idx else {}
            cur = cur[idx]
        else:
            if part not in cur or cur[part] is None:
                cur[part] = [] if nxt_is_idx else {}
            cur = cur[part]
    last = parts[-1]
    if isinstance(cur, list):
        idx = int(last)
        while len(cur) <= idx:
            cur.append(None)
        cur[idx] = value
    else:
        cur[last] = value


def reconstruct(base: Any, flat_edits: dict[str, Any]) -> Any:
    """Deep-copy base structure and overlay flat_edits (dot-path → value)."""
    result = copy.deepcopy(base)
    for path, value in flat_edits.items():
        set_by_path(result, path, value)
    return result


def coerce_value(raw_str: str, original_val: Any) -> Any:
    """Cast annotator text back to the original Python type."""
    s = raw_str.strip()
    if s.lower() in ("null", "none", ""):
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if isinstance(original_val, bool):
        return s.lower() == "true"
    if isinstance(original_val, int):
        try:
            return int(s)
        except ValueError:
            pass
    if isinstance(original_val, float):
        try:
            return float(s)
        except ValueError:
            pass
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass
    return s


# ── Document / model I/O ─────────────────────────────────────────────────────

def get_document_ids() -> list[str]:
    """
    A valid document folder must:
      1. Be a directory inside a model root.
      2. Contain refinement.json in at least one model source.
    """
    ids: set[str] = set()
    for root in MODEL_SOURCES.values():
        if not root.exists():
            continue
        for p in root.iterdir():
            if p.is_dir() and (p / "refinement.json").exists():
                ids.add(p.name)
    return sorted(ids)


def load_refinement(label: str, doc_id: str) -> dict | None:
    path = MODEL_SOURCES[label] / doc_id / "refinement.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Parse error {path}: {e}")
    return None


def get_refined_data(ref_json: dict) -> dict:
    return ref_json.get("refinement", {}).get("refined_data", {})


def load_all_model_flat(doc_id: str) -> dict[str, dict[str, Any]]:
    """Return {model_label: {dot_path: leaf_value}} for every model with data."""
    return {
        label: flatten(get_refined_data(raw))
        for label in MODEL_SOURCES
        if (raw := load_refinement(label, doc_id)) is not None
    }


def find_image(doc_id: str) -> Path | None:
    if not IMAGES_DIR or not IMAGES_DIR.exists():
        return None
    for ext in IMAGE_EXTS:
        p = IMAGES_DIR / f"{doc_id}{ext}"
        if p.exists():
            return p
    return None


# ── Annotation persistence ───────────────────────────────────────────────────

def load_existing_annotation(doc_id: str) -> dict | None:
    path = ANNOTATIONS_DIR / f"{doc_id}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_annotation(doc_id: str, flat_edits: dict[str, str]) -> str:
    """
    Reconstruct original schema from base model, apply edits, save.
    Output is identical in structure to refinement.json input.
    """
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    base_raw = None
    for label in MODEL_SOURCES:
        base_raw = load_refinement(label, doc_id)
        if base_raw is not None:
            break
    if base_raw is None:
        raise ValueError(f"No refinement.json for {doc_id}")

    original_flat = flatten(get_refined_data(base_raw))

    typed_edits = {
        path: coerce_value(val_str, original_flat.get(path))
        for path, val_str in flat_edits.items()
    }

    field_metadata = []
    model_flat = load_all_model_flat(doc_id)
    for path, val_str in typed_edits.items():
        matching_models = []
        for model_name in MODEL_SOURCES:
            m_val = _disp(model_flat.get(model_name, {}).get(path))
            if m_val == _disp(val_str):
                matching_models.append(model_name)
        
        if matching_models:
            selected_from = matching_models[-1]
        else:
            selected_from = "manual_entry"
            
        field_metadata.append({
            "key": path,
            "final_value": val_str,
            "selected_from": selected_from
        })

    out = copy.deepcopy(base_raw)
    out["refinement"]["refined_data"] = reconstruct(
        get_refined_data(base_raw), typed_edits
    )
    out["annotation_meta"] = {
        "annotated": True,
        "source_models": list(MODEL_SOURCES.keys()),
        "manually_edited_keys": [
            p for p, v in typed_edits.items() if v != original_flat.get(p)
        ],
        "field_metadata": field_metadata
    }

    dest = ANNOTATIONS_DIR / f"{doc_id}.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return str(dest)


def save_custom_combinations(doc_id: str, options: list[str]) -> list[str]:
    """
    Save combinations of model outputs based on selected options.
    Output goes to distinct directories like annotation_Only_GPT or annotation_All_models_matching.
    """
    from config import MODEL_SOURCES as _MS

    model_flat = load_all_model_flat(doc_id)
    if not model_flat:
        raise ValueError(f"No refinement.json for {doc_id}")

    base_raw = None
    for label in _MS:
        base_raw = load_refinement(label, doc_id)
        if base_raw is not None:
            break
    if base_raw is None:
        raise ValueError(f"No valid base refinement found for {doc_id}")

    all_paths: set[str] = set()
    for flat in model_flat.values():
        all_paths.update(flat.keys())

    saved_paths = []

    for opt in options:
        opt_dir_name = opt.replace(" ", "_")
        target_dir = ANNOTATIONS_DIR.parent / f"annotation_{opt_dir_name}"
        target_dir.mkdir(parents=True, exist_ok=True)

        edits = {}
        if opt.startswith("Only "):
            model_name = opt.replace("Only ", "")
            for path in all_paths:
                val = model_flat.get(model_name, {}).get(path)
                disp_val = _disp(val)
                if disp_val:
                    edits[path] = disp_val
        elif opt == "All models matching":
            for path in all_paths:
                status, pairs, best = compute_consensus(path, model_flat)
                all_null = all(v == "" for _, v in pairs)
                if status == "agree" and not all_null and len(pairs) == len(_MS):
                    edits[path] = best
        elif opt == "At least two models matching":
            for path in all_paths:
                status, pairs, best = compute_consensus(path, model_flat)
                all_null = all(v == "" for _, v in pairs)
                if status in ("agree", "partial") and not all_null:
                    non_empty = [v for _, v in pairs if v]
                    counts = {v: non_empty.count(v) for v in set(non_empty)}
                    if any(c >= 2 for c in counts.values()):
                        edits[path] = max(counts, key=counts.get)
        elif " and " in opt and opt.endswith(" matching"):
            parts = opt.replace(" matching", "").split(" and ")
            if len(parts) == 2:
                m1, m2 = parts
                for path in all_paths:
                    v1 = _disp(model_flat.get(m1, {}).get(path))
                    v2 = _disp(model_flat.get(m2, {}).get(path))
                    if v1 and v2 and v1 == v2:
                        edits[path] = v1

        if not edits:
            continue

        original_flat = flatten(get_refined_data(base_raw))
        typed_edits = {
            path: coerce_value(val_str, original_flat.get(path))
            for path, val_str in edits.items()
        }

        field_metadata = []
        for path, val_str in typed_edits.items():
            matching_models = []
            for model_name in _MS:
                m_val = _disp(model_flat.get(model_name, {}).get(path))
                if m_val == _disp(val_str):
                    matching_models.append(model_name)
            
            if matching_models:
                selected_from = matching_models[-1]
            else:
                selected_from = "manual_entry"
                
            field_metadata.append({
                "key": path,
                "final_value": val_str,
                "selected_from": selected_from
            })

        out = copy.deepcopy(base_raw)
        out["refinement"]["refined_data"] = reconstruct(
            get_refined_data(base_raw), typed_edits
        )
        out["annotation_meta"] = {
            "annotated": True,
            "match_only": "matching" in opt,
            "source_models": list(_MS.keys()),
            "matched_keys_count": len(edits),
            "matched_keys": list(edits.keys()),
            "combination_type": opt,
            "field_metadata": field_metadata
        }

        dest = target_dir / f"{doc_id}.json"
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        saved_paths.append(str(dest))

    return saved_paths


def export_all_annotations() -> str:
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ANNOTATIONS_DIR / "export_all.jsonl"
    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for p in sorted(ANNOTATIONS_DIR.glob("*.json")):
            if p.name == "export_all.jsonl":
                continue
            f.write(p.read_text(encoding="utf-8").replace("\n", " ") + "\n")
            count += 1
    return f"{out_path}  ({count} documents)"


# ── Consensus engine ─────────────────────────────────────────────────────────

def _disp(val: Any) -> str:
    if val is None:
        return ""
    if val is True:
        return "true"
    if val is False:
        return "false"
    return str(val)


def compute_consensus(
    path: str,
    model_flat: dict[str, dict[str, Any]],
) -> tuple[str, list[tuple[str, str]], str]:
    """
    Returns (status, [(model_label, display_str)...], best_guess_str)
    status: 'agree' | 'partial' | 'conflict' | 'missing'
    """
    labels = list(model_flat.keys())
    raw = {lbl: _disp(model_flat[lbl].get(path)) for lbl in labels}
    pairs = [(lbl, raw[lbl]) for lbl in labels]
    
    non_empty = [v for v in raw.values() if v]
    counts = {v: non_empty.count(v) for v in set(non_empty)}
    has_missing = len(non_empty) < len(labels)
    
    if not non_empty:
        status = "missing"
        best = ""
    else:
        top_val = max(counts, key=counts.get)
        top_cnt = counts[top_val]
        
        if top_cnt == len(labels):
            status = "agree"
            best = top_val
        elif top_cnt >= 2:
            status = "partial"
            best = top_val
        elif len(set(raw.values())) == len(labels):
            status = "conflict"
            best = ""
        elif has_missing:
            status = "missing"
            if len(non_empty) == 1:
                best = top_val
            else:
                best = ""
        else:
            status = "conflict"
            best = ""

    return status, pairs, best


def build_field_table(
    model_flat: dict[str, dict[str, Any]],
    existing_flat_str: dict[str, str] | None,
) -> list[dict]:
    """
    One dict per unique dot-path key, sorted: conflicts first.
    Each dict: {path, status, pairs, final, all_null}
    """
    all_paths: set[str] = set()
    for flat in model_flat.values():
        all_paths.update(flat.keys())

    rows = []
    for path in sorted(all_paths):
        status, pairs, best = compute_consensus(path, model_flat)
        all_null = all(v == "" for _, v in pairs)
        final = (existing_flat_str or {}).get(path, best)
        rows.append(
            {"path": path, "status": status, "pairs": pairs,
             "final": final, "all_null": all_null}
        )

    order = {"conflict": 0, "partial": 1, "agree": 2, "missing": 3}
    rows.sort(
        key=lambda r: (r["all_null"], order.get(r["status"], 9), r["path"])
    )
    return rows


# ── UI helpers ───────────────────────────────────────────────────────────────

STATUS_STYLE = {
    "agree":   ("OK", "#3B6D11", "#EAF3DE", "#C0DD97"),
    "partial": ("~",  "#854F0B", "#FAEEDA", "#FAC775"),
    "conflict":("!!", "#A32D2D", "#FCEBEB", "#F7C1C1"),
    "missing": ("--", "#666",    "#F1EFE8", "#D3D1C7"),
}


def summary_html(rows: list[dict], show_nulls: bool) -> str:
    c = {"conflict": 0, "partial": 0, "agree": 0, "missing": 0}
    shown = 0
    for r in rows:
        if show_nulls or not r["all_null"]:
            c[r["status"]] = c.get(r["status"], 0) + 1
            shown += 1
    total = len(rows)
    return (
        f'<div style="font-size:0.88em;color:#444;padding:3px 0">'
        f"<b>{shown}</b>/{total} keys shown &nbsp;&nbsp;"
        f'<span style="color:#A32D2D">!! {c["conflict"]} conflict</span> &nbsp;'
        f'<span style="color:#854F0B">~ {c["partial"]} partial</span> &nbsp;'
        f'<span style="color:#3B6D11">OK {c["agree"]} agreed</span> &nbsp;'
        f'<span style="color:#666">-- {c["missing"]} missing</span>'
        f"</div>"
    )