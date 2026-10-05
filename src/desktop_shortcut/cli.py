from __future__ import annotations

import argparse
import sys

from . import __version__
from .core import (
    create_shortcut,
    discover,
    find_by_id,
    install_gnome_extension,
    install_user_service,
    remove_shortcut,
    scan,
    search,
    user_extensions_disabled,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="desktop-shortcut",
        description="为 Ubuntu 应用创建和维护桌面快捷方式",
    )
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="列出已安装应用")
    find = commands.add_parser("search", help="搜索已安装应用")
    find.add_argument("query")
    create = commands.add_parser("create", help="创建匹配应用的快捷方式")
    create.add_argument("query")
    create.add_argument("--all", action="store_true", help="为全部匹配项创建")
    create.add_argument("--id", action="store_true", help=argparse.SUPPRESS)
    remove = commands.add_parser("remove", help="删除本工具创建的快捷方式")
    remove.add_argument("query")
    remove.add_argument("--all", action="store_true", help="删除全部匹配项")
    commands.add_parser("scan", help="扫描并同步新安装/更新的应用")
    commands.add_parser("enable-auto", help="启用登录后自动扫描")
    commands.add_parser("install-menu", help="安装应用抽屉右键菜单扩展")
    return result


def _print_apps(apps) -> None:
    for app in apps:
        print(f"{app.app_id}\t{app.name}\t{app.source}")


def _select(query: str, all_matches: bool):
    matches = search(query)
    if not matches:
        print(f"没有找到应用：{query}", file=sys.stderr)
        raise SystemExit(2)
    if len(matches) > 1 and not all_matches:
        print("匹配到多个应用，请使用更精确的名称，或添加 --all：", file=sys.stderr)
        _print_apps(matches)
        raise SystemExit(2)
    return matches


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "list":
        _print_apps(discover())
    elif args.command == "search":
        _print_apps(search(args.query))
    elif args.command == "create":
        if args.id:
            app = find_by_id(args.query)
            if not app:
                print(f"没有找到应用 ID：{args.query}", file=sys.stderr)
                return 2
            matches = [app]
        else:
            matches = _select(args.query, args.all)
        for app in matches:
            print(create_shortcut(app))
    elif args.command == "remove":
        for app in _select(args.query, args.all):
            if remove_shortcut(app):
                print(f"已删除：{app.name}")
    elif args.command == "scan":
        created, updated = scan()
        print(f"新建 {len(created)} 个，更新 {len(updated)} 个快捷方式")
    elif args.command == "enable-auto":
        install_user_service()
        print("已启用自动扫描；新安装的软件将在一分钟内出现在桌面。")
    elif args.command == "install-menu":
        location = install_gnome_extension()
        print(f"扩展已安装到：{location}")
        if user_extensions_disabled():
            print(
                "警告：GNOME 当前禁用了所有用户扩展。请执行：\n"
                "gsettings set org.gnome.shell disable-user-extensions false"
            )
        print(
            "请注销并重新登录，然后执行："
            "gnome-extensions enable "
            "desktop-shortcut@hearotop.github.io"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
