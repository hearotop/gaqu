# Contributing

Contributions, bug reports, and translations are welcome.

## Development

Run the Python tests:

```bash
make test
```

Build the GNOME Shell extension:

```bash
make pack-extension
```

The extension targets GNOME Shell 50. Test UI changes in a nested Shell or log
out and back in before reporting results because GJS modules are cached.

## Translations

English strings in `extension.js` are the translation source. Update the POT
file when strings change, merge it into each PO file, and keep translator
credits in the PO headers. New language files are welcome under
`src/desktop_shortcut/gnome-extension/po/`.

## License

By contributing, you agree that your contribution is licensed under
GPL-2.0-or-later.
