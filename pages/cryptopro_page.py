from locators.cryptopro_locators import CryptoProLocators
from playwright.sync_api import Error as PlaywrightError
from locators.cryptopro_locators import URL
from tools.pdf_pades_signer import sign_pdf_with_cryptopro
from pages.base_page import Base
from pathlib import Path
import subprocess
import requests
import random
import pytest
import shutil
import time
import os

class CryptoPro(Base):
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    REPORTS_DIR = PROJECT_ROOT / "reports"
    SOURCE_PDF = PROJECT_ROOT / "files" / "test.pdf"
    SIGNED_PDF = REPORTS_DIR / "test_signed.pdf"
    SIGNATURE_SCREENSHOT = REPORTS_DIR / "test_signed.png"

    CERT_SOURCE = Path("/tmp/certnew.cer")
    CERT_TARGET = Path("/usr/local/share/ca-certificates/certnew.crt")
    CERTMGR = Path("/opt/cprocsp/bin/amd64/certmgr")

    CRYPTOPRO_WINDOW_NAME = "CryptoPro CSP"
    ENTROPY_AREA = (760, 1150, 500, 620)
    ENTROPY_MAX_WIDTH = 620
    ENTROPY_MAX_HEIGHT = 370

    def create_test_certificate(self):
        """Generate a CryptoPro test CA signing certificate."""
        try:
            self.install_cryptopro_uc_root_certificate()
            self.go_to_site(URL.CRYPTOPRO_URL)
            self.click(CryptoProLocators.CERTRQMA_ASP_LINK)
            self.confirm_system_dialog(coord_set=1)
            self.fill_input(
                CryptoProLocators.IDENTIFICATION_INFO_CERTIFICATE_NAME_FIELD,
                CryptoProLocators.CERTIFICATE_NAME,
            )
            self.check(CryptoProLocators.ACTIVE_FUNCTION_EXPORT_CHECK)
            self.click(CryptoProLocators.ISSUE_BUTTON)
            self.generate_entropy()
            self.wait(1000)
            self.wait_for_selector(CryptoProLocators.INSTALL_CERT, timeout=30000)
            self.click(CryptoProLocators.INSTALL_CERT)
            self.wait(2000)
            self.confirm_system_dialog(coord_set=1)
            self.wait(2000)
            result = self.get_by_text(CryptoProLocators.NEW_CERT_INSTALLED, exact=True)
            result.wait_for(state="visible", timeout=30000)
            return result.inner_text()
        except Exception as e:
            pytest.fail(f"CryptoPro certificates were not installed: {e}")

    def sign(self):
        """Sign the PDF with the generated test certificate."""
        try:
            artifacts = sign_pdf_with_cryptopro(
                self.SOURCE_PDF,
                self.SIGNED_PDF,
                certificate_name=CryptoProLocators.CERTIFICATE_NAME,
            )

            self.page.goto(self.SIGNED_PDF.as_uri(), wait_until="domcontentloaded")
            self.wait(3000)
            self.page.screenshot(path=str(self.SIGNATURE_SCREENSHOT), full_page=True)

            return {
                "signed_pdf": artifacts.signed_pdf,
                "cms_signature": artifacts.cms_signature,
                "screenshot": self.SIGNATURE_SCREENSHOT,
                "signer": artifacts.signer,
            }
        except Exception as e:
            pytest.fail(f"PDF was not signed with the CryptoPro test certificate: {e}")

    def install_cryptopro_uc_root_certificate(self):
        """Download and install the CryptoPro test CA root certificate."""
        self._download_cryptopro_uc_certificate()
        self._install_system_root_certificate()
        self._install_cryptopro_root_certificate()
        return self

    def generate_entropy(self, clicks=1200, wiggle_interval=5, batch_size=20):
        """Generate entropy through X11 events."""
        if clicks <= 0:
            return self

        env = self._x11_env()
        self.wait(1000)

        x_min, x_max, y_min, y_max = self.ENTROPY_AREA
        entropy_x = (x_min + x_max) // 2
        entropy_y = (y_min + y_max) // 2
        entropy_window_id = self._wait_for_entropy_window(env, entropy_x, entropy_y)

        if not entropy_window_id:
            return self

        commands = []
        batch_size = max(1, int(batch_size))

        for click_number in range(clicks):
            if not self._is_cryptopro_window_visible(entropy_window_id, env):
                entropy_window_id = self._wait_for_entropy_window(env, entropy_x, entropy_y, timeout=5000)
                if not entropy_window_id:
                    self.confirm_system_dialog(coord_set=2)
                    if not self._wait_for_password_window_closed(env):
                        for window_id in self._get_password_window_ids(env):
                            subprocess.run(
                                ["xdotool", "windowfocus", "--sync", str(window_id), "key", "Return"],
                                env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                check=False,
                            )
                            if self._wait_for_password_window_closed(env, timeout=1000):
                                break
                    return self

            commands.extend(self._entropy_click_commands(x_min, x_max, y_min, y_max, click_number, wiggle_interval))

            if (click_number + 1) % batch_size == 0:
                if commands:
                    subprocess.run(
                        ["xdotool", *commands],
                        check=True,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=30,
                    )
                commands.clear()

        if commands:
            subprocess.run(
                ["xdotool", *commands],
                check=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

        if not self._wait_for_entropy_window(env, entropy_x, entropy_y, timeout=5000):
            self.confirm_system_dialog(coord_set=2)
            if not self._wait_for_password_window_closed(env):
                for window_id in self._get_password_window_ids(env):
                    subprocess.run(
                        ["xdotool", "windowfocus", "--sync", str(window_id), "key", "Return"],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    if self._wait_for_password_window_closed(env, timeout=1000):
                        break

        return self

    def _download_cryptopro_uc_certificate(self):
        try:
            with self.page.expect_download(timeout=15000) as download_info:
                self.go_to_site(URL.CRYPTOPRO_UC_URL)
            download_info.value.save_as(str(self.CERT_SOURCE))
        except PlaywrightError:
            response = requests.get(URL.CRYPTOPRO_UC_URL, timeout=30000, verify=False)
            response.raise_for_status()
            self.CERT_SOURCE.write_bytes(response.content)

    def _install_system_root_certificate(self):
        self.CERT_TARGET.parent.mkdir(parents=True, exist_ok=True)

        if self._is_der_certificate(self.CERT_SOURCE):
            subprocess.run(
                [
                    "openssl", "x509", "-inform", "DER",
                    "-in", str(self.CERT_SOURCE),
                    "-out", str(self.CERT_TARGET),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            shutil.copyfile(self.CERT_SOURCE, self.CERT_TARGET)

        self.CERT_SOURCE.unlink(missing_ok=True)
        subprocess.run(
            ["update-ca-certificates", "--fresh"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _install_cryptopro_root_certificate(self):
        if not self.CERTMGR.exists():
            return

        with subprocess.Popen(
                [str(self.CERTMGR), "-inst", "-store", "uRoot", "-file", str(self.CERT_TARGET)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
        ) as process:
            self.confirm_system_dialog(coord_set=3)
            try:
                process.communicate(input="o\n", timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()

    def _wait_for_password_window_closed(self, env, timeout=5000):
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            if not self._get_password_window_ids(env):
                return True
            time.sleep(0.2)
        return False

    def _wait_for_entropy_window(self, env, x, y, timeout=10000):
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            window_id = self._get_cryptopro_window_id_at_point(env, x, y)
            if window_id:
                return window_id
            time.sleep(0.2)
        return None

    def _get_cryptopro_window_id_at_point(self, env, x, y):
        for window_id in self._get_cryptopro_window_ids(env):
            geometry = self._get_window_geometry(env, window_id)
            if geometry and self._is_entropy_window_geometry(geometry):
                if geometry["X"] <= x <= geometry["X"] + geometry["WIDTH"]:
                    if geometry["Y"] <= y <= geometry["Y"] + geometry["HEIGHT"]:
                        return window_id
        return None

    def _get_password_window_ids(self, env):
        return [
            window_id
            for window_id in self._get_cryptopro_window_ids(env)
            if (geometry := self._get_window_geometry(env, window_id))
               and not self._is_entropy_window_geometry(geometry)
        ]

    def _get_cryptopro_window_ids(self, env):
        result = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--name", self.CRYPTOPRO_WINDOW_NAME],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return result.stdout.split()

    def _get_window_geometry(self, env, window_id):
        result = subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", str(window_id)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None

        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        keys = {"X", "Y", "WIDTH", "HEIGHT"}
        if not keys <= values.keys():
            return None

        return {key: int(values[key]) for key in keys}

    def _is_cryptopro_window_visible(self, window_id, env):
        if str(window_id) not in self._get_cryptopro_window_ids(env):
            return False

        geometry = self._get_window_geometry(env, window_id)
        return bool(geometry and self._is_entropy_window_geometry(geometry))

    def _entropy_click_commands(self, x_min, x_max, y_min, y_max, click_number, wiggle_interval):
        commands = []
        x = random.randint(x_min, x_max)
        y = random.randint(y_min, y_max)

        for _ in range(random.randint(2, 5)):
            commands.extend([
                "mousemove",
                str(random.randint(x_min, x_max)),
                str(random.randint(y_min, y_max)),
                "sleep",
                "0.01",
            ])

        if click_number and click_number % wiggle_interval == 0:
            for _ in range(random.randint(4, 8)):
                x = max(x_min, min(x_max, x + random.randint(-60, 60)))
                y = max(y_min, min(y_max, y + random.randint(-20, 20)))
                commands.extend(["mousemove", str(x), str(y), "sleep", "0.01"])

        commands.extend(["mousemove", str(x), str(y), "sleep", "0.01", "click", "1", "sleep", "0.02"])
        return commands

    def _x11_env(self):
        env = os.environ.copy()
        env["DISPLAY"] = env.get("DISPLAY") or ":99"
        os.environ["DISPLAY"] = env["DISPLAY"]
        return env

    def _is_entropy_window_geometry(self, geometry):
        return (
                geometry["WIDTH"] <= self.ENTROPY_MAX_WIDTH
                and geometry["HEIGHT"] <= self.ENTROPY_MAX_HEIGHT
        )

    @staticmethod
    def _is_der_certificate(cert_source: Path):
        result = subprocess.run(
            ["file", str(cert_source)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return "DER" in result.stdout
