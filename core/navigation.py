from playwright.sync_api import Page

MENU_EXPAND_WAIT = 1000


class Navigation:

    def __init__(self, page: Page):
        self.page = page

    def discover(self):

        navigation_tree = []

        menus = self.page.locator("li.list-items")

        print(f"\nFound {menus.count()} Main Menus\n")

        for i in range(menus.count()):

            menu = menus.nth(i)

            try:

                menu_name = (
                    menu.locator("#navigateTo")
                    .inner_text()
                    .strip()
                )

                print(f"\n📂 {menu_name}")

                menu.locator("#navigateTo").click()

                self.page.wait_for_timeout(MENU_EXPAND_WAIT)

                submenu_locator = menu.locator("li[id^='subItem']")

                submenus = []

                for j in range(submenu_locator.count()):

                    submenu = submenu_locator.nth(j)

                    submenu_name = (
                        submenu
                        .locator("#navigateToSubItem")
                        .inner_text()
                        .strip()
                    )

                    print(f"   ├── {submenu_name}")

                    submenus.append({
                        "name": submenu_name,
                        "locator": submenu.locator("#navigateToSubItem"),
                        "url": None,
                        "title": None,
                        "status": "PENDING",
                        "load_time": None,
                        "navigation_type": None,
                        "screenshot": None,
                        "error": None
                    })

                navigation_tree.append({
                    "name": menu_name,
                    "locator": menu.locator("#navigateTo"),
                    "submenus": submenus
                })

            except Exception as e:

                print(f"❌ Error processing menu: {e}")

        return navigation_tree