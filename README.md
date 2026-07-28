# Desktop Shortcut

一个面向 Ubuntu/GNOME 的轻量桌面快捷方式管理工具。它读取标准
Freedesktop `.desktop` 文件，因此同时支持 APT、Snap、Flatpak 以及用户手动安装的应用。

## 功能

- 搜索并为已安装软件创建桌面快捷方式
- 后台发现新安装的软件并自动创建快捷方式
- 软件入口更新后同步刷新桌面副本
- 支持中文“桌面”目录和自定义 XDG Desktop 目录
- 使用 `gio` 标记 GNOME 启动器为可信，并设置可执行权限

## 安装与使用

```bash
# Ubuntu 推荐方式：pipx 会为本应用自动管理独立虚拟环境
sudo apt install pipx
pipx ensurepath
pipx install .

# 重新打开终端后查看或搜索应用
desktop-shortcut list
desktop-shortcut search firefox

# 给已有软件创建快捷方式
desktop-shortcut create firefox

# 启用自动创建（每分钟检查一次）
desktop-shortcut enable-auto
```

如果刚执行 `pipx ensurepath`，但不想重新打开终端，可以先运行：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

不要使用 `sudo pip` 或 `--break-system-packages`；这会绕过 Ubuntu 的 Python
环境保护机制。

开发时也可以手动创建项目虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

虚拟环境安装后可直接执行 `.venv/bin/desktop-shortcut`。不过用于长期后台运行时，
`pipx` 管理的位置更稳定。

## 应用抽屉右键菜单

GNOME Shell 50 用户可安装配套扩展：

```bash
pipx reinstall desktop-shortcut
desktop-shortcut install-menu
```

然后注销并重新登录。登录后若扩展尚未自动启用，执行：

```bash
gnome-extensions enable desktop-shortcut@hearotop.github.io
```

此后在应用抽屉中右击应用，即可选择“添加到桌面”。GNOME Wayland 会话不能通过
`Alt+F2`、`r` 重启 Shell，因此安装扩展后必须注销登录一次。

GNOME 扩展部分是独立的纯 GJS 实现，运行时不依赖 Python。生成可上传至
extensions.gnome.org 的投稿包：

```bash
make pack-extension
```

若一个关键词匹配多个应用，命令会列出候选项；请使用更精确的应用 ID，或显式添加
`--all`。

启用自动模式时会先记录当前已有软件，不会一次性把全部应用堆到桌面；之后新安装的
应用才会自动出现。已有软件请使用 `desktop-shortcut create <名称或ID>` 按需创建。

## 配置

创建 `~/.config/desktop-shortcut/config.json`：

```json
{
  "auto_create": true,
  "exclude": ["org.gnome.Settings", "org.gnome.Software"]
}
```

`exclude` 使用 `desktop-shortcut list` 输出的第一列应用 ID。

## 设计说明

自动模式使用用户级 systemd timer，不需要 root 权限，也不会向系统软件包中注入安装脚本。
软件商店和包管理器安装完成后都会生成标准应用入口，下一次扫描会复制到当前用户的桌面。
桌面环境出于安全考虑可能仍会在首次启动时显示确认提示。

## 开发

```bash
python3 -m unittest discover -s tests -v
```
