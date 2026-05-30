import json
import sys

sys.path.append('.')

try:
    from schema import InvoiceData
except Exception as e:
    print('Error importing schema:', e)
    sys.exit(1)

def get_full_description(model_class, path_parts):
    from typing import get_args, get_origin, Union
    
    if not path_parts:
        return []
    
    part = path_parts[0]
    
    # Handle lists like lineItems[*]
    if part.endswith('[*]'):
        part = part[:-3]
    
    # User's json has some typos/inconsistencies with the schema
    mapping = {
        'shippingAmount': 'otherCharges', # The schema uses 'otherCharges' in Totals for shipping? Or maybe shippingAmount was removed. Let's see if there's a shippingAmount. Actually wait!
    }
    
    if part in mapping and not (hasattr(model_class, 'model_fields') and part in model_class.model_fields):
        part = mapping[part]

    if not hasattr(model_class, 'model_fields') or part not in model_class.model_fields:
        return [f"FIELD_NOT_FOUND:{part}"]
    
    field_info = model_class.model_fields[part]
    desc = field_info.description
    
    descriptions = []
    if desc:
        if getattr(model_class, '__name__', '') == 'InvoiceData' and len(path_parts) > 1:
            pass
        else:
            descriptions.append(desc.strip())
        
    if len(path_parts) == 1:
        return descriptions

    # Recurse to next type
    ann = field_info.annotation
    origin = get_origin(ann)
    
    next_model = ann
    if origin is Union:
        args = get_args(ann)
        next_model = args[0]
        
    origin2 = get_origin(next_model)
    if origin2 is list or origin2 is type(list):
        args = get_args(next_model)
        next_model = args[0]
    elif origin2 is dict or origin2 is type(dict):
        args = get_args(next_model)
        next_model = args[1]
    
    child_descriptions = get_full_description(next_model, path_parts[1:])
    descriptions.extend(child_descriptions)
    
    return descriptions

with open('full_paths_to_consider.json', 'r') as f:
    paths = json.load(f)

result = {}
for path in paths:
    if path == 'hasPaidStamp':
        result[path] = "True if the document contains a paid stamp (e.g., 'PAID' stamp on the invoice image), indicating the invoice has been paid."
        continue
    if path == 'totals.shippingAmount.originalValue':
        result[path] = "The raw value exactly as it appears printed on the document (e.g. '1,234.56', '10%', '2 pcs') for shipping, freight, delivery, or logistics charges."
        continue
    if path == 'totals.otherCharges[*].key':
        result[path] = "The label/name of the other charge as printed on the document (e.g., 'Shipping', 'Delivery', 'Surcharge')."
        continue
    if path == 'totals.otherCharges[*].value.originalValue':
        result[path] = "The raw value of the other charge exactly as it appears printed on the document (e.g., '1,234.56', '10%', '2 pcs')."
        continue
        
    if 'addressStructured' in path:
        part = path.split('.')[-1]
        try:
            from schema import AddressStructured
            if hasattr(AddressStructured, 'model_fields') and part in AddressStructured.model_fields:
                field_desc = AddressStructured.model_fields[part].description.strip()
                doc = AddressStructured.__doc__.strip()
                result[path] = f"{doc} {field_desc}"
                continue
        except Exception:
            pass

    descs = get_full_description(InvoiceData, path.split('.'))
    
    # Filter out NOT FOUND
    descs = [d for d in descs if not d.startswith("FIELD_NOT_FOUND")]
    
    if not descs:
        result[path] = "DESCRIPTION_MISSING"
    else:
        # Join multiple descriptions. Usually the parent has the domain description and child (like originalValue) has format.
        result[path] = " ".join(descs)

with open('paths_with_descriptions.json', 'w') as f:
    json.dump(result, f, indent=4)
print("Updated paths_with_descriptions.json")
