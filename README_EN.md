# GAQU

English | [中文](README.md)

Add "Add to Desktop" and custom icon features to GNOME application menus,
with an optional Python CLI for searching apps, creating shortcuts, and
automatically syncing newly installed software.

## Features

- Right-click menu in app grid: "Add to Desktop" and "Update Icon"
- Supports APT, Snap, Flatpak, and user-installed applications
- Automatically detects localized or custom XDG desktop directories
- Sets executable permissions and GNOME trust markers on launchers
- Icon updates refresh desktop and Dock instantly; app grid refreshes
  on next open
- English UI with Simplified Chinese translation
- Optional Python CLI and user-level systemd auto-sync service

## Installation

Install the CLI with `pipx`, then let it install the extension
(Ubuntu follows PEP 668; do not use `sudo pip` or
`--break-system-packages`):

```bash
sudo apt install pipx
pipx ensurepath
pipx install .

# Install the GNOME extension (copies files, compiles translations,
# enables the extension)
gaqu install
```

Do not run `gaqu install` from a Snap VS Code integrated terminal—it may
override `XDG_DATA_HOME` and install the extension to the wrong location.
Use GNOME Terminal instead.

On Wayland, log out and back in after installation for GNOME Shell to
load the extension. Then verify:

```bash
gnome-extensions info gaqu
```

The status should show `ACTIVE`. Right-click an app in the app grid to
see "Add to Desktop" and "Update Icon".

### Alternative without pipx

Build requirements: Python 3, Babel, `make`, and `zip`:

```bash
sudo apt install python3-babel make zip
make install-extension   # Pack and install dist/gaqu.zip
```

If you must install from a Snap app's integrated terminal, clear its data
directory override:

```bash
env -u XDG_DATA_HOME make install-extension
```

## Updating Icons

Right-click an app icon in the app grid or Dock, choose "Update Icon",
and pick an image file. The icon installs to
`~/.local/share/icons/hicolor/scalable/apps/` and syncs to three places:

| Location | Refresh mechanism | When it takes effect |
|---|---|---|
| Desktop shortcut | File monitor auto-refresh | Immediate |
| Dock | `installed-changed` signal + unique filename cache-bust | Immediate |
| App grid | Forced app list rebuild | Next time you open it |

Icon filenames include timestamps so all caches naturally invalidate.
Old icon files are cleaned up automatically.

## CLI Usage

```bash
# List or search applications
gaqu ls
gaqu find firefox

# Create a shortcut for an existing app
gaqu add firefox

# Update a shortcut icon (args: .desktop file, new icon file)
gaqu icon "$HOME/Desktop/firefox.desktop" "$HOME/Downloads/firefox.svg"

# Auto-sync newly installed software
gaqu auto
```

### Auto-sync Configuration

Create `~/.config/gaqu/config.json`:

```json
{
  "auto_create": true,
  "exclude": [
    "org.gnome.Settings",
    "org.gnome.Software"
  ]
}
```

Use application IDs from `gaqu ls` for `exclude`. When auto mode is
enabled, it first records currently installed software, then only
creates shortcuts for newly installed apps.

## Internationalization & Contributing

The extension uses Gettext. English is the source language; translation
files are at:

```text
src/gaqu/gnome-extension/po/
├── gaqu.pot
└── zh_CN.po
```

When adding or modifying UI text, update the POT and corresponding PO
files. The build process compiles PO files into MO files for GNOME Shell.

Pull requests for new language translations are welcome.

## Development & Verification

```bash
# 1. Python unit tests
make test

# 2. Extension syntax check (load with gjs)
gjs -m src/gaqu/gnome-extension/extension.js

# 3. Translation file check
msgfmt --check src/gaqu/gnome-extension/po/zh_CN.po

# 4. Package integrity
make pack-extension
unzip -t dist/gaqu.zip

# 5. Verify extension status after local install
gaqu install
gnome-extensions info gaqu   # should show ACTIVE
```

GNOME Shell caches extension JavaScript. On Wayland, log out and back in
after modifying the extension, or test in a nested GNOME Shell session.

View extension errors:

```bash
journalctl -b _COMM=gnome-shell |
  grep -i -C 5 gaqu
```

## Project Structure

```text
.
├── src/gaqu/
│   ├── gnome-extension/   # Pure GJS extension with translations
│   ├── cli.py             # Optional Python CLI
│   ├── core.py
│   └── systemd/
├── tests/
├── Makefile
└── pyproject.toml
```

## Uninstall

Remove the extension, auto-sync service, and CLI:

```bash
# 1. Disable and remove the GNOME extension
gnome-extensions disable gaqu
rm -rf ~/.local/share/gnome-shell/extensions/gaqu

# 2. Disable auto-sync service (if you ran gaqu auto)
systemctl --user disable --now gaqu.timer 2>/dev/null
rm -f ~/.config/systemd/user/gaqu.service ~/.config/systemd/user/gaqu.timer
systemctl --user daemon-reload

# 3. Uninstall the CLI
pipx uninstall gaqu
```

Optional data created by this tool; delete if no longer needed:

```bash
# Configuration and state
rm -rf ~/.config/gaqu ~/.local/state/gaqu

# User icons installed via "Update Icon" and hidden matching entries
rm -rf ~/.local/share/icons/hicolor/scalable/apps/
# (Note: this is the entire user icon directory. If you have custom
#  icons for other apps, delete individual files instead.)
```

Desktop shortcuts created by "Add to Desktop" are in your desktop
directory; delete them manually as needed.

## License

This project is released under `GPL-2.0-or-later`. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
