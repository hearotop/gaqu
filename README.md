# Desktop Shortcut

为 Ubuntu GNOME 应用菜单增加“添加到桌面”功能，并提供可选的 Python
命令行工具，用于搜索应用、创建快捷方式和自动同步新安装的软件。

## 功能

- 在应用抽屉右键菜单中显示“添加到桌面”
- 支持 APT、Snap、Flatpak 和用户安装的应用
- 自动识别本地化或自定义的 XDG 桌面目录
- 设置启动器可执行权限和 GNOME 信任标记
- 英文界面及简体中文翻译
- 可选的 Python CLI 和用户级 systemd 自动同步服务

## GNOME 扩展

扩展使用纯 GJS 实现，运行时不依赖 Python。当前支持 GNOME Shell 50。

### 从源码构建

构建环境需要 Python 3、Babel、`make` 和 `zip`：

```bash
sudo apt install python3-babel make zip
make pack-extension
```

生成的安装包位于：

```text
dist/desktop-shortcut@hearotop.github.io.shell-extension.zip
```

### 本地安装

不要在 Snap 版 VS Code 的集成终端中直接安装，因为它可能覆盖
`XDG_DATA_HOME`。推荐使用 GNOME Terminal：

```bash
gnome-extensions install --force \
  dist/desktop-shortcut@hearotop.github.io.shell-extension.zip
```

Wayland 会话需要注销并重新登录，随后启用扩展：

```bash
gsettings set org.gnome.shell disable-user-extensions false
gnome-extensions enable desktop-shortcut@hearotop.github.io
gnome-extensions info desktop-shortcut@hearotop.github.io
```

状态应显示为 `ACTIVE`。现在右击应用抽屉中的应用，应能看到“添加到桌面”。

如果必须从 Snap 应用的集成终端安装，请清除其数据目录覆盖：

```bash
env -u XDG_DATA_HOME gnome-extensions install --force \
  dist/desktop-shortcut@hearotop.github.io.shell-extension.zip
```

## Python 命令行工具（可选）

Ubuntu 遵循 PEP 668，不建议使用 `pip install --user`。请使用 `pipx`：

```bash
sudo apt install pipx
pipx ensurepath
pipx install .
```

重新打开终端后：

```bash
# 列出或搜索应用
desktop-shortcut list
desktop-shortcut search firefox

# 为已有应用创建快捷方式
desktop-shortcut create firefox

# 自动同步之后新安装的软件
desktop-shortcut enable-auto
```

如果当前终端尚未加载 pipx 路径：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

不要使用 `sudo pip` 或 `--break-system-packages`。

### 自动同步配置

创建 `~/.config/desktop-shortcut/config.json`：

```json
{
  "auto_create": true,
  "exclude": [
    "org.gnome.Settings",
    "org.gnome.Software"
  ]
}
```

`exclude` 使用 `desktop-shortcut list` 输出的应用 ID。启用自动模式时会先记录
当前已有软件，之后只为新安装的软件自动创建快捷方式。

## 国际化与贡献

扩展使用 Gettext。英文是源代码默认语言，翻译文件位于：

```text
src/desktop_shortcut/gnome-extension/po/
├── desktop-shortcut@hearotop.github.io.pot
└── zh_CN.po
```

增加或修改界面文字时，应同步更新 POT 和对应的 PO 文件。构建过程会将 PO 编译为
GNOME Shell 使用的 MO 文件。

欢迎通过 Pull Request 提交新语言翻译。

## 开发与验证

```bash
# Python 测试
make test

# 构建 GNOME 扩展安装包
make pack-extension

# 检查 ZIP
unzip -t dist/desktop-shortcut@hearotop.github.io.shell-extension.zip
```

GNOME Shell 会缓存扩展 JavaScript。在 Wayland 下修改扩展后，需要注销并重新登录，
或者在嵌套的 GNOME Shell 开发会话中测试。

查看扩展错误：

```bash
journalctl -b _COMM=gnome-shell |
  grep -i -C 5 desktop-shortcut
```

## 项目结构

```text
.
├── src/desktop_shortcut/
│   ├── gnome-extension/   # 纯 GJS 扩展及翻译
│   ├── cli.py             # 可选 Python CLI
│   ├── core.py
│   └── systemd/
├── tests/
├── Makefile
└── pyproject.toml
```

## 许可证

本项目以 `GPL-2.0-or-later` 发布。贡献说明见
[CONTRIBUTING.md](CONTRIBUTING.md)。
