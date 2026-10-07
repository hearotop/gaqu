import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {
    Extension,
    InjectionManager,
    gettext as _,
} from 'resource:///org/gnome/shell/extensions/extension.js';
import {AppMenu} from 'resource:///org/gnome/shell/ui/appMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

// 获取用户桌面目录（如 ~/桌面），取不到时回退到 ~/Desktop
function getDesktopDirectory() {
    return GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP) ??
        GLib.build_filenamev([GLib.get_home_dir(), 'Desktop']);
}

// 「添加到桌面」：把应用的 .desktop 文件复制到桌面目录，
// 并赋予可执行权限和信任标记，否则 GNOME 会把它当作不可启动的普通文件
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

    // GNOME Files 和桌面图标扩展根据这个元数据判断
    // 复制来的 .desktop 文件是否可信、可否启动
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

// 用户级图标目录：~/.local/share/icons/hicolor/scalable/apps
// 更换图标时把图片文件统一安装到这里
function userIconDirectory() {
    return GLib.build_filenamev([
        GLib.get_user_data_dir(),
        'icons/hicolor/scalable/apps',
    ]);
}

// 用户级应用条目目录：~/.local/share/applications，不存在则创建
function userApplicationsDir() {
    const dir = Gio.File.new_for_path(
        GLib.build_filenamev([GLib.get_user_data_dir(), 'applications'])
    );
    if (!dir.query_exists(null))
        dir.make_directory_with_parents(null);
    return dir;
}

// 按 XDG 规则，同 ID 的用户级条目会覆盖 /usr/share 下的系统条目。
// 这里把系统条目复制到用户目录，从而避免直接改写无权限的系统文件。
function ensureUserDesktopEntry(app) {
    const appInfo = app.get_app_info();
    const sourcePath = appInfo?.get_filename();
    if (!sourcePath)
        throw new Error('The application has no desktop entry');

    const userEntry = userApplicationsDir().get_child(app.get_id());
    const source = Gio.File.new_for_path(sourcePath);
    if (!source.equal(userEntry)) {
        source.copy(userEntry, Gio.FileCopyFlags.OVERWRITE, null, null);
        userEntry.set_attribute_uint32(
            'unix::mode',
            0o644,
            Gio.FileQueryInfoFlags.NONE,
            null
        );
    }
    return userEntry;
}

// GNOME Shell 进程内无法直接弹 GTK 对话框，因此用 zenity 子进程
// 弹文件选择器。用户确认返回文件路径，取消返回 null。
function chooseIconFileAsync() {
    return new Promise((resolve, reject) => {
        const zenity = GLib.find_program_in_path('zenity');
        if (!zenity) {
            reject(new Error('zenity is required to choose an icon file'));
            return;
        }
        const chooser = Gio.Subprocess.new(
            [
                zenity,
                '--file-selection',
                '--title', _('Choose a New Icon'),
                '--file-filter',
                'Images | *.png *.svg *.jpg *.jpeg *.gif *.ico *.xpm *.webp',
            ],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
        );
        chooser.communicate_utf8_async(null, null, (proc, result) => {
            try {
                const [, stdout] = proc.communicate_utf8_finish(result);
                const path = stdout?.trim();
                resolve(proc.get_exit_status() === 0 && path ? path : null);
            } catch (error) {
                reject(error);
            }
        });
    });
}

// 改写 .desktop 文件：替换或追加 Icon= 指向新图标路径，
// 同时把 NoDisplay=true 改回 false（避免图标被隐藏显示为齿轮）
function rewriteIcon(desktopFile, mode, iconPath) {
    const [, contents] = desktopFile.load_contents(null);
    const lines = new TextDecoder().decode(contents).split('\n');
    let iconUpdated = false;
    const rewritten = lines.map(line => {
        if (line.startsWith('Icon=')) {
            iconUpdated = true;
            return `Icon=${iconPath}`;
        }
        // 若启动器把条目标记为隐藏，改回可见
        if (line.startsWith('NoDisplay='))
            return 'NoDisplay=false';
        return line;
    });
    if (!iconUpdated)
        rewritten.push(`Icon=${iconPath}`);
    desktopFile.replace_contents(
        new TextEncoder().encode(rewritten.join('\n')),
        null,
        false,
        Gio.FileCreateFlags.REPLACE_DESTINATION,
        null
    );
    // REPLACE_DESTINATION 会重置权限，恢复为可启动的权限位
    desktopFile.set_attribute_uint32(
        'unix::mode',
        mode,
        Gio.FileQueryInfoFlags.NONE,
        null
    );
}

// 更换图标后的四层刷新，让新图标无需注销即可生效：
function refreshIconCaches(appId) {
    console.log('[GAQU] refreshIconCaches: start');

    // 1. 强制 GNOME Shell 立即重新扫描所有 .desktop 条目，
    //    让 Shell 重新构建应用信息。
    try {
        Shell.AppSystem.get_default().emit('installed-changed');
        console.log('[GAQU] refreshIconCaches: appSystem signal emitted');
    } catch (error) {
        console.error(`[GAQU] refreshIconCaches: appSystem error: ${error.message}`);
    }

    // 2. 强制 Shell 的图标主题重新扫描目录。
    //    新生成的图标文件已被安装，重扫后新查找就能命中。
    //    GNOME Shell 50 没有直接的纹理缓存清理 API，
    //    但唯一文件名确保缓存必然失效。
    try {
        // 通过 St.IconTheme 尝试刷新（如果可用）
        const iconTheme = St.IconTheme?.get_default?.();
        if (iconTheme && iconTheme.rescan_if_needed)
            iconTheme.rescan_if_needed();
        console.log('[GAQU] refreshIconCaches: icon theme rescanned');
    } catch (error) {
        console.log(`[GAQU] refreshIconCaches: icon theme rescan skipped: ${error.message}`);
    }

    // 3. 外部工具：更新磁盘缓存，让桌面图标扩展、文件管理器等
    //    其他进程也能感知变化
    const commands = [
        ['gtk-update-icon-cache', '-f', '-t', GLib.build_filenamev([
            GLib.get_user_data_dir(), 'icons/hicolor',
        ])],
        ['update-desktop-database', GLib.build_filenamev([
            GLib.get_user_data_dir(), 'applications',
        ])],
    ];
    for (const argv of commands) {
        if (!GLib.find_program_in_path(argv[0])) {
            console.log(`[GAQU] refreshIconCaches: skipping ${argv[0]} (not in PATH)`);
            continue;
        }
        try {
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE)
                .wait_async(null, () => {});
            console.log(`[GAQU] refreshIconCaches: launched ${argv[0]}`);
        } catch (error) {
            console.error(`[GAQU] refreshIconCaches: ${argv[0]} error: ${error.message}`);
        }
    }

    // 4. 强制重建 App Grid（抽屉栏）。AppDisplay 不监听 installed-changed，
    //    且其内部 AppIcon 的 St.Icon 纹理缓存不会自动更新。
    //    最终方案：销毁并重建整个 AppDisplay，下次打开时用新图标。
    try {
        const overview = Main.overview;
        const appDisplay =
            overview?._overview?.controls?.appDisplay ??
            overview?.viewSelector?.appDisplay ??
            null;
        if (appDisplay) {
            // 销毁所有现有图标，强制重新加载
            if (appDisplay._allItems) {
                for (const item of appDisplay._allItems) {
                    if (item.destroy)
                        item.destroy();
                }
                appDisplay._allItems = [];
            }
            // 清空应用列表缓存
            if (appDisplay._apps)
                appDisplay._apps = [];
            // 延迟后触发重建
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                try {
                    if (appDisplay._redisplay)
                        appDisplay._redisplay();
                    console.log('[GAQU] refreshIconCaches: _redisplay called');
                } catch (e) {
                    console.error(`[GAQU] refreshIconCaches: _redisplay error: ${e.message}`);
                }
                return GLib.SOURCE_REMOVE;
            });
            console.log('[GAQU] refreshIconCaches: appDisplay cleared');
        } else {
            console.log('[GAQU] refreshIconCaches: appDisplay not found');
        }
    } catch (error) {
        console.error(`[GAQU] refreshIconCaches: appDisplay error: ${error.message}`);
    }

    console.log('[GAQU] refreshIconCaches: done');
}

// 弹窗选图并安装到用户 hicolor 图标目录。
// 每次安装都生成带时间戳的唯一文件名：GNOME Shell 的纹理缓存以
// GIcon 字符串为 key，只有路径变化才能保证旧图标缓存必然失效，
// 从而实现免注销即时更新。返回安装后的路径；取消对话框返回 null。
async function installPickedIcon(prefix) {
    const iconSourcePath = await chooseIconFileAsync();
    if (!iconSourcePath)
        return null; // dialog cancelled

    const iconDirectory = Gio.File.new_for_path(userIconDirectory());
    if (!iconDirectory.query_exists(null))
        iconDirectory.make_directory_with_parents(null);
    const iconSource = Gio.File.new_for_path(iconSourcePath);
    const dotIndex = iconSourcePath.lastIndexOf('.');
    const extension = dotIndex >= 0 ? iconSourcePath.slice(dotIndex) : '';
    const uniqueName =
        `gaqu-${prefix}-${GLib.get_real_time()}${extension}`;
    const iconTarget = iconDirectory.get_child(uniqueName);
    iconSource.copy(iconTarget, Gio.FileCopyFlags.OVERWRITE, null, null);
    return iconTarget.get_path();
}

// 删除某应用历次更新遗留的旧图标（文件名形如 gaqu-<prefix>-<时间戳>），
// 保留本次新安装的那个，避免图标目录越积越多
function removeStaleIcons(prefix, keepName) {
    const iconDirectory = Gio.File.new_for_path(userIconDirectory());
    if (!iconDirectory.query_exists(null))
        return;
    const enumerator = iconDirectory.enumerate_children(
        'standard::name',
        Gio.FileQueryInfoFlags.NONE,
        null
    );
    let info;
    while ((info = enumerator.next_file(null)) !== null) {
        const name = info.get_name();
        if (name !== keepName && name.startsWith(`gaqu-${prefix}-`)) {
            try {
                iconDirectory.get_child(name).delete(null);
            } catch (error) {
                console.warn(`Unable to remove stale icon: ${error.message}`);
            }
        }
    }
    enumerator.close(null);
}

// 「更换图标」入口：区分两类应用。
// 正常应用有 .desktop 条目，直接改写图标；
// 窗口型应用（Dock 上的齿轮图标）没有条目，走隐藏匹配条目方案。
async function updateAppIcon(app) {
    console.log(`[GAQU] updateAppIcon: app=${app.get_name()}, id=${app.get_id()}, hasInfo=${!!app.get_app_info()}`);

    // app.get_app_info() 为空说明是未匹配的窗口，没有条目可改写
    if (!app.get_app_info())
        return updateWindowBackedIcon(app);

    // 用应用 ID 作为图标文件名前缀
    const prefix = app.get_id().replace(/\.desktop$/, '');
    console.log(`[GAQU] updateAppIcon: prefix=${prefix}`);

    const iconPath = await installPickedIcon(prefix);
    if (!iconPath) {
        console.log('[GAQU] updateAppIcon: user cancelled');
        return; // dialog cancelled
    }
    console.log(`[GAQU] updateAppIcon: iconPath=${iconPath}`);

    rewriteIcon(ensureUserDesktopEntry(app), 0o644, iconPath);
    console.log(`[GAQU] updateAppIcon: user entry rewritten`);

    // 同步更新桌面快捷方式：如果桌面目录里存在同名 .desktop 文件，
    // 把它的 Icon= 也改为新路径，保持三处（抽屉、Dock、桌面）一致
    const desktopShortcut = Gio.File.new_for_path(
        GLib.build_filenamev([getDesktopDirectory(), app.get_id()])
    );
    if (desktopShortcut.query_exists(null)) {
        rewriteIcon(desktopShortcut, 0o755, iconPath);
        console.log(`[GAQU] updateAppIcon: desktop shortcut updated`);
    } else {
        console.log(`[GAQU] updateAppIcon: no desktop shortcut, skipping`);
    }

    // 条目已指向新图标，再清理历次更新遗留的旧文件
    removeStaleIcons(prefix, iconPath.split('/').pop());
    console.log(`[GAQU] updateAppIcon: stale icons cleaned`);

    refreshIconCaches(app.get_id());
    Main.notify(
        _('GAQU'),
        _('"%s" icon was updated').format(app.get_name()) + '\n' +
        _('The app grid will refresh when opened')
    );
    console.log(`[GAQU] updateAppIcon: done`);
}

// 取窗口身份：优先 Wayland 的 gtk application id，回退 X11 的 wm class。
// GNOME Shell 用这个身份去匹配同名 .desktop 条目。
function windowIdentity(window) {
    return window.get_gtk_application_id() ?? window.get_wm_class() ?? null;
}

// 从 /proc/<pid>/cmdline 读出窗口进程的启动命令，
// 作为隐藏条目的 Exec= 字段（含空格的参数加引号）
function windowCommand(pid) {
    if (!pid || pid < 1)
        return '';
    try {
        const [, contents] = Gio.File.new_for_path(`/proc/${pid}/cmdline`)
            .load_contents(null);
        return new TextDecoder().decode(contents)
            .split('\0')
            .filter(argument => argument)
            .map(argument => argument.includes(' ') ? `"${argument}"` : argument)
            .join(' ');
    } catch {
        return '';
    }
}

// 某些应用的窗口身份与其 .desktop 条目 ID 不一致（如 Spark 打包的
// kdenlive：窗口 app_id 是 org.kde.kdenlive，条目却是 org.kdenlive.spark），
// Shell 匹配不到任何条目，Dock 上只能显示通用齿轮图标。
// 这里按窗口身份创建一个隐藏条目（NoDisplay=true，不出现在应用网格），
// Shell 的窗口追踪器匹配成功后，Dock 就会显示所选的图标。
async function updateWindowBackedIcon(app) {
    const windows = app.get_windows();
    const identity = windows.map(windowIdentity).find(id => id);
    if (!identity)
        throw new Error('The window has no matchable identity');

    const prefix = identity.replaceAll('/', '_');
    const iconPath = await installPickedIcon(prefix);
    if (!iconPath)
        return; // dialog cancelled

    const alias = userApplicationsDir()
        .get_child(`${prefix}.desktop`);
    if (alias.query_exists(null)) {
        rewriteIcon(alias, 0o644, iconPath);
    } else {
        const command = windows
            .map(window => windowCommand(window.get_pid()))
            .find(command => command) ?? '/bin/true';
        alias.replace_contents(
            new TextEncoder().encode(
                '[Desktop Entry]\n' +
                'Type=Application\n' +
                'NoDisplay=true\n' +
                `Exec=${command}\n` +
                `Icon=${iconPath}\n`
            ),
            null,
            false,
            Gio.FileCreateFlags.REPLACE_DESTINATION,
            null
        );
        alias.set_attribute_uint32(
            'unix::mode',
            0o644,
            Gio.FileQueryInfoFlags.NONE,
            null
        );
    }
    // 隐藏条目已指向新图标，再清理历次更新遗留的旧文件
    removeStaleIcons(prefix, iconPath.split('/').pop());

    refreshIconCaches(`${prefix}.desktop`);
    Main.notify(
        _('GAQU'),
        _('“%s” icon was updated').format(app.get_name())
    );
}

// 扩展入口：向应用右键菜单注入「添加到桌面」和「更换图标」两个菜单项。
// 通过 InjectionManager 改写 AppMenu.setApp，在菜单绑定应用时挂载菜单项。
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
                        this._updateIconItem.visible = app !== null;
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
                                _('GAQU'),
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

                    this._updateIconItem =
                        new PopupMenu.PopupImageMenuItem(
                            _('Update Icon'),
                            'image-x-generic-symbolic'
                        );
                    this._updateIconItem.connect('activate', () => {
                        if (!this._app)
                            return;
                        const app = this._app;
                        updateAppIcon(app).catch(error => {
                            Main.notifyError(
                                _('Unable to Update Icon'),
                                error.message
                            );
                        });
                    });
                    this.addMenuItem(this._updateIconItem);
                };
            }
        );
    }

    disable() {
        this._injections.clear();
        this._injections = null;
    }
}
