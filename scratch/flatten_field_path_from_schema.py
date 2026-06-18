#!/usr/bin/env python3
"""
Field Path Extractor Utility from Schema

This script parses a Pydantic schema and flattens its hierarchical structure
to extract a unique set of all field paths. It correctly handles lists (e.g., lineItems, taxes)
by replacing numeric array indices with a wildcard placeholder '[*]'.

"""

import json
from typing import Any, get_args, get_origin, Union, List
from pydantic import BaseModel

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import schema

def is_pydantic_model(type_hint: Any) -> bool:
    try:
        return issubclass(type_hint, BaseModel)
    except TypeError:
        return False

def flatten_pydantic_schema(model: type[BaseModel], parent_path: str = "") -> list[str]:
    """
    Recursively flattens a nested Pydantic model structure to yield all complete paths.
    """
    paths = []
    
    for field_name, field_info in model.model_fields.items():
        current_path = f"{parent_path}.{field_name}" if parent_path else field_name
        
        annotation = field_info.annotation
        
        # Resolve Optional, Union
        origin = get_origin(annotation)
        args = get_args(annotation)
        
        base_type = annotation
        if origin is Union:
            types = [arg for arg in args if type(None) is not arg]
            if types:
                base_type = types[0]
                
        origin = get_origin(base_type)
        args = get_args(base_type)
        
        if origin is list or origin is List:
            item_type = args[0] if args else Any
            item_origin = get_origin(item_type)
            item_args = get_args(item_type)
            if item_origin is Union:
                item_types = [arg for arg in item_args if type(None) is not arg]
                if item_types:
                    item_type = item_types[0]
            
            list_path = f"{current_path}[*]"
            if is_pydantic_model(item_type):
                paths.extend(flatten_pydantic_schema(item_type, list_path))
            else:
                paths.append(list_path)
                
        elif is_pydantic_model(base_type):
            paths.extend(flatten_pydantic_schema(base_type, current_path))
            
        else:
            # Primitive values (strings, numbers, bools, None)
            paths.append(current_path)
            
    return paths

import argparse

def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten Pydantic schema into field paths.")
    parser.add_argument("--model", type=str, default="ReceiptData", help="Name of the Pydantic model to flatten (default: ReceiptData)")
    args = parser.parse_args()

    model_name = args.model
    if not hasattr(schema, model_name):
        print(f"Error: model '{model_name}' not found in schema.py")
        return

    model_cls = getattr(schema, model_name)

    print(f"Extracting field paths from schema.{model_name}...")
    
    try:
        paths = flatten_pydantic_schema(model_cls)
        paths = sorted(list(set(paths)))
        
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_file = os.path.join(root_dir, "full_paths_to_consider.json")
        
        with open(output_file, "w", encoding="utf-8") as out_f:
            json.dump(paths, out_f, indent=4)
            
        print(f"Successfully extracted {len(paths)} field paths.")
        print(f"Saved the unique set of paths to '{output_file}'.")
        print("\nFirst 10 paths sample:")
        for path in paths[:10]:
            print(f"  - {path}")
            
    except Exception as e:
        print(f"Error during execution: {e}")

if __name__ == "__main__":
    main()
