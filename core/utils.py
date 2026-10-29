from playwright.sync_api import Page, TimeoutError


def wait_for_internal_navigation(
    page: Page,
    previous_url: str,
    timeout: int = 15000,
) -> bool:
    """
    Wait for a client-side route change without waiting for networkidle.

    Returns True when the URL changes. Returns False when it remains unchanged
    for the bounded timeout. Network-idle is intentionally not required because
    OPC can keep requests active while rendering.
    """
    try:
        page.wait_for_function(
            "(oldUrl) => window.location.href !== oldUrl",
            arg=previous_url,
            timeout=timeout,
        )
        # A route change is enough to identify navigation. Wait only for the
        # document/body to be available, not for all background requests.
        try:
            page.wait_for_load_state("domcontentloaded", timeout=2000)
        except TimeoutError:
            pass

        page.locator("body").wait_for(state="visible", timeout=5000)
        return True

    except TimeoutError:
        return page.url != previous_url


def wait_for_popup(popup: Page):
    """Wait for a popup to become usable without requiring networkidle."""
    try:
        popup.wait_for_load_state("domcontentloaded", timeout=10000)
    except TimeoutError:
        pass

    popup.locator("body").wait_for(state="visible", timeout=10000)


def get_page_metadata(page: Page):
    """Collect basic metadata from any live page."""
    return {
        "url": page.url,
        "title": page.title(),
    }
