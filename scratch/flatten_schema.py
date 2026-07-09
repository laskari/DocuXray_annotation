import os
import sys
import json
import argparse
import importlib.util
from typing import get_origin, get_args, Union, Any, List, Dict
from pydantic import BaseModel


def unwrap_type(t):
    """Unwrap Optional and Union types to get the underlying type."""
    origin = get_origin(t)
    if origin is Union:
        args = [arg for arg in get_args(t) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
        # Prefer a BaseModel subclass if multiple options exist in Union
        for arg in args:
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                return arg
        return args[0] if args else t
    return t


def get_leaf_paths(model_cls, prefix="") -> list:
    """Recursively traverse Pydantic model fields and return flattened dot-separated paths."""
    paths = []
    
    # Attempt rebuild to resolve string annotations / forward references
    if hasattr(model_cls, "model_rebuild"):
        try:
            model_cls.model_rebuild()
        except Exception:
            pass

    if not hasattr(model_cls, "model_fields"):
        return paths

    for field_name, field_info in model_cls.model_fields.items():
        ann = unwrap_type(field_info.annotation)
        origin = get_origin(ann)

        if origin in (list, List, set, tuple) or ann is list:
            args = get_args(ann)
            item_type = unwrap_type(args[0]) if args else Any
            curr_prefix = f"{prefix}.{field_name}[*]" if prefix else f"{field_name}[*]"
            if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                paths.extend(get_leaf_paths(item_type, curr_prefix))
            else:
                paths.append(curr_prefix)
        elif origin in (dict, Dict) or ann is dict:
            args = get_args(ann)
            val_type = unwrap_type(args[1]) if len(args) > 1 else Any
            curr_prefix = f"{prefix}.{field_name}[*]" if prefix else f"{field_name}[*]"
            if isinstance(val_type, type) and issubclass(val_type, BaseModel):
                paths.extend(get_leaf_paths(val_type, curr_prefix))
            else:
                paths.append(curr_prefix)
        elif isinstance(ann, type) and issubclass(ann, BaseModel):
            curr_prefix = f"{prefix}.{field_name}" if prefix else field_name
            paths.extend(get_leaf_paths(ann, curr_prefix))
        else:
            curr_prefix = f"{prefix}.{field_name}" if prefix else field_name
            paths.append(curr_prefix)

    return paths


def load_schema_module(file_path):
    """Dynamically import a Python module from an arbitrary file path."""
    from importlib.machinery import SourceFileLoader
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Schema file not found: {file_path}")

    module_dir = os.path.dirname(file_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    module_name = os.path.splitext(os.path.basename(file_path))[0]
    loader = SourceFileLoader(module_name, file_path)
    spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def get_root_model(module, schema_path, model_name=None):
    """Determine the root Pydantic schema model to flatten."""
    if model_name:
        if hasattr(module, model_name):
            return getattr(module, model_name)
        raise AttributeError(f"Model class '{model_name}' not found in module.")

    filename_lower = os.path.basename(schema_path).lower()
    if "receipt" in filename_lower and hasattr(module, "RECEIPT_SCHEMA_MAP"):
        if module.RECEIPT_SCHEMA_MAP.get("full") is not None:
            return module.RECEIPT_SCHEMA_MAP.get("full")
    if hasattr(module, "SCHEMA_MAP"):
        if module.SCHEMA_MAP.get("full") is not None:
            return module.SCHEMA_MAP.get("full")
    if hasattr(module, "RECEIPT_SCHEMA_MAP"):
        if module.RECEIPT_SCHEMA_MAP.get("full") is not None:
            return module.RECEIPT_SCHEMA_MAP.get("full")

    for candidate in ["ReceiptData", "InvoiceData", "DocumentExtractionResult"]:
        if hasattr(module, candidate):
            return getattr(module, candidate)

    raise ValueError("Could not automatically determine root schema class. Please specify using --model.")


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_schema = os.path.join(root_dir, "schema.py")
    default_output = os.path.join(root_dir, "full_paths_to_consider.json")

    parser = argparse.ArgumentParser(description="Flatten a Pydantic schema file into a JSON list of dot-separated paths.")
    parser.add_argument("schema_pos", nargs="?", default=None, help="Positional schema file path")
    parser.add_argument("output_pos", nargs="?", default=None, help="Positional output file or directory path")
    parser.add_argument("-s", "--schema", dest="schema_opt", default=None, help=f"Schema file path (default: {default_schema})")
    parser.add_argument("-o", "--output", dest="output_opt", default=None, help=f"Output JSON file or directory path (default: {default_output})")
    parser.add_argument("-m", "--model", dest="model_name", default=None, help="Specific root model class name to flatten")

    args = parser.parse_args()

    schema_path = args.schema_opt or args.schema_pos or default_schema
    output_path = args.output_opt or args.output_pos or default_output

    schema_path = os.path.abspath(schema_path)
    output_path = os.path.abspath(output_path)

    if os.path.isdir(output_path) or not os.path.splitext(output_path)[1]:
        os.makedirs(output_path, exist_ok=True)
        output_path = os.path.join(output_path, "full_paths_to_consider.json")
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"Loading schema from: {schema_path}")
    module = load_schema_module(schema_path)
    root_model = get_root_model(module, schema_path, args.model_name)
    print(f"Flattening root model: {root_model.__name__}")

    leaf_paths = get_leaf_paths(root_model)
    sorted_paths = [
        p for p in sorted(list(set(leaf_paths)))
        if not any(k in p.lower() for k in ("reason", "anlysis", "analysis", "analytics"))
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted_paths, f, indent=4)

    print(f"Successfully generated {len(sorted_paths)} flattened paths to: {output_path}")


if __name__ == "__main__":
    main()
