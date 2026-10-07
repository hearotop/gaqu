import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gaqu.cli import main
from gaqu.core import Application, create_shortcut, desktop_dir, read_application


SAMPLE = """[Desktop Entry]
Type=Application
Name=Example
Name[zh_CN]=示例程序
Comment=An example
Exec=example
Icon=example
"""


class CoreTests(unittest.TestCase):
    def test_reads_application(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "example.desktop"
            source.write_text(SAMPLE)
            app = read_application(source)
            self.assertIsNotNone(app)
            self.assertEqual(app.app_id, "example")

    def test_desktop_dir_from_xdg_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "config"
            config.mkdir()
            (config / "user-dirs.dirs").write_text('XDG_DESKTOP_DIR="$HOME/桌面"\n')
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config), "HOME": folder}):
                with patch("pathlib.Path.home", return_value=root):
                    self.assertEqual(desktop_dir(), root / "桌面")

    def test_create_copies_and_marks_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "example.desktop"
            source.write_text(SAMPLE)
            app = Application("example", "Example", source)
            with patch("gaqu.core.desktop_dir", return_value=root / "Desktop"):
                target = create_shortcut(app)
            self.assertEqual(target.read_text(), SAMPLE)
            self.assertTrue(target.stat().st_mode & 0o100)

    def test_update_icon_cli(self):
        with patch("gaqu.cli.update_icon") as update_icon:
            self.assertEqual(
                main(["icon", "/tmp/app.desktop", "/tmp/icon.svg"]),
                0,
            )
        update_icon.assert_called_once_with("/tmp/app.desktop", "/tmp/icon.svg")


if __name__ == "__main__":
    unittest.main()
