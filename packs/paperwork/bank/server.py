"""Bank MCP server - read-only access to transaction data."""

import contextlib
import csv
from datetime import datetime
from pathlib import Path

# Default bank data directory
BANK_DIR = Path(__file__).parent.parent.parent.parent / "demo_data" / "bank"


def query_transactions(
    account: str = "",
    min_amount: float = 0.0,
    max_amount: float = 999999999.0,
    description: str = "",
) -> list[dict[str, str]]:
    """Query bank transactions by account, amount range, or description.

    Args:
        account: Filter by account number (optional). Placeholders like [ACCT_1] are accepted.
        min_amount: Minimum transaction amount (optional).
        max_amount: Maximum transaction amount (optional).
        description: Filter by description text (optional). Placeholders like [PERSON_1] are accepted.

    Returns:
        List of matching transactions with date, description, amount, type, and balance.
    """
    transactions = []

    # Find CSV files in the bank directory
    if not BANK_DIR.exists():
        return []

    for csv_file in BANK_DIR.glob("*.csv"):
        try:
            with csv_file.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Apply filters
                    if account and account not in row.get("Account", ""):
                        continue

                    try:
                        amount = abs(float(row.get("Amount", 0)))
                        if amount < min_amount or amount > max_amount:
                            continue
                    except ValueError:
                        continue

                    if (
                        description
                        and description.lower() not in row.get("Description", "").lower()
                    ):
                        continue

                    transactions.append(
                        {
                            "date": row.get("Date", ""),
                            "description": row.get("Description", ""),
                            "amount": row.get("Amount", ""),
                            "type": row.get("Type", ""),
                            "balance": row.get("Balance", ""),
                            "account": row.get("Account", ""),
                        }
                    )
        except (OSError, csv.Error):
            continue  # Skip files that can't be read

    return transactions


def summarise_period(start_date: str = "", end_date: str = "", account: str = "") -> dict[str, str]:
    """Summarize transactions for a given period.

    Args:
        start_date: Start date in YYYY-MM-DD format (optional).
        end_date: End date in YYYY-MM-DD format (optional).
        account: Filter by account number (optional). Placeholders like [ACCT_1] are accepted.

    Returns:
        Summary with total credits, debits, and transaction count.
    """
    total_credits = 0.0
    total_debits = 0.0
    count = 0

    # Parse date filters
    start_dt = None
    end_dt = None
    if start_date:
        with contextlib.suppress(ValueError):
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    if end_date:
        with contextlib.suppress(ValueError):
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    if not BANK_DIR.exists():
        return {
            "total_credits": "0.00",
            "total_debits": "0.00",
            "count": "0",
            "account": account or "all",
        }

    for csv_file in BANK_DIR.glob("*.csv"):
        try:
            with csv_file.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Apply account filter
                    if account and account not in row.get("Account", ""):
                        continue

                    # Apply date filters
                    if start_dt or end_dt:
                        try:
                            txn_date = datetime.strptime(row.get("Date", ""), "%Y-%m-%d")
                            if start_dt and txn_date < start_dt:
                                continue
                            if end_dt and txn_date > end_dt:
                                continue
                        except ValueError:
                            continue

                    # Accumulate amounts
                    try:
                        amount = float(row.get("Amount", 0))
                        txn_type = row.get("Type", "").upper()

                        if txn_type == "CREDIT":
                            total_credits += amount
                        elif txn_type == "DEBIT":
                            total_debits += amount

                        count += 1
                    except ValueError:
                        continue
        except (OSError, csv.Error):
            continue

    return {
        "total_credits": f"{total_credits:.2f}",
        "total_debits": f"{total_debits:.2f}",
        "net": f"{total_credits - total_debits:.2f}",
        "count": str(count),
        "account": account or "all",
    }
