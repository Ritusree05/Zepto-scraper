from playwright.sync_api import sync_playwright

STATE_FILE = "auth_state.json"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.zepto.com")

        input("Log in and set your location in the browser, then press Enter here... ")

        context.storage_state(path=STATE_FILE)
        browser.close()
    print(f"Session saved to {STATE_FILE}")


if __name__ == "__main__":
    main()