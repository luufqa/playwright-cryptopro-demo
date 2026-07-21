from playwright.sync_api import sync_playwright
from pathlib import Path
import tempfile
import platform
import pytest
import shutil
import os



EXTENSION_ID = "iifchhfnnmpdbibifmljnfjhpififfog"
PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"
QA_DASHBOARD_REPORT = REPORTS_DIR / "report.html"


def get_browser_and_extension_paths():
    project_root = Path(__file__).resolve().parent
    tools_dir = project_root / "tools"
    extensions_dir = tools_dir / "extensions" / EXTENSION_ID
    system = platform.system()

    if system == "Darwin":  # macOS
        browser_candidates = [
            Path(os.environ["CHROMIUM_GOST_PATH"]) if os.environ.get("CHROMIUM_GOST_PATH") else None,
            Path("/Applications/Chromium-Gost.app/Contents/MacOS/Chromium-Gost"),
            Path.home() / "Applications" / "Chromium-Gost.app" / "Contents" / "MacOS" / "Chromium-Gost",
            tools_dir / "chromium-gost-mac" / "Chromium-Gost.app" / "Contents" / "MacOS" / "Chromium-Gost",
        ]
        browser_path = next((path for path in browser_candidates if path and path.exists()), None)
        if browser_path is None:
            checked_paths = "\n".join(str(path) for path in browser_candidates if path)
            raise FileNotFoundError(f"Chromium-Gost was not found. Checked paths:\n{checked_paths}")

        extension_path = None
        if extensions_dir.exists():
            version_dirs = sorted([path for path in extensions_dir.iterdir() if path.is_dir()])
            if version_dirs:
                latest_extension_path = version_dirs[-1]
                if (latest_extension_path / "manifest.json").exists():
                    extension_path = latest_extension_path

        return str(browser_path), str(extension_path) if extension_path else None

    elif system == "Windows":
        browser_path = Path.home() / "AppData" / "Local" / "Chromium" / "Application" / "chrome.exe"
        extension_path = None
        if extensions_dir.exists():
            version_dirs = sorted([path for path in extensions_dir.iterdir() if path.is_dir()])
            if version_dirs:
                extension_path = version_dirs[-1]
        return str(browser_path), str(extension_path) if extension_path else None

    elif system == "Linux":
        browser_path = shutil.which("chromium-gost")
        if browser_path is None:
            raise FileNotFoundError(
                "chromium-gost was not found in PATH. "
                "Check that the image is built FROM docker.io/luufqa/debian-cryptopro:latest."
            )
        return browser_path, None
    else:
        raise RuntimeError(f"OS {system} is not supported")


def create_browser_context(playwright_instance):
    browser_path, extension_path = get_browser_and_extension_paths()
    user_data_dir = tempfile.mkdtemp(prefix="hr-tests-profile-")

    args = [
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--window-position=0,0",
        "--disable-gpu",
        "--no-sandbox"
    ]

    if extension_path is not None:
        args.extend([
            f"--disable-extensions-except={extension_path}",
            f"--load-extension={extension_path}",
        ])

    context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path=browser_path,
        headless=False,
        args=args,
        viewport={"width": 1920, "height": 1080},
        accept_downloads=True,
        ignore_https_errors=True,
        bypass_csp=True,
        java_script_enabled=True,
        ignore_default_args=[
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--enable-automation"
        ]
    )

    return context, user_data_dir


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p


@pytest.fixture
def browser_context(playwright_instance):
    context, user_data_dir = create_browser_context(playwright_instance)
    yield context
    context.close()
    shutil.rmtree(user_data_dir, ignore_errors=True)


@pytest.fixture
def context(browser_context):
    return browser_context


@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    page.set_default_timeout(10000)
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(window, 'chrome', { get: () => undefined });
        Object.defineProperty(window, 'csi', { get: () => undefined });
    """)
    yield page
    page.close()


def pytest_collection_modifyitems(items):
    items.sort(key=lambda x: (
        x.get_closest_marker("order").args[0]
        if x.get_closest_marker("order")
        else float('inf')
    ))


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    if call.when == 'setup':
        doc = item.function.__doc__ or ''
        if hasattr(item, 'callspec'):
            params = item.callspec.params
            doc = doc.format(**params)
        item._report_description = doc.strip()
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call':
        setattr(rep, 'description', getattr(item, '_report_description', ''))


def pytest_html_results_table_header(cells):
    cells.insert(2, '<th>Description</th>')


def pytest_html_results_table_row(report, cells):
    description = getattr(report, 'description', '')
    cells.insert(2, f'<td class="col-description">{description}</td>')


def pytest_sessionstart(session):
    REPORTS_DIR.mkdir(exist_ok=True)
    for path in REPORTS_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def pytest_unconfigure(config):
    html_path = Path(getattr(config.option, "htmlpath", "") or REPORTS_DIR / "report.html")
    if not html_path.is_absolute():
        html_path = PROJECT_ROOT / html_path
    if not html_path.exists():
        return

    from tools.generate_report import generate_dashboard

    generate_dashboard(html_path, QA_DASHBOARD_REPORT)
