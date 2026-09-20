import json
import sys

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

STATE_FILE      = "auth_state.json"
CART_URL        = "https://www.zepto.com/?cart=open"
FETCH_LIST_PATH = "/cart/coupons/fetch-list"
WAIT_MS         = 90_000
PERSONAL_FIELDS = {"cartId", "storeId", "latitude", "longitude", "userAddressId"}


def parse_body(request) -> dict:
    """Return the request payload as a dict, or {} if it isn't a JSON object."""
    try:
        body = json.loads(request.post_data or "")
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def is_all_offers(response) -> bool:
    req = response.request
    if req.method != "POST" or FETCH_LIST_PATH not in req.url:
        return False
    body = parse_body(req)
    return body.get("activeTab") == "PAYMENT_OFFERS_TAB"


def main(headless: bool = False) -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=STATE_FILE)
        page    = context.new_page()
        page.goto(CART_URL)

        # 1. Open the offers sheet and capture the unfiltered response it fires.
        try:
            with page.expect_response(is_all_offers, timeout=WAIT_MS) as resp_info:
                try:
                    page.get_by_text("View all payment offers").click(timeout=15_000)
                except PlaywrightError:
                    print("Couldn't click 'View all payment offers'. Click it yourself.")
            response = resp_info.value
            data     = response.json()
        except PlaywrightError:
            print("No fetch-list response seen. Session may have expired or cart is empty.")
            browser.close()
            return 1

        context.storage_state(path=STATE_FILE)  # persist renewed tokens
        browser.close()

    # 2. Save the response.
    with open("raw_offers.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 3. Save request metadata for debugging.
    req  = response.request
    body = parse_body(req)
    masked = {k: ("<REDACTED>" if k in PERSONAL_FIELDS else v) for k, v in body.items()}
    with open("captured_request.json", "w", encoding="utf-8") as f:
        json.dump({"method": req.method, "url": req.url,
                   "payload": masked, "header_names": sorted(req.headers)},
                  f, ensure_ascii=False, indent=2)

    n_offers = sum(
        w.get("widgetType") == "COUPON_CARD_WIDGET"
        for w in data["pageLayout"]["widgets"]
    )
    filter_key = body.get("filterKey") or "(none — all offers)"
    print(f"Captured {n_offers} coupon widgets (filterKey={filter_key}) -> raw_offers.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(headless="--headless" in sys.argv))