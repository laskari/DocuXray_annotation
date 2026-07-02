RECEIPT_SCHEMA_MAP = {
    "full":      ReceiptData,
    "lineitems": ReceiptPartLineItems,
    "parties":   ReceiptPartParties,
    "totals":    ReceiptPartTotals,
    "other":     ReceiptPartOther,
}

RECEIPT_SPLIT_PARTS = ["parties", "lineitems", "totals", "other"]


# =============================================================================
# BANK STATEMENT MODELS
# =============================================================================

class TransactionType(str, Enum):
    credit = "Credit"
    debit = "Debit"
    transfer = "Transfer"
    deposit = "Deposit"
    direct_deposit = "Direct Deposit"
    withdrawal = "Withdrawal"
    check = "Check"
    payment = "Payment"
    fee = "Fee"
    interest = "Interest"
    refund = "Refund"
    other = "Other"


class BankAccountHolder(StrictModel):
    name: Optional[str] = Field(
        None,
        description=(
            "Full name of the account holder or entity as printed on the statement "
            "(e.g., 'John M. Smith', 'Acme Corp Ltd'). Extract verbatim."
        ),
    )
    addressStructured: Optional[AddressStructured] = Field(
        None,
        description="Structured mailing address of the account holder broken into individual components (street, city, state, postal code, country).",
    )


class BankStatementInfo(StrictModel):
    bankName: Optional[str] = Field(
        None,
        description="Name of the financial institution issuing the statement, exactly as printed (e.g., 'Chase Bank', 'HSBC', 'Bank of America').",
    )
    accountNumber: Optional[str] = Field(
        None,
        description=(
            "Account number as printed on the statement. "
            "May be fully or partially masked (e.g., '****1234', 'XXXX-XXXX-5678'). "
            "Extract verbatim — do not unmask or infer missing digits."
        ),
    )
    accountType: Optional[str] = Field(
        None,
        description="Type of account as labeled on the statement (e.g., 'Checking', 'Savings', 'Current', 'Money Market').",
    )
    routingNumber: Optional[str] = Field(
        None,
        description=(
            "ABA routing/transit number as printed on the statement (9-digit US bank identifier). "
            "Extract verbatim — do not infer or correct digits. "
            "May appear labeled as 'Routing Number', 'ABA Number', or 'Transit Number'."
        ),
    )
    statementPeriodStart: Optional[str] = Field(
        None,
        description="Start date of the statement period exactly as printed (e.g., 'Jan 1, 2024', '01/01/2024').",
    )
    statementPeriodStartISO: Optional[str] = Field(
        None,
        description="Start date of the statement period in ISO 8601 format (YYYY-MM-DD). Derive from the printed value only.",
    )
    statementPeriodEnd: Optional[str] = Field(
        None,
        description="End date of the statement period exactly as printed.",
    )
    statementPeriodEndISO: Optional[str] = Field(
        None,
        description="End date of the statement period in ISO 8601 format (YYYY-MM-DD). Derive from the printed value only.",
    )
    openingBalance: Optional[NumericValue] = Field(
        None,
        description=(
            "Account balance at the start of the statement period as printed. "
            "Also labeled 'Beginning Balance', 'Opening Balance', or 'Balance Brought Forward'."
        ),
    )
    closingBalance: Optional[NumericValue] = Field(
        None,
        description=(
            "Account balance at the end of the statement period as printed. "
            "Also labeled 'Ending Balance', 'Closing Balance', or 'Balance Carried Forward'."
        ),
    )

    @field_validator(
        "statementPeriodStart",
        "statementPeriodStartISO",
        "statementPeriodEnd",
        "statementPeriodEndISO",
        mode="before",
    )
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)


class BankStatementTransaction(StrictModel):
    date: Optional[str] = Field(
        None,
        description=(
            "The date of the transaction exactly as it appears printed on the statement. "
            "Preserve the original format (e.g., '01/15/2024', '15 Jan 2024', '2024-01-15'). "
            "Do not reformat, normalize, or infer missing dates."
        ),
    )
    dateISO: Optional[str] = Field(
        None,
        description="The transaction date converted to ISO 8601 format (YYYY-MM-DD). Derive from the printed date field only.",
    )
    description: Optional[str] = Field(
        None,
        description=(
            "The full transaction narrative exactly as printed in the statement's description, "
            "memo, or particulars column. This typically includes the payee name, merchant, "
            "transaction channel (e.g., 'POS', 'ACH', 'WIRE'), location, or any reference text "
            "the bank associates with the transaction. Preserve the original casing and spacing. "
            "Do not summarize, truncate, or clean up the value."
        ),
    )
    type: Optional[TransactionType] = Field(
        None,
        description=(
            "AI-inferred transaction category. This field is NOT extracted verbatim — classify it "
            "by reading the description, the printed transaction code (e.g., 'POS', 'ACH CR', 'ATM WD'), "
            "and whether an amount appears in the credit or debit column. "
            "Rules: 'Credit' — money arriving in the account (salary, transfers in, interest credited); "
            "'Debit' — card purchases, online payments, POS transactions; "
            "'Transfer' — inter-account or wire movements (both inbound and outbound); "
            "'Deposit' — manual, ATM, or check deposits of funds into the account; "
            "'Direct Deposit' — payroll, government benefits, or tax refunds deposited electronically; "
            "'Withdrawal' — cash taken out at an ATM or bank counter; "
            "'Check' — written check payments cleared against the account; "
            "'Payment' — bill payments, loan repayments, credit card payments; "
            "'Fee' — bank service charges, overdraft fees, account maintenance fees; "
            "'Interest' — interest earned on the account balance or charged on an overdraft; "
            "'Refund' — merchant reversals, returned payments, or disputed transaction credits. "
            "Use 'Other' only when none of the above applies and the type genuinely cannot be determined."
        ),
    )
    amountIn: Optional[NumericValue] = Field(
        None,
        description=(
            "Money flowing INTO the account for this transaction — regardless of transaction type. "
            "Maps to the credit, deposit, or 'CR' column on the statement. "
            "Populate this field for any transaction that adds funds to the account: "
            "incoming transfers, direct deposits, refunds, interest credits, cash deposits, etc. "
            "Extract the raw value exactly as printed (e.g., '1,250.00', '500'). "
            "Leave null only if this row has no value in the inflow column."
        ),
    )
    amountOut: Optional[NumericValue] = Field(
        None,
        description=(
            "Money flowing OUT OF the account for this transaction — regardless of transaction type. "
            "Maps to the debit, withdrawal, or 'DR' column on the statement. "
            "Populate this field for any transaction that removes funds from the account: "
            "outgoing transfers, payments, purchases, fees, ATM withdrawals, cheques cleared, etc. "
            "Extract the raw value exactly as printed. Some statements show outflows in brackets (e.g., '(200.00)') — "
            "preserve bracket notation as-is. Leave null only if this row has no value in the outflow column."
        ),
    )
    balance: Optional[NumericValue] = Field(
        None,
        description=(
            "The running account balance after this transaction has been applied, "
            "as printed in the balance or 'running total' column of the statement. "
            "Extract the value exactly as printed. Leave null if the statement does not show a per-row balance."
        ),
    )
    referenceNumber: Optional[str] = Field(
        None,
        description=(
            "Any unique identifier printed on the statement against this transaction. "
            "This includes check numbers, cheque numbers, wire reference codes, ACH trace IDs, "
            "authorization codes, transaction IDs, or confirmation numbers. "
            "Common labels: 'Ref #', 'Ref No.', 'Chq No.', 'Check No.', 'Trace ID', 'Auth Code', 'TXN ID'. "
            "Extract verbatim. Leave null if no reference identifier is present for this row."
        ),
    )

    @field_validator("date", "dateISO", mode="before")
    @classmethod
    def normalize_transaction_date(cls, v: Any) -> Optional[str]:
        return normalize_date_or_time_field(v)


class BankStatementData(StrictModel):
    """Structured extraction output for bank statements."""
    currency: Optional[str] = Field(
        None,
        description="ISO 4217 currency code for all monetary amounts in this statement (e.g., 'USD', 'GBP', 'EUR').",
    )
    accountHolder: Optional[BankAccountHolder] = Field(
        None,
        description="Details of the account holder as printed on the statement.",
    )
    statementInfo: Optional[BankStatementInfo] = Field(
        None,
        description="Statement-level metadata: bank name, account number, account type, statement period, and opening/closing balances.",
    )
    transactions: Optional[List[BankStatementTransaction]] = Field(
        None,
        description=(
            "Complete ordered list of every transaction row appearing in the statement, "
            "extracted in the same top-to-bottom order as printed. "
            "Each row in the transaction table must produce exactly one entry — do not skip, "
            "merge, or deduplicate rows."
        ),
    )
    isOverflowPage: Optional[bool] = Field(
        None,
        description=(
            "True if this page is a mid-table continuation from the previous page — "
            "i.e., the transaction table carries over with no new statement header or account summary at the top. "
            "False if this page starts a fresh statement or a new transaction table header."
        ),
    )


# =============================================================================
# BANK STATEMENT SPLIT PART MODELS
# =============================================================================

class BankStatementPartGeneral(StrictModel):
    """Part 1: currency, account holder, and page-continuity flag."""
    currency: Optional[str] = Field(
        None,
        description="ISO 4217 currency code for all monetary amounts in this statement (e.g., 'USD', 'GBP', 'EUR').",
    )
    accountHolder: Optional[BankAccountHolder] = Field(
        None,
        description="Details of the account holder as printed on the statement.",
    )
    isOverflowPage: Optional[bool] = Field(
        None,
        description=(
            "True if this page is a mid-table continuation from the previous page — "
            "i.e., the transaction table carries over with no new statement header or account summary at the top. "
            "False if this page starts a fresh statement or a new transaction table header."
        ),
    )


class BankStatementPartTransactions(StrictModel):
    """Part 2: the full ordered list of transaction rows."""
    transactions: Optional[List[BankStatementTransaction]] = Field(
        None,
        description=(
            "Complete ordered list of every transaction row appearing in the statement, "
            "extracted in the same top-to-bottom order as printed. "
            "Each row in the transaction table must produce exactly one entry — do not skip, "
            "merge, or deduplicate rows."
        ),
    )


class BankStatementPartStatementInfo(StrictModel):
    """Part 3: bank and account metadata, statement period, opening/closing balances."""
    statementInfo: Optional[BankStatementInfo] = Field(
        None,
        description="Statement-level metadata: bank name, account number, account type, statement period, and opening/closing balances.",
    )


# =============================================================================
# BANK STATEMENT SCHEMA REGISTRY
# =============================================================================

BANK_STATEMENT_SCHEMA_MAP = {
    "general":        BankStatementPartGeneral,
    "transactions":   BankStatementPartTransactions,
    "statement_info": BankStatementPartStatementInfo,
}

BANK_STATEMENT_SPLIT_PARTS = ["general", "transactions", "statement_info"]


# Resolve the forward reference on DocumentExtractionResult now that
# BankStatementData is defined in this module.
# DocumentExtractionResult.model_rebuild()