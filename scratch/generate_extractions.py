import json
import shutil
from pathlib import Path

def main():
    project_root = Path(__file__).resolve().parent.parent
    ann_dir = project_root / "annotations"
    ext_dir = project_root / "extraction"
    src_dir = project_root.parent / "one_model_receipt" / "extraction"

    ext_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    generated_count = 0
    skipped_count = 0

    for ann_file in sorted(ann_dir.glob("*.json")):
        if ann_file.name == "export_all.jsonl":
            continue
        
        doc_id = ann_file.stem
        target_dir = ext_dir / doc_id
        target_file = target_dir / "1_extraction.json"

        if target_file.exists():
            skipped_count += 1
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        src_file = src_dir / doc_id / "1_extraction.json"

        if src_file.exists():
            shutil.copy2(src_file, target_file)
            copied_count += 1
        else:
            try:
                with open(ann_file, "r", encoding="utf-8") as f:
                    ann_data = json.load(f)
                
                ext_data = {
                    "document_id": ann_data.get("document_id", doc_id),
                    "file": ann_data.get("file", f"{doc_id}.JPG"),
                    "data": ann_data.get("data", {}),
                    "metadata": ann_data.get("metadata", {
                        "model": "gemini-3-flash-preview",
                        "parts_run": ["all"],
                        "token_usage": {"input": 0, "output": 0, "thinking": 0, "total": 0},
                        "errors": []
                    })
                }

                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(ext_data, f, indent=2, ensure_ascii=False)
                generated_count += 1
            except Exception as e:
                print(f"Error processing {doc_id}: {e}")

    print(f"Extraction generation complete:")
    print(f"  Existing skipped: {skipped_count}")
    print(f"  Copied from one_model_receipt: {copied_count}")
    print(f"  Generated from annotations: {generated_count}")
    print(f"Total extractions now available: {len([d for d in ext_dir.iterdir() if d.is_dir() and (d / '1_extraction.json').exists()])}")

if __name__ == "__main__":
    main()
