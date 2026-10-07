
# GAQU

为GNOME 应用菜单增加“添加到桌面快捷方式”和自定义图标功能，并提供可选的 Python
命令行工具，用于搜索应用、创建快捷方式和自动同步新安装的软件。

## 功能

- 在应用抽屉右键菜单中显示“添加到桌面”
- 支持 APT、Snap、Flatpak 和用户安装的应用
- 自动识别本地化或自定义的 XDG 桌面目录
- 设置启动器可执行权限和 GNOME 信任标记
- 英文界面及简体中文翻译
- 可选的 Python CLI 和用户级 systemd 自动同步服务

## 安装

推荐用 `pipx` 安装 CLI，再由 CLI 一键安装扩展（Ubuntu 遵循 PEP 668，请勿使用
`sudo pip` 或 `--break-system-packages`）：

```bash
sudo apt install pipx
pipx ensurepath
pipx install .

# 安装 GNOME 扩展（复制扩展文件、编译翻译并启用）
gaqu install
```

不要在 Snap 版 VS Code 的集成终端中执行 `gaqu install`，因为它可能覆盖
`XDG_DATA_HOME`，导致扩展装到错误位置。推荐使用 GNOME Terminal。

Wayland 会话安装后需要注销并重新登录，扩展才会被 GNOME Shell 加载。重新登录后
确认状态：

```bash
gnome-extensions info gaqu
```

状态应显示为 `ACTIVE`。现在右击应用抽屉中的应用，应能看到“添加到桌面”和
“更换图标”。

### 不使用 pipx 的备选方式

构建环境需要 Python 3、Babel、`make` 和 `zip`：

```bash
sudo apt install python3-babel make zip
make install-extension   # 打包并安装 dist/gaqu.zip
```

如果必须从 Snap 应用的集成终端安装，请清除其数据目录覆盖：

```bash
env -u XDG_DATA_HOME make install-extension
```

## CLI 用法

```bash
# 列出或搜索应用
gaqu ls
gaqu find firefox

# 为已有应用创建快捷方式
gaqu add firefox

# 更新快捷方式图标（参数依次为 .desktop 文件和新图标文件）
gaqu icon "$HOME/Desktop/firefox.desktop" "$HOME/Downloads/firefox.svg"

# 自动同步之后新安装的软件
gaqu auto
```

### 自动同步配置

创建 `~/.config/gaqu/config.json`：

```json
{
  "auto_create": true,
  "exclude": [
    "org.gnome.Settings",
    "org.gnome.Software"
  ]
}
```

`exclude` 使用 `gaqu ls` 输出的应用 ID。启用自动模式时会先记录
当前已有软件，之后只为新安装的软件自动创建快捷方式。

## 国际化与贡献

扩展使用 Gettext。英文是源代码默认语言，翻译文件位于：

```text
src/gaqu/gnome-extension/po/
├── gaqu.pot
└── zh_CN.po
```

增加或修改界面文字时，应同步更新 POT 和对应的 PO 文件。构建过程会将 PO 编译为
GNOME Shell 使用的 MO 文件。

欢迎通过 Pull Request 提交新语言翻译。

## 开发与验证

```bash
# 1. Python 单元测试
make test

# 2. 扩展语法检查（用 gjs 加载验证）
gjs -m src/gaqu/gnome-extension/extension.js

# 3. 翻译文件检查
msgfmt --check src/gaqu/gnome-extension/po/zh_CN.po

# 4. 打包产物完整性
make pack-extension
unzip -t dist/gaqu.zip

# 5. 本地安装后验证扩展状态
gaqu install
gnome-extensions info gaqu   # 应显示 ACTIVE
```

GNOME Shell 会缓存扩展 JavaScript。在 Wayland 下修改扩展后，需要注销并重新登录，
或者在嵌套的 GNOME Shell 开发会话中测试。

查看扩展错误：

```bash
journalctl -b _COMM=gnome-shell |
  grep -i -C 5 gaqu
```

## 项目结构

```text
.
├── src/gaqu/
│   ├── gnome-extension/   # 纯 GJS 扩展及翻译
│   ├── cli.py             # 可选 Python CLI
│   ├── core.py
│   └── systemd/
├── tests/
├── Makefile
└── pyproject.toml
```

## 卸载

依次清理扩展、自动同步服务和 CLI：

```bash
# 1. 停用并删除 GNOME 扩展
gnome-extensions disable gaqu
rm -rf ~/.local/share/gnome-shell/extensions/gaqu

# 2. 停用自动同步服务（如曾运行过 gaqu auto）
systemctl --user disable --now gaqu.timer 2>/dev/null
rm -f ~/.config/systemd/user/gaqu.service ~/.config/systemd/user/gaqu.timer
systemctl --user daemon-reload

# 3. 卸载 CLI
pipx uninstall gaqu
```

以下为本工具产生的可选数据，如不再需要可一并删除：

```bash
# 配置与状态
rm -rf ~/.config/gaqu ~/.local/state/gaqu

# 通过「更换图标」安装的用户图标和隐藏匹配条目
rm -rf ~/.local/share/icons/hicolor/scalable/apps/
# （注意：上面是整个用户自定义图标目录，若还装有其他应用的自定义图标，
#  请按需删除单个文件而不是整个目录）
```

「添加到桌面」生成的 `.desktop` 快捷方式位于你的桌面目录，按需手动删除。

## 许可证

本项目以 `GPL-2.0-or-later` 发布。贡献说明见
[CONTRIBUTING.md](CONTRIBUTING.md)。
