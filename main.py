import io
import json
import os
import re
import sys

from fetch_offers import main as run_fetch
from login import main as run_login

# Ensure utf-8 output on Windows consoles that default to cp1252
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Non-bank brands (card networks, wallets, UPI apps & fintechs)
NON_BANK_BRANDS: list[str] = [
    "Visa",
    "Mastercard",
    "RuPay",
    "Rupay",
    "Novio",
    "Amex",
    "American Express",
    "Paytm",
    "Amazon Pay",
    "Amazon",
    "MobiKwik",
    "Mobikwik",
    "Bajaj Pay",
    "Bajaj",
    "Jupiter",
    "BHIM",
]

_non_bank_pattern = re.compile(
    r"\b(?:" + "|".join(re.escape(b) for b in NON_BANK_BRANDS) + r")\b",
    re.IGNORECASE,
)

# Patterns to extract issuer / bank / service name from heading:
# 1. "... with/via/using/on <Issuer> Credit/Debit/UPI/wallet/app/Balance ..."
_issuer_prep_pattern = re.compile(
    r"\b(?:with|via|using|on)\s+(.+?)\s+(?:Credit|Debit|UPI|wallet|app|App|Balance|Later|card|cards)\b",
    re.IGNORECASE,
)
# 2. "... Off <Issuer> Credit/Debit ..."
_issuer_off_pattern = re.compile(
    r"\bOff\s+(.+?)\s+(?:Credit|Debit|UPI|app)\b",
    re.IGNORECASE,
)
# 3. Fallback: match after "with/via/using/on " till end of string
_issuer_fallback_pattern = re.compile(
    r"\b(?:with|via|using|on)\s+(.+)$",
    re.IGNORECASE,
)


# Classification helpers

def extract_issuer(heading: str) -> str | None:
    # Clean trailing punctuation
    clean_heading = heading.rstrip(" .")
    
    m = (
        _issuer_prep_pattern.search(clean_heading)
        or _issuer_off_pattern.search(clean_heading)
        or _issuer_fallback_pattern.search(clean_heading)
    )
    if not m:
        return None
    
    issuer = m.group(1).strip()
    # Strip common leading words like "payment via", "using", etc. if captured
    issuer = re.sub(r"^(?:payment via|payments via|using|payment)\s+", "", issuer, flags=re.IGNORECASE).strip()
    return issuer or None


def is_bank_related(heading: str) -> bool:
    issuer = extract_issuer(heading)
    if issuer is None:
        return True  # conservative fallback

    # Check if the issuer is purely one of the non-bank brands
    return not bool(re.fullmatch(
        r"(?:" + "|".join(re.escape(b) for b in NON_BANK_BRANDS) + r")[\w\s,&./]*",
        issuer,
        re.IGNORECASE,
    ))


# Data extraction

def extract_offers(raw: dict) -> list[dict]:
    offers = []
    for widget in raw.get("pageLayout", {}).get("widgets", []):
        if widget.get("widgetType") != "COUPON_CARD_WIDGET":
            continue
        items = widget["data"]["items"]
        meta = items["couponButton"]["action"]["actionMeta"]
        heading = items["heading"]["text"]
        offers.append({
            "heading": heading,
            "coupon_code": items["couponCode"]["text"],
            "issuer": extract_issuer(heading),
            "is_bank": is_bank_related(heading),
            "coupon_type": meta.get("couponType", ""),
            "coupon_id": meta.get("couponId", ""),
            "state": items["couponButton"].get("state", ""),
            "description": items.get("termsAndConditions", {}).get("description", ""),
            "terms": items.get("termsAndConditions", {}).get("terms", []),
        })
    return offers

# To print Non-bank offers (Not that it is used)
def print_non_bank_offers(offers: list[dict]) -> None:
    non_bank = [o for o in offers if not o["is_bank"]]

    print("=" * 60)
    print(f"  Non-Bank / Wallet / UPI / Network Offers ({len(non_bank)})")
    print("=" * 60)
    if not non_bank:
        print("  (none found)")
        return

    for i, offer in enumerate(non_bank, 1):
        print(f"\n  {i:2d}. {offer['heading']}")
        print(f"      Code  : {offer['coupon_code']}")
        print(f"      Brand : {offer['issuer']}")
        print(f"      Type  : {offer['coupon_type']}")
        print(f"      State : {offer['state']}")
        print(f"      Desc  : {offer['description']}")


def print_bank_offers(offers: list[dict]) -> None:
    bank_offers = [o for o in offers if o["is_bank"]]

    print(f"\n{'='*60}")
    print(f"  Bank-Related Offers ({len(bank_offers)})")
    print(f"{'='*60}")

    for i, offer in enumerate(bank_offers, 1):
        print(f"\n  {i:2d}. {offer['heading']}")
        print(f"      Code  : {offer['coupon_code']}")
        print(f"      Bank  : {offer['issuer']}")
        print(f"      Type  : {offer['coupon_type']}")
        print(f"      State : {offer['state']}")
        print(f"      Desc  : {offer['description']}")

    print(f"\n{'='*60}\n")


def filter_and_print(raw_path: str = "raw_offers.json") -> None:
    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    all_offers = extract_offers(raw)
    bank_offers = [o for o in all_offers if o["is_bank"]]
    non_bank = [o for o in all_offers if not o["is_bank"]]

    # Summary
    print(f"Total payment offers : {len(all_offers)}")
    print(f"Bank-related offers  : {len(bank_offers)}")
    print(f"Non-bank offers (filtered out) : {len(non_bank)}")

    # Persist non-bank offers
    with open("non_bank_offers.json", "w", encoding="utf-8") as f:
        json.dump(non_bank, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(non_bank)} non-bank offers -> non_bank_offers.json")

    # Bank offers section
    print_bank_offers(all_offers)


def run_workflow() -> None:
    headless = "--headless" in sys.argv
    relogin = "--relogin" in sys.argv
    auth_file = "auth_state.json"

    # Step 1: Login
    if relogin or not os.path.exists(auth_file):
        reason = "re-login requested" if relogin else f"{auth_file} not found"
        print(f"[1/3] Login — {reason}. Opening browser...")
        run_login()
    else:
        print(f"[1/3] Login skipped — {auth_file} exists. (Pass --relogin to force.)")

    # Step 2: Fetch offers
    print("\n[2/3] Fetching all payment offers from Zepto...")
    exit_code = run_fetch(headless=headless)
    if exit_code != 0:
        print("Fetch failed — aborting. Ensure your cart has at least one item.")
        sys.exit(exit_code)

    # Step 3: Filter & print
    print("\n[3/3] Filtering and printing offers...\n")
    filter_and_print()


if __name__ == "__main__":
    run_workflow()
