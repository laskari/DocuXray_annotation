import json
import os
import glob
import copy
from pathlib import Path

def has_non_null_data(obj):
    if isinstance(obj, dict):
        return any(has_non_null_data(v) for v in obj.values())
    elif isinstance(obj, list):
        return any(has_non_null_data(v) for v in obj)
    else:
        return obj is not None and obj != ""

def combine_address(address_structured):
    if not address_structured or not isinstance(address_structured, dict):
        return None
    parts = []
    # Logical order: building, unit, street_number, street_name, street_type, district
    for key in ["building", "unit", "street_number", "street_name", "street_type", "district"]:
        val = address_structured.get(key)
        if val and isinstance(val, str) and val.strip():
            parts.append(val.strip())
    
    if parts:
        return ", ".join(parts)
    return None

def copy_path(source, target, path_parts):
    if not path_parts:
        return
    
    part = path_parts[0]
    is_list = part.endswith('[*]')
    clean_part = part[:-3] if is_list else part
    
    if is_list:
        source_list = source.get(clean_part) if isinstance(source, dict) else None
        
        if clean_part not in target or target[clean_part] is None:
            target[clean_part] = []
            
        if isinstance(source_list, list):
            while len(target[clean_part]) < len(source_list):
                target[clean_part].append({})
            for i, src_item in enumerate(source_list):
                tgt_item = target[clean_part][i]
                if isinstance(src_item, dict) and isinstance(tgt_item, dict):
                    copy_path(src_item, tgt_item, path_parts[1:])
    else:
        if len(path_parts) == 1:
            if isinstance(source, dict) and clean_part in source:
                target[clean_part] = copy.deepcopy(source[clean_part])
            else:
                target[clean_part] = None
        else:
            source_dict = source.get(clean_part) if isinstance(source, dict) else None
            if clean_part not in target or target[clean_part] is None:
                target[clean_part] = {}
            if isinstance(target[clean_part], dict):
                copy_path(source_dict or {}, target[clean_part], path_parts[1:])

def main():
    PROJECT_ROOT = Path(__file__).resolve().parent
    paths_file = os.path.join(PROJECT_ROOT.parent, "full_paths_to_consider.json")
    
    with open(paths_file, 'r', encoding='utf-8') as f:
        valid_paths = set(json.load(f))
        
    # Dynamically allow our new combined address fields and new taxes fields
    valid_paths.add("totals.taxAmount.originalValue")
    valid_paths.add("totals.taxName")
    valid_paths.add("totals.taxPercentage.originalValue")
    
    # We will also add the address fields for all possible parties just to be safe
    for party in ["customer", "seller", "shipTo"]:
        valid_paths.add(f"parties.{party}.addressStructured.address")

    # Remove the individual address components as requested by user
    components_to_remove = (".building", ".street_name", ".district", ".street_number", ".street_type", ".unit")
    paths_to_remove = [p for p in valid_paths if p.endswith(components_to_remove)]
    for p in paths_to_remove:
        valid_paths.remove(p)

    # Iterate over all refinement.json files as the original data source
    # print(PROJECT_ROOT.parent)
    search_pattern = os.path.join(PROJECT_ROOT.parent, "SKS_Annotation", "model_outputs", "*", "*","refinement.json")
    files = glob.glob(search_pattern)
    
    print(f"Found {len(files)} files to process.")
    
    for ref_file in files:
        with open(ref_file, 'r', encoding='utf-8') as f:
            try:
                ref_content = json.load(f)
            except json.JSONDecodeError:
                continue
                
        # Original data is in refinement -> refined_data
        if "refinement" not in ref_content or "refined_data" not in ref_content["refinement"]:
            continue
            
        # Deepcopy to avoid modifying the original refinement.json in memory (though we don't save it back)
        data = copy.deepcopy(ref_content["refinement"]["refined_data"])
        
        # 1. Handle Taxes
        if "totals" not in data or not isinstance(data["totals"], dict):
            data["totals"] = {}
            
        taxes = data.get("taxes", [])
        if isinstance(taxes, list) and len(taxes) > 0:
            tax = taxes[0]
            tax_amount = tax.get("amount", {}).get("originalValue") if isinstance(tax.get("amount"), dict) else None
            tax_name = tax.get("name")
            tax_percentage = tax.get("percentage", {}).get("originalValue") if isinstance(tax.get("percentage"), dict) else None
        else:
            tax_amount, tax_name, tax_percentage = None, None, None
            
        data["totals"]["taxAmount"] = {"originalValue": tax_amount}
        data["totals"]["taxName"] = tax_name
        data["totals"]["taxPercentage"] = {"originalValue": tax_percentage}
            
        # 2. Handle Parties (billTo, buyer -> customer)
        parties = data.get("parties", {})
        if isinstance(parties, dict):
            customer = parties.get("customer", {})
            if not has_non_null_data(customer):
                billTo = parties.get("billTo", {})
                buyer = parties.get("buyer", {})
                if has_non_null_data(billTo):
                    parties["customer"] = copy.deepcopy(billTo)
                elif has_non_null_data(buyer):
                    parties["customer"] = copy.deepcopy(buyer)
            
            # 3. Combine address fields for all possible parties
            for party_key in ["customer", "seller", "shipTo"]:
                party_data = parties.get(party_key, {})
                if isinstance(party_data, dict):
                    address_structured = party_data.get("addressStructured", {})
                    combined = combine_address(address_structured)
                    address_structured["address"] = combined
                    party_data["addressStructured"] = address_structured
                    parties[party_key] = party_data
                        
        # 4. Reconstruct and filter by valid paths
        clean_data = {}
        for path in sorted(valid_paths):
            copy_path(data, clean_data, path.split('.'))

        # Write to postprocessing.json
        post_file = os.path.join(os.path.dirname(ref_file), "postprocessing.json")
        
        # We need to maintain the same envelope structure for postprocessing.json
        # Check if postprocessing.json already exists to keep its metadata if any
        post_content = {}
        if os.path.exists(post_file):
            try:
                with open(post_file, 'r', encoding='utf-8') as f:
                    post_content = json.load(f)
            except json.JSONDecodeError:
                pass
                
        post_content["document_id"] = ref_content.get("document_id", os.path.basename(os.path.dirname(ref_file)))
        post_content["postprocessed"] = clean_data
        if "metadata" in ref_content and "metadata" not in post_content:
            post_content["metadata"] = ref_content["metadata"]

        with open(post_file, 'w', encoding='utf-8') as f:
            json.dump(post_content, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
