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
    update_icon,
    user_extensions_disabled,
)


def parser() -> argparse.ArgumentParser:
    """构建并返回 CLI 参数解析器。"""
    result = argparse.ArgumentParser(
        prog="gaqu",
        description="GNOME application quick update",
    )
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("ls", help="列出已安装应用")
    find = commands.add_parser("find", help="搜索已安装应用")
    find.add_argument("query")
    create = commands.add_parser("add", help="创建匹配应用的快捷方式")
    create.add_argument("query")
    create.add_argument("--all", action="store_true", help="为全部匹配项创建")
    create.add_argument("--id", action="store_true", help=argparse.SUPPRESS)
    remove = commands.add_parser("rm", help="删除本工具创建的快捷方式")
    remove.add_argument("query")
    remove.add_argument("--all", action="store_true", help="删除全部匹配项")
    commands.add_parser("sync", help="扫描并同步新安装/更新的应用")
    update = commands.add_parser("icon", help="更新快捷方式图标")
    update.add_argument("desktop_path", help=".desktop 文件路径")
    update.add_argument("icon_source_path", help="新的图标文件路径")
    commands.add_parser("auto", help="启用登录后自动扫描")
    commands.add_parser("install", help="安装应用抽屉右键菜单扩展")

    return result


def _print_apps(apps) -> None:
    """以制表符分隔的格式打印应用列表。"""
    for app in apps:
        print(f"{app.app_id}\t{app.name}\t{app.source}")


def _select(query: str, all_matches: bool):
    """搜索并选中应用；未匹配或匹配过多时打印提示后退出。"""
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
    """CLI 入口：解析参数并分发到各子命令。"""
    args = parser().parse_args(argv)
    if args.command == "ls":
        _print_apps(discover())
    elif args.command == "find":
        _print_apps(search(args.query))
    elif args.command == "add":
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
    elif args.command == "rm":
        for app in _select(args.query, args.all):
            if remove_shortcut(app):
                print(f"已删除：{app.name}")
    elif args.command == "sync":
        created, updated = scan()
        print(f"新建 {len(created)} 个，更新 {len(updated)} 个快捷方式")
    elif args.command == "icon":
        update_icon(args.desktop_path, args.icon_source_path)
    elif args.command == "auto":
        install_user_service()
        print("已启用自动扫描；新安装的软件将在一分钟内出现在桌面。")
    elif args.command == "install":
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
            "gaqu"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
