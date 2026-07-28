from playwright.sync_api import Page, TimeoutError


def wait_for_internal_navigation(
    page: Page,
    previous_url: str,
    timeout: int = 15000
) -> bool:
    """
    Waits for an Angular route change.

    Returns:
        True  -> URL changed
        False -> URL remained same
    """

    try:

        page.wait_for_function(
            "(oldUrl) => window.location.href !== oldUrl",
            arg=previous_url,
            timeout=timeout
        )

        page.wait_for_load_state("networkidle")

        page.locator("body").wait_for(
            state="visible",
            timeout=5000
        )

        return True

    except TimeoutError:

        return False


def wait_for_popup(popup: Page):

    """
    Wait until popup is completely loaded.
    """

    popup.wait_for_load_state("domcontentloaded")

    try:
        popup.wait_for_load_state("networkidle")
    except Exception:
        pass

    popup.locator("body").wait_for(
        state="visible",
        timeout=10000
    )


def get_page_metadata(page: Page):

    """
    Collect metadata from any page.
    """

    return {

        "url": page.url,

        "title": page.title()
    }