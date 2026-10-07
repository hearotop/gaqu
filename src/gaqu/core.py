"""GAQU 核心逻辑：应用发现、快捷方式管理、图标更新与自动同步。"""

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

# 系统级应用条目目录（.desktop 文件所在位置）
APP_DIRS = (
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
)


@dataclass(frozen=True)
class Application:
    """一个已安装应用的 .desktop 条目信息。"""

    app_id: str        # 条目 ID（文件名去掉 .desktop 后缀）
    name: str          # 本地化的应用名称
    source: Path       # .desktop 文件路径
    comment: str = ""  # 应用描述
    icon: str = ""     # 图标名


def data_home() -> Path:
    """XDG 数据目录，默认 ~/.local/share。"""
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def config_home() -> Path:
    """XDG 配置目录，默认 ~/.config。"""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def state_home() -> Path:
    """XDG 状态目录，默认 ~/.local/state。"""
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))


def application_dirs() -> tuple[Path, ...]:
    """所有可能存放应用条目的目录（用户目录优先，即 XDG 覆盖规则）。"""
    dirs = [data_home() / "applications", *APP_DIRS]
    snap = Path("/var/lib/snapd/desktop/applications")
    flatpak_system = Path("/var/lib/flatpak/exports/share/applications")
    flatpak_user = data_home() / "flatpak/exports/share/applications"
    dirs.extend((snap, flatpak_system, flatpak_user))
    return tuple(dirs)


def update_icon(desktop_path: str, icon_source_path: str):
    """
    更新指定 .desktop 文件的 Icon 路径，并将新的图标文件移动至用户本地图标目录。

    :param desktop_path: .desktop 文件的完整路径 (如 /home/hearo/.local/share/applications/xxx.desktop)
    :param icon_source_path: 用户上传的待移动图标路径 (如 /tmp/x.svg)
    """
    # 1. 确定目标图标存放路径
    user_home = os.path.expanduser("~")
    target_icon_dir = os.path.join(user_home, ".local/share/icons/hicolor/scalable/apps")

    # 确保目标文件夹存在
    os.makedirs(target_icon_dir, exist_ok=True)

    # 获取图标文件名并拼接最终保存路径
    icon_name = os.path.basename(icon_source_path)
    target_icon_path = os.path.join(target_icon_dir, icon_name)

    # 移动/覆盖图标文件到目标路径
    shutil.move(icon_source_path, target_icon_path)
    print(f"[+] 图标已保存至: {target_icon_path}")

    # 2. 读取并更新 .desktop 文件内容
    if not os.path.exists(desktop_path):
        raise FileNotFoundError(f"未找到指定的桌面文件: {desktop_path}")

    with open(desktop_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    icon_updated = False
    new_lines = []

    for line in lines:
        # 更新或替代 Icon= 行
        if line.startswith("Icon="):
            new_lines.append(f"Icon={target_icon_path}\n")
            icon_updated = True
        # 如果存在 NoDisplay=true，顺手修正为 false，避免图标隐形/显示为齿轮
        elif line.startswith("NoDisplay="):
            new_lines.append("NoDisplay=false\n")
        else:
            new_lines.append(line)

    # 如果原文件中没有 Icon= 字段，则追加到末尾
    if not icon_updated:
        new_lines.append(f"Icon={target_icon_path}\n")

    # 写回 .desktop 文件
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"[+] 快捷方式已更新: {desktop_path}")

    # 3. 刷新系统图标缓存与桌面数据库 (保证 Wayland 环境下即时生效)
    try:
        subprocess.run(["gtk-update-icon-cache", "-f", "-t", os.path.join(user_home, ".local/share/icons/hicolor")],
                       check=False)
        subprocess.run(["update-desktop-database", os.path.join(user_home, ".local/share/applications")], check=False)
        print("[+] 桌面与图标数据库刷新完毕！")
    except Exception as e:
        print(f"[-] 刷新缓存时发生警告（可忽略）: {e}")

def desktop_dir() -> Path:
    """解析用户桌面目录（支持中文本地化目录，如 ~/桌面），回退 ~/Desktop。"""
    config = config_home() / "user-dirs.dirs"
    if config.exists():
        for line in config.read_text(errors="replace").splitlines():
            match = re.match(r'XDG_DESKTOP_DIR="(.+)"', line)
            if match:
                raw = match.group(1).replace("$HOME", str(Path.home()))
                return Path(os.path.expandvars(raw)).expanduser()
    return Path.home() / "Desktop"


def _localized(section: configparser.SectionProxy, key: str) -> str:
    """按当前系统语言取条目中本地化的字段值，如 Name[zh_CN]。"""
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
    """解析单个 .desktop 文件；非应用、隐藏或无可执行命令的返回 None。"""
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
    """扫描所有应用目录，返回去重后的应用列表（按名称排序）。

    靠前的目录优先（XDG 覆盖规则）：用户目录里的同 ID 条目会
    覆盖系统目录里的条目。
    """
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
    """按关键词模糊搜索应用（匹配名称、ID、描述，支持多关键词）。"""
    terms = query.casefold().split()
    candidates = apps if apps is not None else discover()
    return [
        app
        for app in candidates
        if all(term in f"{app.name} {app.app_id} {app.comment}".casefold() for term in terms)
    ]


def find_by_id(app_id: str) -> Application | None:
    """按条目 ID 精确查找应用。"""
    normalized = app_id.removesuffix(".desktop")
    return next((app for app in discover() if app.app_id == normalized), None)


def destination_for(app: Application) -> Path:
    """计算某个应用的桌面快捷方式目标路径（ID 中的非法字符替换为 -）。"""
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", app.app_id)
    return desktop_dir() / f"{safe_id}.desktop"


def create_shortcut(app: Application, overwrite: bool = True) -> Path:
    """把应用的 .desktop 条目复制到桌面，赋可执行权限并打上信任标记。"""
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
    """删除桌面快捷方式，返回是否真的删掉了。"""
    target = destination_for(app)
    if target.exists():
        target.unlink()
        return True
    return False


def fingerprint(app: Application) -> str:
    """计算条目指纹（路径+修改时间+大小的哈希），用于检测应用更新。"""
    stat = app.source.stat()
    value = f"{app.source}\0{stat.st_mtime_ns}\0{stat.st_size}".encode()
    return hashlib.sha256(value).hexdigest()


def save_current_state() -> Path:
    """记录当前已安装应用的指纹基线，不创建任何快捷方式。"""
    state_path = state_home() / "gaqu/apps.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    current = {app.app_id: fingerprint(app) for app in discover()}
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(state_path)
    return state_path


def load_config() -> dict:
    """读取 ~/.config/gaqu/config.json，缺省值 auto_create=True、exclude=[]。"""
    path = config_home() / "gaqu/config.json"
    defaults = {"auto_create": True, "exclude": []}
    try:
        value = json.loads(path.read_text())
        defaults.update(value)
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def scan() -> tuple[list[Path], list[Path]]:
    """对比指纹基线：为新装应用创建快捷方式、为更新过的应用刷新快捷方式。

    返回 (新建列表, 更新列表)。
    """
    cfg = load_config()
    if not cfg.get("auto_create", True):
        return [], []
    state_path = state_home() / "gaqu/apps.json"
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
    """安装并启用用户级 systemd 定时器，实现登录后自动扫描新应用。"""
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
            f"{sys.executable} -m gaqu.cli",
        )
        target.write_text(content)
        written.append(target)
    # 先记录基线，避免启用自动同步时把已装应用全部铺到桌面
    save_current_state()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "gaqu.timer"],
        check=True,
    )
    return written


def install_gnome_extension() -> Path:
    """安装 GNOME 扩展：复制 extension.js/metadata.json、编译 po 为 mo 并启用。"""
    uuid = "gaqu"
    domain = uuid
    source_dir = Path(__file__).parent / "gnome-extension"
    # Snap 版 IDE 会为集成终端覆盖 XDG_DATA_HOME，但 GNOME Shell 不读那个
    # 沙箱目录；用户扩展必须装到真实主目录下
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
        ["gnome-extensions", "disable", "gaqu@local"],
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
