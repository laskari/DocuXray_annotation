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

from config import ANNOTATIONS_DIR, IMAGES_DIR, MODEL_SOURCES, ALLOWED_DOCS_JSON

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
      2. Contain 1_extraction.json in at least one model source, OR be a direct .json file.
    """
    ids: set[str] = set()
    for root in MODEL_SOURCES.values():
        if not root.exists():
            continue
        for p in root.iterdir():
            if p.is_dir() and (p / "1_extraction.json").exists():
                ids.add(p.name)
            elif p.is_file() and p.suffix == ".json" and p.name != "postprocessing.json":
                ids.add(p.stem)

    if ALLOWED_DOCS_JSON and ALLOWED_DOCS_JSON.exists():
        try:
            with open(ALLOWED_DOCS_JSON, encoding="utf-8") as f:
                allowed_names = json.load(f)
            allowed_stems = {Path(name).stem for name in allowed_names}
            ids = ids.intersection(allowed_stems)
        except Exception as e:
            print(f"Error filtering document IDs: {e}")

    return sorted(ids)


def load_refinement(label: str, doc_id: str) -> dict | None:
    path = MODEL_SOURCES[label] / doc_id / "1_extraction.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Parse error {path}: {e}")
            
    path_direct = MODEL_SOURCES[label] / f"{doc_id}.json"
    if path_direct.exists():
        try:
            with open(path_direct, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Parse error {path_direct}: {e}")
            
    return None


def get_refined_data(ref_json: dict) -> dict:
    if "data" in ref_json:
        return ref_json["data"]
    if "extracted_data" in ref_json:
        return ref_json["extracted_data"]
    if "postprocessed" in ref_json:
        return ref_json["postprocessed"]
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


def save_annotation(doc_id: str, flat_edits: dict[str, str], timestamps: dict[str, str] | None = None, confusing_image: bool = False) -> str:
    """
    Reconstruct original schema from base model, apply edits, save.
    Output is identical in structure to 1_extraction.json input.
    """
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    base_raw = None
    for label in MODEL_SOURCES:
        base_raw = load_refinement(label, doc_id)
        if base_raw is not None:
            break
    if base_raw is None:
        raise ValueError(f"No 1_extraction.json for {doc_id}")

    original_flat = flatten(get_refined_data(base_raw))

    typed_edits = {
        path: coerce_value(val_str, original_flat.get(path))
        for path, val_str in flat_edits.items()
    }

    if timestamps is None:
        timestamps = {}

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
            "selected_from": selected_from,
            "last_updated": timestamps.get(path)
        })

    out = copy.deepcopy(base_raw)
    reconstructed = reconstruct(get_refined_data(base_raw), typed_edits)
    if "postprocessed" in out:
        out["postprocessed"] = reconstructed
    elif "extracted_data" in out:
        out["extracted_data"] = reconstructed
    elif "data" in out:
        out["data"] = reconstructed
    else:
        if "refinement" not in out:
            out["refinement"] = {}
        out["refinement"]["refined_data"] = reconstructed
    out["annotation_meta"] = {
        "annotated": True,
        "confusing_image": confusing_image,
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
        raise ValueError(f"No 1_extraction.json for {doc_id}")

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
        reconstructed = reconstruct(get_refined_data(base_raw), typed_edits)
        if "postprocessed" in out:
            out["postprocessed"] = reconstructed
        elif "extracted_data" in out:
            out["extracted_data"] = reconstructed
        elif "data" in out:
            out["data"] = reconstructed
        else:
            if "refinement" not in out:
                out["refinement"] = {}
            out["refinement"]["refined_data"] = reconstructed
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

    from config import PROJECT_ROOT
    import re
    
    paths_file = None
    try:
        from config import SCHEMA_DIR
        if (SCHEMA_DIR / "full_paths_to_consider.json").exists():
            paths_file = SCHEMA_DIR / "full_paths_to_consider.json"
    except Exception:
        pass
    if paths_file is None:
        paths_file = PROJECT_ROOT / "full_paths_to_consider.json"

    if paths_file.exists():
        try:
            with open(paths_file, "r", encoding="utf-8") as f:
                full_paths = json.load(f)
                
            for p in full_paths:
                if "[*]" in p:
                    # Check if any existing path matches this array pattern
                    pattern_str = "^" + re.escape(p).replace(r"\[\*\]", r"\.\d+") + "$"
                    pattern = re.compile(pattern_str)
                    if not any(pattern.match(ep) for ep in all_paths):
                        all_paths.add(p.replace("[*]", ".0"))
                else:
                    if p not in all_paths:
                        all_paths.add(p)
        except Exception as e:
            print(f"Error loading full_paths_to_consider.json: {e}")

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

def ensure_schema_and_descriptions_generated(doc_id: str | None = None) -> None:
    """
    Automatically creates/updates the flattened JSON (`full_paths_to_consider.json`)
    and description JSON (`paths_with_descriptions.json`) inside the designated SCHEMA_DIR
    using the first available extraction JSON and the schema class in SCHEMA_DIR.
    """
    import re
    import importlib.util
    import sys
    from config import PROJECT_ROOT, MODEL_SOURCES
    try:
        from config import SCHEMA_DIR
    except ImportError:
        SCHEMA_DIR = PROJECT_ROOT / "bank_statement_schema"

    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Get reference extraction data (using doc_id or first available doc_id)
    if doc_id is None:
        doc_ids = get_document_ids()
        if not doc_ids:
            return
        doc_id = doc_ids[0]

    first_extraction_data = None
    for label in MODEL_SOURCES:
        raw = load_refinement(label, doc_id)
        if raw is not None:
            first_extraction_data = get_refined_data(raw)
            break

    if first_extraction_data is None:
        return

    # 2. Flatten and normalize list indices to [*]
    flat_data = flatten(first_extraction_data)
    normalized_paths = set()
    for path in flat_data.keys():
        norm_p = re.sub(r'\.\d+(?=\.|$)', '[*]', path)
        normalized_paths.add(norm_p)

    sorted_paths = [
        p for p in sorted(list(normalized_paths))
        if not any(k in p.lower() for k in ("reason", "anlysis", "analysis", "analytics"))
    ]
    flattened_json_path = SCHEMA_DIR / "full_paths_to_consider.json"
    try:
        with open(flattened_json_path, "w", encoding="utf-8") as f:
            json.dump(sorted_paths, f, indent=4)
        print(f"[Schema Gen] Saved {len(sorted_paths)} flattened paths to {flattened_json_path}")
    except Exception as e:
        print(f"[Schema Gen] Error saving {flattened_json_path}: {e}")

    # 3. Locate schema file in SCHEMA_DIR and extract descriptions
    schema_files = list(SCHEMA_DIR.glob("schema*.py"))
    if not schema_files:
        return
    schema_path = schema_files[0]

    module_name = schema_path.stem
    try:
        if module_name in sys.modules:
            module = sys.modules[module_name]
        else:
            spec = importlib.util.spec_from_file_location(module_name, str(schema_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            else:
                return
    except Exception as e:
        print(f"[Schema Gen] Error importing schema from {schema_path}: {e}")
        return

    root_model = None
    for attr in ["BankStatementData", "ReceiptData", "InvoiceData", "DocumentExtractionResult"]:
        if hasattr(module, attr):
            root_model = getattr(module, attr)
            break
    if root_model is None:
        for map_attr in ["BANK_STATEMENT_SCHEMA_MAP", "RECEIPT_SCHEMA_MAP", "SCHEMA_MAP"]:
            if hasattr(module, map_attr):
                m_map = getattr(module, map_attr)
                if isinstance(m_map, dict) and m_map.get("full"):
                    root_model = m_map.get("full")
                    break

    if root_model is None:
        return

    def get_desc(model_cls, path_parts) -> list[str]:
        from typing import get_args, get_origin, Union
        if not path_parts or model_cls is None or model_cls is Any:
            return []
        part = path_parts[0]
        if part.endswith('[*]'):
            part = part[:-3]

        if not hasattr(model_cls, 'model_fields') or part not in model_cls.model_fields:
            return [f"FIELD_NOT_FOUND:{part}"]

        field_info = model_cls.model_fields[part]
        desc = field_info.description

        descs = []
        if desc:
            if getattr(model_cls, '__name__', '') in ('BankStatementData', 'InvoiceData', 'ReceiptData', 'DocumentExtractionResult') and len(path_parts) > 1:
                pass
            else:
                descs.append(desc.strip())

        if len(path_parts) == 1:
            return descs

        ann = field_info.annotation
        origin = get_origin(ann)
        nxt = ann
        if origin is Union:
            args = [a for a in get_args(ann) if a is not type(None)]
            if args:
                nxt = args[0]

        origin2 = get_origin(nxt)
        if origin2 in (list, list) or nxt is list:
            args = get_args(nxt)
            if args:
                nxt = args[0]
        elif origin2 in (dict, dict) or nxt is dict:
            args = get_args(nxt)
            if len(args) > 1:
                nxt = args[1]

        origin3 = get_origin(nxt)
        if origin3 is Union:
            args = [a for a in get_args(nxt) if a is not type(None)]
            if args:
                nxt = args[0]

        child_descs = get_desc(nxt, path_parts[1:])
        descs.extend(child_descs)
        return descs

    result_map = {}
    for path in sorted_paths:
        if "addressStructured" in path:
            part = path.split(".")[-1]
            if hasattr(module, "AddressStructured") and hasattr(module.AddressStructured, "model_fields"):
                if part in module.AddressStructured.model_fields:
                    field_desc = (module.AddressStructured.model_fields[part].description or "").strip()
                    doc = (module.AddressStructured.__doc__ or "").strip()
                    result_map[path] = f"{doc} {field_desc}".strip()
                    continue

        descs = get_desc(root_model, path.split("."))
        descs = [d for d in descs if not d.startswith("FIELD_NOT_FOUND")]
        if descs:
            result_map[path] = " ".join(descs)
        else:
            result_map[path] = "DESCRIPTION_MISSING"

    desc_path = SCHEMA_DIR / "paths_with_descriptions.json"
    try:
        with open(desc_path, "w", encoding="utf-8") as f:
            json.dump(result_map, f, indent=4)
        print(f"[Schema Gen] Updated {len(result_map)} descriptions in {desc_path}")
    except Exception as e:
        print(f"[Schema Gen] Error saving {desc_path}: {e}")


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