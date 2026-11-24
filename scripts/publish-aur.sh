#!/usr/bin/env sh
# Publish packaging/arch/PKGBUILD to the AUR as the current version.
# Needs: git, curl, makepkg, and an SSH key registered on your AUR account.
# Run after the vX.Y.Z tag has been pushed to GitHub.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/lightdeck/__init__.py")
PKGVER=$(sed -n 's/^pkgver=//p' "$ROOT/packaging/arch/PKGBUILD")
if [ "$VERSION" != "$PKGVER" ]; then
  echo "Version mismatch: app is $VERSION but PKGBUILD says $PKGVER" >&2
  exit 1
fi

URL="https://github.com/MechNoxer/lightdeck/archive/refs/tags/v$VERSION.tar.gz"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "Downloading $URL"
curl -fsSL "$URL" -o "$WORK/src.tar.gz"
TOP=$(tar -tzf "$WORK/src.tar.gz" | head -n1 | cut -d/ -f1)
if [ "$TOP" != "lightdeck-$VERSION" ]; then
  echo "Tarball unpacks to '$TOP', expected 'lightdeck-$VERSION'. Is the GitHub repo renamed to 'lightdeck'?" >&2
  exit 1
fi
SUM=$(sha256sum "$WORK/src.tar.gz" | cut -d' ' -f1)

# Record the checksum in the repo copy too.
sed -i "s/^sha256sums=.*/sha256sums=(\"$SUM\")/" "$ROOT/packaging/arch/PKGBUILD"

git clone ssh://aur@aur.archlinux.org/lightdeck.git "$WORK/aur"
cp "$ROOT/packaging/arch/PKGBUILD" "$WORK/aur/PKGBUILD"
cd "$WORK/aur"
makepkg --printsrcinfo > .SRCINFO
cp .SRCINFO "$ROOT/packaging/arch/.SRCINFO"

if [ -z "$(git status --porcelain -- PKGBUILD .SRCINFO)" ]; then
  echo "The AUR already has lightdeck $VERSION with this PKGBUILD; nothing to publish."
  echo "Bump the version (or pkgrel in packaging/arch/PKGBUILD) to publish an update."
  exit 0
fi

echo "Test build (installs missing dependencies with pacman):"
makepkg -f --cleanbuild --syncdeps

git add PKGBUILD .SRCINFO
git commit -m "Update to $VERSION"
git push origin HEAD:master
echo "Published lightdeck $VERSION to the AUR."
