from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(ignore_https_errors=True)

    page = context.new_page()

    page.goto("https://opc.astro.stage.xp.irdeto.com")

    print("=" * 60)
    print("Login manually in the browser.")
    print("After you reach the OPC Home page,")
    print("come back here and press ENTER.")
    print("=" * 60)

    input()

    context.storage_state(path="auth/stage.json")

    print("Session saved successfully!")

    browser.close()