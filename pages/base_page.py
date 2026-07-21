from playwright.sync_api import Page
import subprocess
import platform
import time
import os

class Base:
    def __init__(self, page: Page):
        self.page = page

    def go_to_site(self, url: str, timeout=30000):
        """Navigate to a URL."""
        self.page.goto(url, timeout=timeout)
        return self

    def get_by_text(self, text, exact=True):
        """Return a locator by text."""
        return self.page.get_by_text(text, exact=exact)

    def click(self, locator: str):
        """Click an element by locator."""
        self.page.click(locator)
        return self

    def check(self, locator: str):
        """Check a checkbox by locator."""
        self.page.check(locator)
        return self

    def fill_input(self, locator: str, value: str):
        """Fill a text input by locator."""
        self.page.fill(locator, value)
        return self

    def wait_for_selector(self, selector, timeout=10000):
        """Wait until a selector appears."""
        self.page.wait_for_selector(selector, timeout=timeout)
        return self

    def wait(self, mc: int):
        """Wait for the given number of milliseconds."""
        self.page.wait_for_timeout(mc)
        return self

    def confirm_system_dialog(self, coord_set=1):
        system = platform.system()
        if system == "Linux":
            time.sleep(2)
            os.environ['DISPLAY'] = ':99'

            coords = {
                1: (136, 264),  # OK button for the certificate selection dialog.
                2: (1126, 680),  # OK button for the password dialog.
                3: (138, 121),  # OK button for the certificate installation dialog.
            }
            window_names = {
                1: ["Authentication - CryptoPro CSP", "CryptoPro CSP"],
                2: ["Authentication - CryptoPro CSP", "CryptoPro CSP"],
                3: ["CryptoPro CSP"],
            }

            if coord_set not in coords:
                coord_set = 1

            if coord_set in window_names and self.confirm_system_dialog_by_window_focus(window_names[coord_set]):
                return True

            ok_x, ok_y = coords[coord_set]

            subprocess.run(['xdotool', 'mousemove', str(ok_x), str(ok_y), 'click', '1'], check=False)
            time.sleep(0.5)
            return True

        elif system in ["Windows", "Darwin"]:
            return True

        return False

    def confirm_system_dialog_by_window_focus(self, window_names):
        for window_name in window_names:
            search_result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", window_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            window_ids = [window_id.strip() for window_id in search_result.stdout.splitlines() if window_id.strip()]

            for window_id in window_ids:
                focus_result = subprocess.run(
                    ["xdotool", "windowfocus", "--sync", window_id, "key", "Return"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if focus_result.returncode != 0:
                    continue

                time.sleep(0.5)
                visible_after = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--name", window_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    check=False,
                )
                visible_window_ids = {
                    visible_window_id.strip()
                    for visible_window_id in visible_after.stdout.splitlines()
                    if visible_window_id.strip()
                }
                if window_id not in visible_window_ids:
                    return True

        return False
