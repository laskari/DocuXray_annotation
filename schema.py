from enum import Enum
from typing import List, Optional, Any, Union, Dict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, ValidationError


class StrictModel(BaseModel):
    """Base model that rejects any field not declared in the schema."""
    model_config = ConfigDict(extra="forbid")

import json as json_module


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

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


# =============================================================================
# ENUMS AND CLASSIFICATION
# =============================================================================

class InvoiceCategory(str, Enum):
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
    other = "Other"

class DocumentType(str, Enum):
    invoice = "invoice"
    meaningfulOther = "meaningfulOther"  # Tax docs, purchase orders, contracts, forms
    junk = "junk"  # Blank pages, unreadable, random images

class InvoiceStatus(str, Enum):
    paid = "paid"                  # Fully settled
    unpaid = "unpaid"              # Due but not yet paid
    partial = "partial"            # Partially paid
    processing = "processing"      # Order/fulfillment still in progress
    cancelled = "cancelled"        # Voided or cancelled
    unknown = "unknown"            # Status not determinable from the document


class ClassificationResult(StrictModel):
    documentType: DocumentType = Field(description="The classified type of the document.")
    confidence: float = Field(description="Confidence score for the classification, between 0 and 1.")


# =============================================================================
# COMMON MODELS
# =============================================================================

class NumericValue(StrictModel):
    """
    Universal wrapper for any numeric field extracted from a document.
    Covers monetary amounts, percentages, quantities, rates, and any other number.

    - `originalValue`: the raw string exactly as printed (e.g. "1,234.56", "10%", "2 pcs")
    - `value`: the parsed floating-point number (e.g. 1234.56, 10.0, 2.0)
    """
    originalValue: Optional[str] = Field(
        None,
        description="The raw value exactly as it appears printed on the document (e.g. '1,234.56', '10%', '2 pcs'). Preserve bracket notation as-is (e.g. '(102.68)').",
    )


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
        "**Do not** include city, state/province/region, postal/ZIP code, or country in this field."
        ))
    city: Optional[str] = Field(None, description="City or town name only, following standard U.S. addressing conventions where the city "
        "appears separately from the street address, state, and ZIP code. Extract only the locality "
        "value explicitly representing the city/town.")
    state: Optional[str] = Field(None, description="State, province, or region code/name.")
    postal_code: Optional[str] = Field(None, description="Postal or ZIP code.")
    country: Optional[str] = Field(None, description="Country name or ISO alpha-3 code (e.g., 'USA', 'GBR'), only if explicitly printed.")
# =============================================================================
# INVOICE MODELS
# =============================================================================

class InvoiceInfo(StrictModel):
    documentNumber: Optional[str] = Field(None, description="The unique identifier or number of the invoice.")
    issueDate: Optional[str] = Field(None, description="The date the invoice was issued(only date). Extraction format should be exactly as printed on the document.")
    issueDateISO: Optional[str] = Field(None, description="The date the invoice was issued in ISO 8601 format (YYYY-MM-DD).")
    dueDate: Optional[str] = Field(None, description="The date by which payment is due, only if explicitly printed on the invoice. Extraction format should be exactly as printed on the document.")
    dueDateISO: Optional[str] = Field(None, description="The date by which payment is due in ISO 8601 format (YYYY-MM-DD).")
    purchaseOrderNumber: Optional[str] = Field(None, description="The associated Purchase Order (PO) number.")
    customerNumber: Optional[str] = Field(None, description="The customer account number assigned by the seller (e.g., 'Customer #: 1485223').")
    paymentTerms: Optional[str] = Field(None, description="Terms of payment (e.g., 'Net 30', 'Due on receipt').")

    # --- Additional fields ---
    customerMemo: Optional[str] = Field(
        None,
        description=(
            "User-entered message to the customer; this message is visible to the customer on their invoice or transaction. "
            "Typically used to provide additional context, notes, or remarks related to the transaction."
        )
    )
    category: Optional[InvoiceCategory] = Field(None, description="Category that best describes the nature of this invoice according to line items.")

    @field_validator('issueDate', 'issueDateISO', 'dueDate', 'dueDateISO', mode='before')
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)

class Party(StrictModel):
    name: Optional[str] = Field(None, description="The name of the entity (person or company).")
    addressStructured: Optional[AddressStructured] = Field(None, description="Structured address broken into individual components (street, city, state, postal code, country).")
    phone: Optional[str] = Field(None, description="The contact phone number of the entity.")
    email: Optional[str] = Field(None, description="The email address of the entity.")

class Parties(StrictModel):
    seller: Optional[Party] = Field(None, description="The entity selling the goods or services, including the seller's business details "
        "and any associated shipping, dispatch, warehouse, or origin address information "
        "from which the goods are shipped. This may include the seller's operational or "
        "fulfillment location, but must not capture carrier, courier, freight, logistics, "
        "or transportation provider details responsible only for delivering the shipment.")
    customer: Optional[Party] = Field(None, description="The primary customer-related entity associated with the document, including the purchasing party, billed party, or end customer. Triggered by labels such as 'Customer', 'Buyer', 'Purchaser', 'Sold To', 'Ordered By', 'Bill To', 'Invoice To', or 'Remit To'. Use this field for the main external party receiving goods, services, or the invoice, regardless of whether the role is purchasing, billing, or consuming.")
    shipTo: Optional[Party] = Field(None, description="Extract the shipment recipient party only when a 'Ship To' or semantically equivalent "
        "identifier is explicitly present in the document, such as 'Ship To', 'Deliver To', "
        "'Consignee', 'Delivery Address', 'Recipient', or 'Destination'. "
        "Do not infer this field from the customer, billing, purchasing, sold-to, or invoice-related "
        "parties unless the document explicitly indicates they are also the shipment recipient. "
        "This field represents the physical delivery destination or receiving party for the goods.")

class LineItem(StrictModel):
    description: Optional[str] = Field(None, description="The name or short description of the item or service exactly as printed on the line. Other data like serial numbers, lot/batch numbers, model numbers, quantities, prices, discounts, tax amounts belongs in their respective dedicated fields.")
    itemCode: Optional[str] = Field(None, description="SKU, part number, or internal item code.")
    quantity: Optional[NumericValue] = Field(None, description="The number of units.")
    unitOfMeasure: Optional[str] = Field(None, description="Unit of measure for the quantity (e.g., 'each', 'kg', 'box', 'hr').")
    unitPrice: Optional[NumericValue] = Field(None, description="The price per single unit; if both a unit price and a List Price(or List Selling Price (LSP)) are present, use the LSP.")
    
    discountAmount: Optional[NumericValue] = Field(None, description="Line item discount amount present in a dedicated 'Discount' column or as a subtraction from the line total. Extract only when discount is explicitly printed against this specific line, otherwise leave as null.")
    discountPercent: Optional[NumericValue] = Field(None, description="Line item discount percentage present in a dedicated 'Discount' column or as a percentage against this specific line. Extract only when discount is explicitly printed against this specific line, otherwise leave as null.")
    
    lineTotalExcludingTax: Optional[NumericValue] = Field(None, description="The net amount for this line item excluding tax. May equal lineTotalIncludingTax if no tax is applied.")
    lineTaxAmount: Optional[NumericValue] = Field(None, description="Line item tax amount present in a dedicated 'Tax' column or as a tax value against this specific line. Extract only when tax is explicitly printed against this specific line, otherwise leave as null.")
    lineTaxPercent: Optional[NumericValue] = Field(None, description="Line item tax percentage present in a dedicated 'Tax' column or as a percentage against this specific line. Extract only when tax is explicitly printed against this specific line, otherwise leave as null.")
    lineTotalIncludingTax: Optional[NumericValue] = Field(None, description="The net amount for this line item including tax. May equal lineTotalExcludingTax if no tax is applied.")

    # --- Additional fields ---
    serviceDate: Optional[str] = Field(None, description="Date the service or product was delivered for this line item. Extraction format should be exactly as printed on the document.")
    serviceDateISO: Optional[str] = Field(None, description="Date the service or product was delivered for this line item in ISO 8601 format (YYYY-MM-DD).") 

    @field_validator('serviceDate', 'serviceDateISO', mode='before')
    @classmethod
    def normalize_service_date(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)

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
    otherCharges: Optional[Dict[str, NumericValue]] = Field(None,description=(
        "Dictionary of any additional non-line-item charges explicitly printed on the document "
        "that are applied outside the base merchandise or service amounts. "
        "Use the charge label/name as the dictionary key and the corresponding charge amount "
        "as the value. This field is intended to flexibly capture any extra charges that may "
        "appear across different invoice formats. "
        "Only extract charges that are explicitly mentioned or printed in the document and do not "
        "infer or calculate missing charges. Preserve the original charge label as closely as possible "
        "for the dictionary key."),)

    # --- Tax ---
    taxAmount: Optional[NumericValue] = Field(
        None,
        description=(
            "Extract the total tax amount only when it is explicitly printed or clearly identified "
            "in the document using labels such as 'Tax', 'Total Tax', 'Tax Amount', "
            "'GST', 'VAT', 'Sales Tax', or other semantically similar identifiers. "
            "This field represents the overall tax amount charged on the document. "
            "Do not calculate, infer, or sum individual tax lines if a total tax amount is not "
            "explicitly present in the document or image."
        ),
    )

    taxName: Optional[str] = Field(None,description=(
        "The explicit name or label of the tax associated with the extracted taxAmount, "
        "exactly as shown in the document. Examples may include 'Sales Tax', 'State Tax', "
        "'County Tax', 'City Tax', 'Use Tax', 'VAT', 'GST', or other printed tax identifiers. "
        "Extract only when explicitly present and do not infer, standardize, or normalize the value."),)

    taxPercentage: Optional[NumericValue] = Field(None,description=(
            "The explicit tax rate or percentage associated with the extracted taxAmount, "
            "as printed in the document (e.g., '10%', '18', 'VAT Rate'). "
            "Extract only when explicitly present alongside or clearly associated with the taxAmount. "
            "Do not calculate or infer the percentage from the tax amount or subtotal."
        ),
    )
    # --- Grand total ---
    totalIncludingTax: Optional[NumericValue] = Field(
        None,
        description=(
            "The grand total amount including all taxes, all charges, and after all discounts. "
            "Typically labelled 'Total', 'Invoice Total', 'Grand Total', or 'Total Inc. Tax'."
        ),
    )
    # --- Payments & credits applied ---
    deposit: Optional[NumericValue] = Field(
        None,
        description=(
            "Deposit or advance payment already paid and explicitly deducted on this invoice "
            "(e.g., 'Deposit Paid', 'Advance', 'Down Payment')."
        ),
    )
    # --- Final balance ---
    balanceDue: Optional[NumericValue] = Field(
        None,
        description=(
            "The remaining amount owed as explicitly printed on the document after all payments, "
            "credits, and deductions. Also labelled 'Amount Due', 'Balance Due', "
            "'Please Pay', 'Total Due', or 'Net Due'."
        ),
    )

    # --- FX ---
    exchangeRate: Optional[NumericValue] = Field(
        None,
        description=(
            "The exchange rate as printed on the document: number of home/reporting currency units "
            "per one unit of the invoice currency (e.g., if invoice is in USD and home currency is INR, "
            "this would be ~83.5). Extract only if explicitly stated."
        ),
    )

class ShippingInfo(StrictModel):
    carrier: Optional[str] = Field(None, description="The company responsible for shipping.")
    deliveryDate: Optional[str] = Field(None, description="The expected or actual delivery date or shipping date. Extraction format should be exactly as printed on the document if a valid delivery date is fount, else null.")
    deliveryDateISO: Optional[str] = Field(None, description="The expected or actual delivery date or shipping date in ISO 8601 format (YYYY-MM-DD).")
    trackingNumber: Optional[str] = Field(None, description="Shipment tracking number (also labelled 'Waybill #', 'AWB', or 'Airway Bill' or 'Delivery No.' or 'Tracking No.' on some documents).")

    @field_validator('deliveryDate', 'deliveryDateISO', mode='before')
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)

# =============================================================================
# OTHER DOCUMENT MODELS
# =============================================================================

class KeyValuePair(StrictModel):
    """Key-value pair for labeled fields in forms and documents."""
    key: Optional[str] = None
    value: Optional[str] = None


class OtherDocumentInfo(StrictModel):
    """General document metadata."""
    documentTitle: Optional[str] = None
    documentNumber: Optional[str] = None
    documentType: Optional[str] = None
    issueDate: Optional[str] = Field(None, description="The document issue date. Extraction format should be exactly as printed on the document.")
    issueDateISO: Optional[str] = Field(None, description="The document issue date in ISO 8601 format (YYYY-MM-DD).")

    @field_validator('issueDate', 'issueDateISO', mode='before')
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)


class OtherDocumentData(StrictModel):
    """
    Simplified structured extraction for 'meaningfulOther' document types.
    Handles tax documents, purchase orders, contracts, forms, applications, etc.
    """

    # Basic document info
    documentInfo: Optional[OtherDocumentInfo] = None

    # Parties (reuse existing Party model for flexibility)
    parties: Optional[List[Party]] = None

    # Flexible key-value pairs for all labeled fields
    fields: Optional[List[KeyValuePair]] = None

    # Financial amounts if applicable
    amounts: Optional[List[KeyValuePair]] = None

    # Signatures/certifications
    signatures: Optional[List[str]] = None

    # Backwards compatibility fallback
    rawJsonString: Optional[str] = Field(
        None,
        description="FALLBACK: Use structured fields above when possible."
    )


# =============================================================================
# MAIN DOCUMENT DATA MODELS (FULL SCHEMAS)
# =============================================================================

class InvoiceData(StrictModel):
    """
    Structured invoice content with proper nested Pydantic models.
    """
    currency: Optional[str] = Field(None, description="The primary currency of the invoice as ISO 4217 text code (e.g., 'USD', 'EUR', 'INR'), not currency symbols.")
    invoiceInfo: Optional[InvoiceInfo] = Field(None, description="General invoice identification and date info.")
    parties: Optional[Parties] = Field(None, description="Participants in the invoice (seller, buyer, billTo, shipTo, etc.).")
    lineItems: Optional[List[LineItem]] = Field(None, description="Detailed list of items or services billed.")
    totals: Optional[Totals] = Field(None, description="Financial summary including subtotal, tax, and grand total.")
    shippingInfo: Optional[ShippingInfo] = Field(None, description="Carrier and logistics details.")
    invoiceStatus: Optional[InvoiceStatus] = Field(None, description="The payment/fulfillment status of the invoice. Use 'paid' if fully settled, 'unpaid' if outstanding, 'partial' if partially paid, 'processing' if still being fulfilled, 'cancelled' if voided, or 'unknown' if not determinable.")
    isOverflowPage: Optional[bool] = Field(None, description="True if this page is a continuation of a table from the previous page (no new document header, line items continue mid-stream). False if this is a fresh page.")
    applyTaxAfterDiscount: Optional[bool] = Field(True, description="If True, discount is subtracted first and then tax is calculated on the discounted amount. If False or absent, tax is calculated first and then discount is applied.")

# -----------------------------------------------------------------------------
# INVOICE SPLIT SCHEMAS
# -----------------------------------------------------------------------------

class InvoicePartGeneral(StrictModel):
    """
    Part 1: General invoice metadata, currency, and category.
    """
    currency: Optional[str] = Field(None, description="The primary currency of the invoice as ISO 4217 text code (e.g., 'USD', 'EUR', 'INR'), not currency symbols.")
    invoiceInfo: Optional[InvoiceInfo] = Field(None, description="General invoice identification and date info.")
    invoiceStatus: Optional[InvoiceStatus] = Field(None, description="The payment/fulfillment status of the invoice. Use 'paid' if fully settled, 'unpaid' if outstanding, 'partial' if partially paid, 'processing' if still being fulfilled, 'cancelled' if voided, or 'unknown' if not determinable.")

class InvoicePartParties(StrictModel):
    """
    Part 2: All participants involved in the transaction.
    """
    parties: Optional[Parties] = Field(None, description="Participants in the invoice (seller, buyer, billTo, shipTo, etc.).")
    shippingInfo: Optional[ShippingInfo] = Field(None, description="Carrier and logistics details.")

class InvoicePartLineItems(StrictModel):
    """
    Part 3: Detailed list of line items/products/services.
    """
    lineItems: Optional[List[LineItem]] = Field(None, description="Detailed list of items or services billed.")
    isOverflowPage: Optional[bool] = Field(None, description="True if this page is a continuation of a table from the previous page (no new document header, line items continue mid-stream). False if this is a fresh page.")

class InvoicePartTotals(StrictModel):
    """
    Part 4: Financial totals, tax breakdowns, and payments.
    """
    totals: Optional[Totals] = Field(None, description="Financial summary including subtotal, tax, and grand total.")
    applyTaxAfterDiscount: Optional[bool] = Field(True, description="If True, discount is subtracted first and then tax is calculated on the discounted amount. If False or absent, tax is calculated first and then discount is applied.")


# =============================================================================
# DOCUMENT EXTRACTION RESULT (Wrapper)
# =============================================================================

class DocumentTypeAlternative(StrictModel):
    type: DocumentType = Field(description="Alternative document type candidate.")
    confidence: float = Field(description="Confidence score for this candidate.")


class ExtractionMetadata(StrictModel):
    pageCount: Optional[int] = Field(None, description="Total number of pages processed.")
    language: Optional[str] = Field(None, description="Detected language of the document (e.g., 'English', 'Spanish').")
    sourceCountryIfObvious: Optional[str] = Field(None, description="The country the document likely originates from.")
    extractionDate: Optional[str] = Field(None, description="The date the extraction occurred.")
    extractionDateISO: Optional[str] = Field(None, description="The date the extraction occurred in ISO 8601 format.")

    @field_validator('extractionDate', 'extractionDateISO', mode='before')
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)


class DocumentExtractionResult(StrictModel):
    documentType: DocumentType = Field(description="The primary identified type of the document (e.g., invoice, receipt).")
    documentTypeConfidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score for the primary document type."
    )
    documentTypeAlternatives: List[DocumentTypeAlternative] = Field(
        default_factory=list, description="A list of other possible document types and their confidence scores."
    )

    metadata: ExtractionMetadata = Field(
        default_factory=ExtractionMetadata, description="Metadata about the extraction process."
    )

    # Type-specific extracted data; ONLY ONE should be non-null
    invoiceOutputData: Optional[InvoiceData] = Field(None, description="Extracted data specifically for Invoices.")
    otherDocumentData: Optional[OtherDocumentData] = Field(None, description="Extracted data for documents not matching known types.")


# =============================================================================
# SCHEMA REGISTRY (used by extraction service)
# =============================================================================

SCHEMA_MAP = {
    "full":    InvoiceData,
    "general": InvoicePartGeneral,
    "parties": InvoicePartParties,
    "items":   InvoicePartLineItems,
    "totals":  InvoicePartTotals,
}

SPLIT_PARTS = ["general", "parties", "items", "totals"]
