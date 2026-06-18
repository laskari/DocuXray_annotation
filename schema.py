from enum import Enum
from typing import List, Optional, Any, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, ValidationError

import json  as json_module


def normalize_date_or_time_field(v: Any) -> Optional[str]:
    """
    Normalize date/time fields that may come as either:
    - A simple string: "2021-02-10"
    - An object with value/originalValue: {"originalValue": "02/10/2021", "value": "2021-02-10"}
    
    Returns the normalized string value, preferring 'value' over 'originalValue' when available.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # Prefer 'value' (normalized) over 'originalValue' (raw)
        return v.get('value') or v.get('originalValue') or None
    # For any other type, try to convert to string
    return str(v) if v else None


def normalize_string_or_object_field(v: Any) -> Optional[str]:
    """
    Normalize fields that expect a string but may receive an object.
    If the input is a dict or list, it gets JSON-serialized to a string.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (dict, list)):
        # Serialize object/array to JSON string
        return json_module.dumps(v)
    # For any other type, convert to string
    return str(v) if v else None

class StrictModel(BaseModel):
    """Base model that rejects any field not declared in the schema."""
    model_config = ConfigDict(extra="forbid")


# =============================================================================
# RECEIPT MODELS
# =============================================================================

class AddressStructured(StrictModel):
    """
    Address broken into semantically meaningful components.
    """
    address: Optional[str] = Field(None,description=(
        "Complete street-level address as it appears in the document, combining all available "
        "street address components into a single field. This may include house or building number, "
        "street name, street type, apartment/suite/unit/floor, building or complex name, "
        "district, neighborhood, or sub-locality. Separate each address component using commas "
        "to preserve structure and enable downstream parsing. Preserve the original formatting "
        "and ordering from the source document whenever possible. "
        ))
    city: Optional[str] = Field(None, description="City or town name only, following standard U.S. addressing conventions where the city "
        "appears separately from the street address, state, and ZIP code. Extract only the locality "
        "value explicitly representing the city/town.")
    state: Optional[str] = Field(None, description="State, province, or region code/name.")
    postal_code: Optional[str] = Field(None, description="Postal or ZIP code.")
    country: Optional[str] = Field(None, description="Country name or ISO alpha-3 code (e.g., 'USA', 'GBR'), only if explicitly printed.")

class NumericValue(StrictModel):
    """
    Universal wrapper for any numeric field extracted from a document.
    Covers monetary amounts, percentages, quantities, rates, and any other number.

    - `originalValue`: the raw string exactly as printed (e.g. "1,234.56", "10%", "2 pcs")
    + `value`: the parsed floating-point number (e.g. 1234.56, 10.0, 2.0)
    """
    originalValue: Optional[str] = Field(
        None,
        description="The raw value exactly as it appears printed on the document (e.g. '1,234.56', '10%', '2 pcs'). Preserve bracket notation as-is (e.g. '(102.68)').",
    )

class ReceiptCategory(str, Enum):
    accommodation = "Accommodation"
    food = "Food"
    it_tech = "IT & Tech"
    medical = "Medical"
    motor_expenses = "Motor Expenses"
    office_supplies = "Office Supplies"
    postage = "Postage"
    professional_services = "Professional Services"
    rent_lease = "Rent and Lease"
    telecom_internet = "Telecom and Internet"
    training_education = "Training and Education"
    travel = "Travel"
    utilities_bills = "Utilities and Bills"
    parking = "Vehicle Parking"
    fuel = "Fuel"
    other = "Other"

class ReceiptInfo(StrictModel):
    documentNumber: Optional[str] = Field(None, description="The unique identifier or number of the receipt.")
    txnDate: Optional[str] = Field(None, description="The date of the transaction (only date). Extraction format should be exactly as printed on the document. Do not extract or include any time, timestamp, or timezone information")
    txnDateISO: Optional[str] = Field(None, description="The date of the transaction in ISO 8601 format (YYYY-MM-DD).")
    # dueDate: Optional[str] = Field(None, description="The date by which payment is due, only if explicitly printed on the receipt. Extraction format should be exactly as printed on the document.")
    # dueDateISO: Optional[str] = Field(None, description="The date by which payment is due in ISO 8601 format (YYYY-MM-DD).")
    # purchaseOrderNumber: Optional[str] = Field(None, description="The Purchase Order (PO) number. Extract only when it is explicitly identified as a PO number, Purchase Order number, PO#, PO No., or similar label. Do not infer or guess from other reference, receipt, order, or document numbers.")
    customerNumber: Optional[str] = Field(None, description="The customer account number assigned by the seller (e.g., 'Customer #: 1485223').")
    # paymentTerms: Optional[str] = Field(None, description= "Payment terms as stated on the receipt, specifying when payment is due, the accepted payment method(s), "
    #     "and any agreed-upon conditions, including due periods, payment schedules, "
    #     "discounts, penalties, or arrangements such as 'Due on Receipt', 'Net 15', "
    #     "'Net 30', 'Net 60', or installment payments.")

    # --- Additional fields ---
    customerMemo: Optional[str] = Field(
        None,
        description=(
            "User-entered message to the customer; this message is visible to the customer on their receipt or transaction. "
            "Typically used to provide additional context, notes, or remarks related to the transaction."
        )
    )
    category: Optional[ReceiptCategory] = Field(None, description="Category that best describes the nature of this receipt according to line items.")
    categoryReasoning: Optional[str] = Field(None, description="Detailed reasoning explaining why the specific category was assigned to the receipt.")

    @field_validator('txnDate', 'txnDateISO', mode='before')
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)

class Party(StrictModel):
    name: Optional[str] = Field(None, description="The full name of the party. Follow this extraction hierarchy strictly: "
        "1. Primary Target: Explicitly printed party name(s). Include both the person and company name if both are present. "
        "2. Fallback 1: The first line of the address block, ONLY IF it represents a person or entity name."
        "3. Fallback 2: If the address block lists a person on line 1 and a company on line 2, extract both.")
    addressStructured: Optional[AddressStructured] = Field(None, description="Structured address broken into individual components "
        "(street, city, state, postal code, country).")
    phone: Optional[str] = Field(None, description="The contact phone number of the party. Priority: Telephone>Mobile")
    email: Optional[str] = Field(None, description="The email address of the party.")

class Parties(StrictModel):
    seller: Optional[Party] = Field(None, description="The party selling the goods or services, including the seller's business details "
        "and any associated shipping, dispatch, warehouse, or origin address information "
        "from which the goods are shipped. This may include the seller's operational or "
        "fulfillment location.")
    customer: Optional[Party] = Field(None, description="The primary customer-related party associated with the document, including the purchasing "
        "party, billed party, or end customer. Triggered by labels such as 'Customer', 'Buyer', 'Purchaser', "
        "'Sold To', 'Ordered By', 'Bill To', 'Receipt To', or 'Remit To'. Use this field for the main external "
        "party receiving goods, services, or the receipt, regardless of whether the role is purchasing, "
        "billing, or consuming.")
    # shipTo: Optional[Party] = Field(None, description="Extract the shipment recipient party only when a 'Ship To' or semantically equivalent "
    #     "identifier is explicitly present in the document, such as 'Ship To', 'Deliver To', "
    #     "'Consignee', 'Delivery Address', 'Recipient', or 'Destination'. "
    #     "Do not infer this field from the customer, billing, purchasing, sold-to, or receipt-related "
    #     "parties unless the document explicitly indicates they are also the shipment recipient. "
    #     "This field represents the physical delivery destination or receiving party for the goods.")

class LineItem(StrictModel):
    description: Optional[str] = Field(
        None,
        description=(
            "The name or short description of the item or service exactly as printed on the line. "
            "Do not include administrative or status annotations such as 'VOID NOTE', 'VOID', 'CANCELLED', "
            "or similar prefixes/suffixes â€” extract only the product or service name itself. "
            "Other data like item code, quantity, prices, tax amounts belongs in their respective dedicated fields."
        )
    )
    itemCode: Optional[str] = Field(
        None,
        description=(
            "SKU, part number, or internal item code assigned to the product or service. "
            "Do not extract row numbers, line numbers, or sequential integers used only for ordering rows in the table."
        )
    )
    quantity: Optional[NumericValue] = Field(None, description="The number of units.")
    # unitOfMeasure: Optional[str] = Field(
    #     None,
    #     description=(
    #         "Unit of measure for the quantity (e.g., 'each', 'kg', 'box', 'hr'). "
    #         "Only populate if a dedicated unit label is explicitly printed on the document â€” "
    #         "do not infer or derive from any other field."
    #     )
    # )
    unitPrice: Optional[NumericValue] = Field(
        None,
        description=(
            "The price per single unit; if both a unit price and a List Price "
            "(or List Selling Price (LSP)) are present, use the LSP."
        )
    )

    discountAmount: Optional[NumericValue] = Field(
        None,
        description=(
            "Line item discount amount present in a dedicated 'Discount' column or as a subtraction from the line total. "
            "Extract only when discount is explicitly printed against this specific line, otherwise leave as null."
        )
    )
    discountPercent: Optional[NumericValue] = Field(
        None,
        description=(
            "Line item discount percentage present in a dedicated 'Discount' column or as a percentage against this specific line. "
            "Extract only when discount is explicitly printed against this specific line, otherwise leave as null."
        )
    )

    lineTotalExcludingTax: Optional[NumericValue] = Field(
        None,
        description=(
            "The line total amount excluding tax. "
            "If tax is not applied on this line, populate this field with the line total and leave lineTotalIncludingTax empty."
        )
    )
    lineTaxAmount: Optional[NumericValue] = Field(
        None,
        description=(
            "Tax amount applied to this line item. "
            "Extract only when a numeric tax amount is explicitly printed on the line item row itself â€” "
            "do not infer, calculate, or derive from any other field. "
            "Do NOT source this from receipt-level summary sections, footer totals, or subtotal blocks â€” "
            "these represent aggregated receipt-level figures, not individual line item values. "
        )
    )
    lineTaxPercent: Optional[NumericValue] = Field(
        None,
        description=(
            "Tax rate (percentage) applied to this line item. "
            "Extract only when a numeric tax percentage is explicitly printed on the line item row itself â€” "
            "do not infer, calculate, or derive from any other field. "
            "Do NOT source this from receipt-level summary sections, footer totals, or subtotal blocks â€” "
            "a tax rate shown in a totals area applies to the receipt as a whole and must not be "
            "attributed to any individual line item. "
        )
    )
    lineTotalIncludingTax: Optional[NumericValue] = Field(
        None,
        description=(
            "The line total amount including tax. "
            "Only populate this field when tax is applied on this line â€” "
            "if tax is not applied, leave this empty and use lineTotalExcludingTax instead."
        )
    )

    # --- Additional fields ---
    # serviceDate: Optional[str] = Field(
    #     None,
    #     description=(
    #         "Date the service or product was delivered, as printed on this specific line item row. "
    #         "Extract only if a date is explicitly shown on the line item itself â€” do not infer from "
    #         "the receipt date, header, or any other field. Preserve the exact format as it appears "
    #         "on the document. Set to null if no date is explicitly present on this line item."
    #     )
    # )
    
    # serviceDateISO: Optional[str] = Field(
    #     None,
    #     description=(
    #         "ISO 8601 (YYYY-MM-DD) representation of serviceDate. Populate only when serviceDate "
    #         "was successfully extracted AND contains an unambiguous, complete date with all three "
    #         "components â€” day, month, and year â€” present (e.g. '14/12/24', '14 Dec 2024', '2024-12-14'). "
    #         "Set to null if: serviceDate is null; the date is missing the year (e.g. '15 Jul'); "
    #         "the date is missing the day (e.g. 'Nov-24', 'Jul-24'); or only a year is given (e.g. '2024')."
    #     )
    # )

    # @field_validator('serviceDate', 'serviceDateISO', mode='before')
    # @classmethod
    # def normalize_service_date(cls, v: Any) -> Optional[str]:
    #     return normalize_date_or_time_field(v)

class Charges(StrictModel):
    key: Optional[str] = Field(None, description="The name or label of the charge as printed on the document.")
    value: Optional[NumericValue] = Field(None, description="The amount of the charge as printed on the document.")

class Taxes(StrictModel):
    key: Optional[str] = Field(None, description="The name or label of the tax as explicitly printed on the document (e.g., 'Sales Tax', 'VAT', 'GST', 'State Tax').")
    value: Optional[NumericValue] = Field(None, description="The amount of the tax as explicitly printed on the document.")
    percentage: Optional[NumericValue] = Field(None, description="The rate or percentage of the tax as explicitly printed on the document (e.g., '10%', '18').")

class Totals(StrictModel):
    # --- Discounts ---
    discountTotal: Optional[NumericValue] = Field(
        None,
        description=(
            "Final Discount Amount: Extract only when a total discount amount is explicitly printed "
            "in the totals section as a monetary value, applied against the final subtotal "
            "(e.g., 'Discount: -$50', 'Less discount', 'Trade Discount', 'Promotional Discount'). "
            "only extract if an amount is printed."
        ),
    )
    discountPercentage: Optional[NumericValue] = Field(
        None,
        description=(
            "Final Discount Percentage: Extract only when a total discount percentage is explicitly printed in the totals section (e.g., '5% discount', 'Less 10%'). "
        ),
    )
    # --- Pre-tax subtotals ---
    subtotal: Optional[NumericValue] = Field(
        None,
        description=(
        "Extract the subtotal amount only when it is explicitly printed or clearly identified "
        "in the document using labels such as 'Subtotal', 'Sub Total', 'Net Amount', "
        "'Net Total', 'Merchandise Total', 'Items Total', or other semantically similar identifiers. "
        "This value represents the total of all line item amounts before applying taxes, "
        "shipping, handling, surcharges, discounts, or other additional charges. "
        "Do not infer or calculate the subtotal if it is not explicitly present."
        ),
    )    
    totalExcludingTax: Optional[NumericValue] = Field(
        None,
        description=(
            "The total amount after applying discounts and adding other charges (like freight, handling, "
            "insurance, etc.) but BEFORE any tax is applied. This is the taxable base. "
            "Typically labelled 'Total Before Tax', 'Net Total', or 'Taxable Amount'. "
        ),
    )
    # --- Charges ---
    otherCharges: List[Charges] = Field(None,description=(
        "List of any additional non-line-item charges explicitly printed on the document"
        "that are applied outside the base merchandise or service amounts. e.g. `tips`, `gratuity`, `carry out charge`, `packing charges` etc. "
        "Return one object per charge, where 'key' is the charge label/name and 'value' is the "
        "corresponding charge amount. This field is intended to flexibly capture any extra charges "
        "that may appear across different receipt formats. "
        "Only extract charges that are explicitly mentioned or printed in the document and do not "
        "infer or calculate missing charges. Preserve the original charge label as closely as possible "
        "in the 'key' field."),)

    # --- Tax ---
    taxes: List[Taxes] = Field(None,description=(
        "List of all taxes as explicitly printed or clearly identified in the document using labels "
        "such as 'Tax', 'Total Tax', 'Tax Amount', 'GST', 'VAT', 'Sales Tax', or other semantically "
        "similar identifiers. Return one object per tax, where 'key' is the tax label/name and 'value' is the "
        "corresponding tax amount. Include percentage if explicitly present."))
    
    cash: Optional[NumericValue] = Field(
        None,
        description=(
            "The total amount paid in cash as explicitly printed on the document (e.g., 'Cash Paid', 'Cash Received', 'Cash Tendered'). "
        ),
    )
    
    change: Optional[NumericValue] = Field(
        None,
        description=(
            "The change or refund amount as explicitly printed on the document (e.g., 'Change', 'CG'). "
        ),
    )

    roundingAdjustment: Optional[NumericValue] = Field(
        None,
        description=(
            "The rounding adjustment amount as explicitly printed on the document (e.g., 'Rounding Adjustment'). "
        ),
    )
    # --- Grand total ---
    totalIncludingTax: Optional[NumericValue] = Field(
        None,
        description=(
            "The grand total amount including all taxes, all charges, and after all discounts. "
            "Typically labelled 'Total', 'Receipt Total', 'Grand Total', or 'Total Inc. Tax'."
        ),
    )
    # # --- Payments & credits applied ---
    # deposit: Optional[NumericValue] = Field(
    #     None,
    #     description=(
    #         "Deposit or advance payment already paid and explicitly deducted on this receipt "
    #         "(e.g., 'Deposit Paid', 'Advance', 'Down Payment')."
    #     ),
    # )
    # # --- Final balance ---
    # balanceDue: Optional[NumericValue] = Field(
    #     None,
    #     description=(
    #         "The remaining amount owed as explicitly printed on the document after all payments, "
    #         "credits, and deductions. Also labelled 'Amount Due', 'Balance Due', "
    #         "'Please Pay', 'Total Due', or 'Net Due'."
    #     ),
    # )

    # --- FX ---
    exchangeRate: Optional[NumericValue] = Field(
        None,
        description=(
            "The exchange rate as printed on the document: number of home/reporting currency units "
            "per one unit of the receipt currency (e.g., if receipt is in USD and home currency is INR, "
            "this would be ~83.5). Extract only if explicitly stated."
        ),
    )

# class ShippingInfo(StrictModel):
#     carrier: Optional[str] = Field(None, description="Name of the carrier or shipping company responsible for transporting the goods (e.g., FedEx, UPS, DHL, etc.)")
#     deliveryDate: Optional[str] = Field(None, description="The expected or actual delivery/shipping date. Extract only when a date is explicitly associated "
#         "with labels such as 'Delivery Date', 'Delivered On', 'Expected Delivery', 'Estimated Delivery', "
#         "'Shipment Date', 'Shipping Date', 'Date Shipped', 'Dispatch Date', 'Delivery Schedule', or similar "
#         "delivery/shipping-related terms. Do not infer from receipt dates, order dates, due dates, or other "
#         "unrelated dates. Preserve the date exactly as printed on the document. If no explicit delivery/shipping "
#         "date is present, return null.")
#     deliveryDateISO: Optional[str] = Field(None, description="The delivery/shipping date converted to ISO 8601 format (YYYY-MM-DD), derived from deliveryDate. "
#         "Populate only when an explicit delivery/shipping date is found; otherwise return null.")
#     trackingNumber: Optional[str] = Field(None, description="Shipment tracking number (also labelled 'Waybill #', 'AWB', or 'Airway Bill' or 'Delivery No.' or 'Tracking No.' on some documents).")

#     @field_validator('deliveryDate', 'deliveryDateISO', mode='before')
#     @classmethod
#     def normalize_dates(cls, v: Any) -> Optional[str]:
#         return normalize_date_or_time_field(v)

# =============================================================================
# MAIN DOCUMENT DATA MODELS (FULL SCHEMAS)
# =============================================================================

class ReceiptData(StrictModel):
    """
    Structured receipt content with proper nested Pydantic models.
    """
    currency: Optional[str] = Field(None, description="The primary currency of the receipt as ISO 4217 text code (e.g., 'USD', 'EUR', 'INR'), not currency symbols.")
    receiptInfo: Optional[ReceiptInfo] = Field(None, description="General receipt identification and date info.")

    parties: Optional[Parties] = Field(None, description="Participants in the receipt (seller, buyer, billTo, shipTo, etc.).")
    lineItems: Optional[List[LineItem]] = Field(None, description="Product or service line items from the order table(s). Excludes ancillary charges appended at the end or bottom of any order table.")
    totals: Optional[Totals] = Field(None, description="Financial summary including subtotal, tax, and grand total.")
    applyTaxAfterDiscount: Optional[bool] = Field(True, description="If True, discount is subtracted first and then tax is calculated on the discounted amount. If False or absent, tax is calculated first and then discount is applied.")

# -----------------------------------------------------------------------------
# RECEIPT SPLIT SCHEMAS
# -----------------------------------------------------------------------------

class ReceiptPartParties(StrictModel):
    """
    Part 2: All participants involved in the transaction.
    """
    parties: Optional[Parties] = Field(None, description="Participants in the receipt (seller, buyer).")

class ReceiptPartLineItems(StrictModel):
    """Part 2: Detailed list of line items/products/services."""

    lineItems: Optional[List[LineItem]] = Field(
        None,
        description="Product or service line items from the order table(s). Excludes ancillary charges appended at the end or bottom of any order table."
    )

class ReceiptPartTotals(StrictModel):
    """
    Part 4: Financial totals, tax breakdowns, and payments.
    """
    totals: Optional[Totals] = Field(None, description="Financial summary including subtotal, tax, and grand total.")
    applyTaxAfterDiscount: Optional[bool] = Field(True, description="If True, discount is subtracted first and then tax is calculated on the discounted amount. If False or absent, tax is calculated first and then discount is applied.")

class ReceiptPartOther(StrictModel):
    """
    Part 5: Remaining receipt fields (overflow status, currency, shipping, status).
    """
    receiptInfo: Optional[ReceiptInfo] = Field(None, description="General receipt identification and date info.")
    currency: Optional[str] = Field(None, description="The primary currency of the receipt as ISO 4217 text code (e.g., 'USD', 'EUR', 'INR'), not currency symbols.")


# =============================================================================
# SCHEMA REGISTRY
# =============================================================================

RECEIPT_SCHEMA_MAP: dict = {
    "lineitems": ReceiptPartLineItems,
    "parties":   ReceiptPartParties,
    "totals":    ReceiptPartTotals,
    "other":     ReceiptPartOther,
}

RECEIPT_SPLIT_PARTS: list[str] = ["parties", "lineitems", "totals", "other"]