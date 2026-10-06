#!/usr/bin/env bash
# Publish web/ (the app page) to a public GitHub repo served by GitHub Pages.
# The main repo stays private; web/ holds only public values.
#
#   scripts/publish_web.sh                  # default: shahalam22/walksafe-app
#   scripts/publish_web.sh owner/repo
#
# Needs the GitHub CLI (gh), signed in. The first run creates the repo and turns on Pages.
set -euo pipefail

REPO="${1:-shahalam22/walksafe-app}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Creating public repo $REPO"
  gh repo create "$REPO" --public --description "WalkSafe app page (built from the WalkSafe repo's web/ folder)"
fi

cp -r "$ROOT/web/." "$TMP/"
touch "$TMP/.nojekyll"
cat > "$TMP/README.md" <<EOF
# WalkSafe app

The installable WalkSafe web app, published from the \`web/\` folder of the main WalkSafe repo
by \`scripts/publish_web.sh\`. Don't edit here; changes are overwritten on the next publish.
EOF

SOURCE="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
git -C "$TMP" init -q -b main
git -C "$TMP" add -A
git -C "$TMP" -c user.name="$(git -C "$ROOT" config user.name)" -c user.email="$(git -C "$ROOT" config user.email)" \
  commit -q -m "Publish app page from WalkSafe@$SOURCE"
git -C "$TMP" push -q --force "https://github.com/$REPO.git" main

if ! gh api "repos/$REPO/pages" >/dev/null 2>&1; then
  echo "Turning on GitHub Pages"
  gh api -X POST "repos/$REPO/pages" -f "source[branch]=main" -f "source[path]=/" >/dev/null
fi

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
echo "Published. The app is at https://${OWNER,,}.github.io/$NAME/ (the first publish can take a minute)."
