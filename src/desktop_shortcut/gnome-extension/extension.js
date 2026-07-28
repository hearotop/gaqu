import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {
    Extension,
    InjectionManager,
    gettext as _,
} from 'resource:///org/gnome/shell/extensions/extension.js';
import {AppMenu} from 'resource:///org/gnome/shell/ui/appMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

function getDesktopDirectory() {
    return GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP) ??
        GLib.build_filenamev([GLib.get_home_dir(), 'Desktop']);
}

function createDesktopShortcut(app) {
    const appInfo = app.get_app_info();
    const sourcePath = appInfo?.get_filename();
    if (!sourcePath)
        throw new Error('The application has no desktop entry');

    const desktopDirectory = Gio.File.new_for_path(getDesktopDirectory());
    if (!desktopDirectory.query_exists(null))
        desktopDirectory.make_directory_with_parents(null);

    const source = Gio.File.new_for_path(sourcePath);
    const destination = desktopDirectory.get_child(app.get_id());
    source.copy(
        destination,
        Gio.FileCopyFlags.OVERWRITE,
        null,
        null
    );
    destination.set_attribute_uint32(
        'unix::mode',
        0o755,
        Gio.FileQueryInfoFlags.NONE,
        null
    );

    // GNOME Files and Desktop Icons use this metadata to decide whether a
    // copied desktop entry is trusted and may be launched.
    try {
        destination.set_attribute_string(
            'metadata::trusted',
            'true',
            Gio.FileQueryInfoFlags.NONE,
            null
        );
    } catch (error) {
        console.warn(`Unable to mark shortcut as trusted: ${error.message}`);
    }
}

export default class DesktopShortcutExtension extends Extension {
    enable() {
        this._injections = new InjectionManager();
        this._injections.overrideMethod(
            AppMenu.prototype,
            'setApp',
            originalMethod => {
                return function (app) {
                    originalMethod.call(this, app);
                    if (this._desktopShortcutItem) {
                        this._desktopShortcutItem.visible = app !== null;
                        return;
                    }

                    this._desktopShortcutItem =
                        new PopupMenu.PopupImageMenuItem(
                            _('Add to Desktop'),
                            'user-desktop-symbolic'
                        );
                    this._desktopShortcutItem.connect('activate', () => {
                        if (!this._app)
                            return;

                        try {
                            createDesktopShortcut(this._app);
                            Main.notify(
                                _('Desktop Shortcut'),
                                _('“%s” was added to the desktop')
                                    .format(this._app.get_name())
                            );
                        } catch (error) {
                            Main.notifyError(
                                _('Unable to Create Desktop Shortcut'),
                                error.message
                            );
                        }
                    });
                    this.addMenuItem(this._desktopShortcutItem);
                };
            }
        );
    }

    disable() {
        this._injections.clear();
        this._injections = null;
    }
}
