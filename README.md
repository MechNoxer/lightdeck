# Lightdeck

A desktop remote for Hue lights on Linux, Windows and macOS.

> [!WARNING]
> **Coming from `philips-hue-for-arch`?** The project has been renamed to **Lightdeck**, and the
> old AUR package won't be updated anymore. Uninstall it and install `lightdeck` instead.
> See [Switching from philips-hue-for-arch](#switching-from-philips-hue-for-arch). Your bridge
> pairing carries over, so you don't need to pair again.

- **Rooms and zones** with a room switch and brightness slider
- **Scenes**: turn on the scenes from the Hue app, or create, edit and delete your own, with an optional live preview on the lights
- **Color and white**: a hue/saturation color wheel, a Kelvin slider (warm → cool) and quick presets
- **Live**: changes made in the Hue app or with a physical switch show up instantly (CLIP v2 event stream)
- **Smooth controls**: sliders send updates while you drag, rate-limited to what the bridge can handle
- Light and dark themes (follows your system by default)
- A **demo mode** with simulated lights, so you can try it without a bridge

Requires a Hue Bridge v2 (the square one) with up-to-date firmware.

> Lightdeck is an independent project and is not affiliated with or endorsed by Signify or Philips. "Hue" is a trademark of Signify.

## Install

Download the installer for your platform from the [Releases](https://github.com/MechNoxer/lightdeck/releases) page:

| Platform | File |
| --- | --- |
| Windows 10/11 | `Lightdeck-<version>-windows-setup.exe` |
| macOS (Apple Silicon) | `Lightdeck-<version>-macos-arm64.dmg` |
| macOS (Intel) | `Lightdeck-<version>-macos-x64.dmg` |
| Linux | `lightdeck-<version>-linux-x64.tar.gz`, or the AUR package below |

The builds are not code-signed yet:

- **Windows**: SmartScreen may warn you. Click *More info → Run anyway*.
- **macOS**: the first time, right-click the app and choose *Open*, or allow it under *System Settings → Privacy & Security*. When asked, allow access to the local network, because that's how the app reaches your bridge.

### Arch Linux (AUR)

```bash
yay -S lightdeck
```

The AUR files are in [`packaging/arch/`](packaging/arch).

### Switching from philips-hue-for-arch

`philips-hue-for-arch` is the old name of this app and no longer gets updates. Remove it and install `lightdeck`:

```bash
yay -Rns philips-hue-for-arch
yay -S lightdeck
```

Then start **Lightdeck** from your app launcher, or run `lightdeck` in a terminal. The old `philips-hue-for-arch` command and launcher entry are removed.
Lightdeck reads your existing pairing from `~/.config/philips-hue-for-arch/config.json` the first time it starts, so you don't need to press the bridge button again.

## Getting started

1. Start Lightdeck. It searches your network for bridges.
2. Pick your bridge, or type its IP address.
3. Press the round link button on top of the bridge within 30 seconds.

Your pairing is stored in:

| Platform | Location |
| --- | --- |
| Linux | `~/.config/lightdeck/config.json` |
| macOS | `~/Library/Application Support/Lightdeck/config.json` |
| Windows | `%APPDATA%\Lightdeck\config.json` |

If you used `philips-hue-for-arch` before, your existing pairing is picked up automatically.

On first connection, Lightdeck remembers the bridge's TLS certificate and from then on only talks to a bridge that presents that same certificate.

## Development

```bash
python -m venv .venv
source .venv/bin/activate          # fish: source .venv/bin/activate.fish
pip install -e ".[dev]"
lightdeck --demo                   # run with simulated lights
pytest                             # headless UI + client tests
```

Project layout:

```
src/lightdeck/
  hue/        bridge client, live store, command queue, demo bridge
  ui/         widgets, pages, scene editor, setup flow, theme
  colors.py   CIE xy / gamut / color temperature math
packaging/    PyInstaller spec, Inno Setup script, AUR PKGBUILD, icons
```

### Releasing

Push a tag such as `v0.3.0`. GitHub Actions runs the tests, builds the Windows installer, the macOS disk images and a Linux tarball, and attaches them to a GitHub release.

To build locally:

```bash
pip install . pyinstaller
pyinstaller packaging/pyinstaller/lightdeck.spec
# Windows: iscc /DAppVersion=0.3.0 packaging\windows\lightdeck.iss
```

Icons are generated with `python scripts/make_icons.py`.
