#!/usr/bin/env bash
# Fetch pinned, checksum-verified linters into .tools/ (gitignored). Nothing is installed system-wide.
#   scripts/tools.sh   -> .tools/actionlint, .tools/shellcheck
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=.tools
AL_VERSION=1.7.12
SC_VERSION=0.11.0
mkdir -p "$DEST"

os=$(uname -s | tr '[:upper:]' '[:lower:]'); arch=$(uname -m)
case "$arch" in x86_64 | amd64) al_arch=amd64 sc_arch=x86_64 ;; arm64 | aarch64) al_arch=arm64 sc_arch=aarch64 ;;
  *) echo "unsupported arch $arch" >&2; exit 1 ;; esac

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
fetch() { # url sha256 -> tmp file
  local tmp; tmp=$(mktemp)
  curl -fsSL --retry 3 -o "$tmp" "$1"
  [ "$(sha256 "$tmp")" = "$2" ] || { echo "checksum mismatch for $1" >&2; rm -f "$tmp"; exit 1; }
  echo "$tmp"
}

if [ ! -x "$DEST/actionlint" ] || ! "$DEST/actionlint" -version | grep -q "$AL_VERSION"; then
  case "${os}_$al_arch" in
    darwin_arm64) sum=aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f ;;
    darwin_amd64) sum=5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644 ;;
    linux_amd64) sum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 ;;
    linux_arm64) sum=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6 ;;
  esac
  f=$(fetch "https://github.com/rhysd/actionlint/releases/download/v$AL_VERSION/actionlint_${AL_VERSION}_${os}_${al_arch}.tar.gz" "$sum")
  tar -xzf "$f" -C "$DEST" actionlint && rm -f "$f"
fi

if [ ! -x "$DEST/shellcheck" ] || ! "$DEST/shellcheck" --version | grep -q "$SC_VERSION"; then
  case "$os.$sc_arch" in
    darwin.aarch64) sum=339b930feb1ea764467013cc1f72d09cd6b869ebf1013296ba9055ab2ffbd26f ;;
    darwin.x86_64) sum=c2c15e08df0e8fbc374c335b230a7ee958c313fa5714817a59aa59f1aa594f51 ;;
    linux.x86_64) sum=b7af85e41cc99489dcc21d66c6d5f3685138f06d34651e6d34b42ec6d54fe6f6 ;;
    linux.aarch64) sum=68a8133197a50beb8803f8d42f9908d1af1c5540d4bb05fdfca8c1fa47decefc ;;
  esac
  f=$(fetch "https://github.com/koalaman/shellcheck/releases/download/v$SC_VERSION/shellcheck-v$SC_VERSION.$os.$sc_arch.tar.gz" "$sum")
  tar -xzf "$f" -C "$DEST" --strip-components 1 "shellcheck-v$SC_VERSION/shellcheck" && rm -f "$f"
fi
echo "tools ready: $("$DEST/actionlint" -version | head -1), shellcheck $SC_VERSION"
