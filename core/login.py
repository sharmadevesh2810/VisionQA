from dotenv import load_dotenv
import os

from core.browser import BrowserManager

load_dotenv()


class LoginManager:

    def __init__(self, url, session_file):

        self.url = url
        self.session_file = session_file

    def login(self):

        username = os.getenv("STAGE_USERNAME")

        password = os.getenv("STAGE_PASSWORD")

        with BrowserManager(headless=False) as page:

            page.goto(self.url)

            print("Opened Login Page")

            # Login selectors will be updated later

            page.wait_for_timeout(5000)

            page.context.storage_state(path=self.session_file)

            print("Session Saved")