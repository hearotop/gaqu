from __future__ import annotations

import configparser
import hashlib
import json
import locale
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

APP_DIRS = (
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
)


@dataclass(frozen=True)
class Application:
    app_id: str
    name: str
    source: Path
    comment: str = ""


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))


def application_dirs() -> tuple[Path, ...]:
    dirs = [data_home() / "applications", *APP_DIRS]
    snap = Path("/var/lib/snapd/desktop/applications")
    flatpak_system = Path("/var/lib/flatpak/exports/share/applications")
    flatpak_user = data_home() / "flatpak/exports/share/applications"
    dirs.extend((snap, flatpak_system, flatpak_user))
    return tuple(dirs)


def desktop_dir() -> Path:
    config = config_home() / "user-dirs.dirs"
    if config.exists():
        for line in config.read_text(errors="replace").splitlines():
            match = re.match(r'XDG_DESKTOP_DIR="(.+)"', line)
            if match:
                raw = match.group(1).replace("$HOME", str(Path.home()))
                return Path(os.path.expandvars(raw)).expanduser()
    return Path.home() / "Desktop"


def _localized(section: configparser.SectionProxy, key: str) -> str:
    language = (locale.getlocale()[0] or "").replace("-", "_")
    candidates = []
    if language:
        candidates.extend((f"{key}[{language}]", f"{key}[{language.split('_')[0]}]"))
    candidates.append(key)
    for candidate in candidates:
        if section.get(candidate):
            return section[candidate].strip()
    return ""


def read_application(path: Path) -> Application | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
        entry = parser["Desktop Entry"]
    except (OSError, UnicodeError, KeyError, configparser.Error):
        return None
    if entry.get("Type", "Application") != "Application":
        return None
    if entry.get("NoDisplay", "false").lower() == "true":
        return None
    if entry.get("Hidden", "false").lower() == "true":
        return None
    if not entry.get("Exec"):
        return None
    name = _localized(entry, "Name") or path.stem
    return Application(path.stem, name, path, _localized(entry, "Comment"))


def discover() -> list[Application]:
    # Earlier directories follow the XDG override rule.
    found: dict[str, Application] = {}
    for directory in application_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.desktop")):
            if path.stem in found:
                continue
            app = read_application(path)
            if app:
                found[app.app_id] = app
    return sorted(found.values(), key=lambda app: (app.name.casefold(), app.app_id))


def search(query: str, apps: Iterable[Application] | None = None) -> list[Application]:
    terms = query.casefold().split()
    candidates = apps if apps is not None else discover()
    return [
        app
        for app in candidates
        if all(term in f"{app.name} {app.app_id} {app.comment}".casefold() for term in terms)
    ]


def find_by_id(app_id: str) -> Application | None:
    normalized = app_id.removesuffix(".desktop")
    return next((app for app in discover() if app.app_id == normalized), None)


def destination_for(app: Application) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", app.app_id)
    return desktop_dir() / f"{safe_id}.desktop"


def create_shortcut(app: Application, overwrite: bool = True) -> Path:
    target = destination_for(app)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    content = app.source.read_bytes()
    temporary = target.with_suffix(".desktop.tmp")
    temporary.write_bytes(content)
    temporary.chmod(0o755)
    temporary.replace(target)
    try:
        subprocess.run(
            ["gio", "set", str(target), "metadata::trusted", "true"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass
    return target


def remove_shortcut(app: Application) -> bool:
    target = destination_for(app)
    if target.exists():
        target.unlink()
        return True
    return False


def fingerprint(app: Application) -> str:
    stat = app.source.stat()
    value = f"{app.source}\0{stat.st_mtime_ns}\0{stat.st_size}".encode()
    return hashlib.sha256(value).hexdigest()


def save_current_state() -> Path:
    """Record installed applications without creating shortcuts."""
    state_path = state_home() / "desktop-shortcut/apps.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    current = {app.app_id: fingerprint(app) for app in discover()}
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(state_path)
    return state_path


def load_config() -> dict:
    path = config_home() / "desktop-shortcut/config.json"
    defaults = {"auto_create": True, "exclude": []}
    try:
        value = json.loads(path.read_text())
        defaults.update(value)
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def scan() -> tuple[list[Path], list[Path]]:
    """Create new shortcuts and refresh changed ones; return (created, updated)."""
    cfg = load_config()
    if not cfg.get("auto_create", True):
        return [], []
    state_path = state_home() / "desktop-shortcut/apps.json"
    try:
        old_state = json.loads(state_path.read_text())
    except (OSError, ValueError, TypeError):
        old_state = {}
    excluded = set(cfg.get("exclude", []))
    new_state: dict[str, str] = {}
    created: list[Path] = []
    updated: list[Path] = []
    for app in discover():
        mark = fingerprint(app)
        new_state[app.app_id] = mark
        if app.app_id in excluded:
            continue
        target = destination_for(app)
        if app.app_id not in old_state:
            create_shortcut(app)
            created.append(target)
        elif target.exists() and old_state.get(app.app_id) != mark:
            create_shortcut(app)
            updated.append(target)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(state_path)
    return created, updated


def install_user_service() -> list[Path]:
    source_dir = Path(__file__).parent / "systemd"
    unit_dir = config_home() / "systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for source in source_dir.glob("*"):
        if source.suffix not in {".service", ".timer"}:
            continue
        target = unit_dir / source.name
        content = source.read_text().replace(
            "@EXECUTABLE@",
            f"{sys.executable} -m desktop_shortcut.cli",
        )
        target.write_text(content)
        written.append(target)
    # Establish a baseline so enabling automation does not flood the desktop
    # with every application that was already installed.
    save_current_state()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "desktop-shortcut.timer"],
        check=True,
    )
    return written


def install_gnome_extension() -> Path:
    uuid = "desktop-shortcut@hearotop.github.io"
    domain = uuid
    source_dir = Path(__file__).parent / "gnome-extension"
    # IDEs installed through Snap override XDG_DATA_HOME for their integrated
    # terminals. GNOME Shell does not inspect that sandbox-specific directory;
    # user extensions always need to be installed in the real home directory.
    extension_dir = (
        Path.home() / ".local/share/gnome-shell/extensions" / uuid
    )
    extension_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("extension.js", "metadata.json"):
        source = source_dir / filename
        (extension_dir / filename).write_bytes(source.read_bytes())
    for po_file in (source_dir / "po").glob("*.po"):
        language = po_file.stem
        target = (
            extension_dir / "locale" / language /
            "LC_MESSAGES" / f"{domain}.mo"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        msgfmt = shutil.which("msgfmt")
        if msgfmt:
            command = [msgfmt, str(po_file), "--output-file", str(target)]
        else:
            command = [
                "pybabel", "compile",
                "--input-file", str(po_file),
                "--output-file", str(target),
            ]
        subprocess.run(command, check=True)
    subprocess.run(
        ["gnome-extensions", "disable", "desktop-shortcut@local"],
        check=False,
    )
    subprocess.run(["gnome-extensions", "enable", uuid], check=False)
    return extension_dir


def user_extensions_disabled() -> bool:
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.shell", "disable-user-extensions"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return result.stdout.strip().lower() == "true"
