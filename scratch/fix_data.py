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

def filter_dict_by_paths(data, valid_paths, current_path=""):
    if not isinstance(data, dict):
        return data

    keys_to_remove = []
    for k, v in data.items():
        new_path = f"{current_path}.{k}" if current_path else k
        
        if isinstance(v, dict):
            filter_dict_by_paths(v, valid_paths, new_path)
            # Remove empty dicts if they are not explicitly in valid paths
            # Wait, if we keep them, they might clutter. But we'll leave clean up for later if needed.
        elif isinstance(v, list):
            new_path_list = f"{new_path}[*]"
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    filter_dict_by_paths(item, valid_paths, new_path_list)
        else:
            # Leaf node
            is_valid = new_path in valid_paths
            if not is_valid:
                keys_to_remove.append(k)

    for k in keys_to_remove:
        del data[k]
        
    return data

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
                        
        # 4. Filter by valid paths
        filter_dict_by_paths(data, valid_paths)
        
        # Clean up empty parent nodes that are not prefixes of valid_paths
        keys_to_delete = []
        for k in list(data.keys()):
            has_valid_child = any(vp.startswith(k) for vp in valid_paths)
            # The root fields in valid_paths
            if not has_valid_child and k not in ["invoiceStatus", "hasPaidStamp", "isOverflowPage", "applyTaxAfterDiscount", "currency"]:
                keys_to_delete.append(k)
                
        for k in keys_to_delete:
            del data[k]
            
        if "taxes" in data:
            del data["taxes"]

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
        post_content["postprocessed"] = data
        if "metadata" in ref_content and "metadata" not in post_content:
            post_content["metadata"] = ref_content["metadata"]

        with open(post_file, 'w', encoding='utf-8') as f:
            json.dump(post_content, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
