#!/bin/bash
#
# Sync shared code from Pro (main) to Community branch
# Usage: ./scripts/sync-community.sh
#
# This script:
# 1. Reads .pro-only to know which files/dirs are exclusive to Pro
# 2. Merges main into community branch
# 3. Removes pro-only files from community
# 4. Strips PRO-BEGIN/PRO-END code blocks from source files
# 5. Replaces files that need community-specific versions
# 6. Commits and optionally pushes

set -e

PRO_ONLY_FILE=".pro-only"
PRO_BRANCH="main"
COMMUNITY_BRANCH="community"
COMMUNITY_REMOTE="community"

if [ ! -f "$PRO_ONLY_FILE" ]; then
  echo "Error: $PRO_ONLY_FILE not found"
  exit 1
fi

echo "=== Syncing Pro -> Community ==="

current_branch=$(git branch --show-current)
if [ "$current_branch" != "$PRO_BRANCH" ]; then
  echo "Error: Must run from $PRO_BRANCH branch (currently on $current_branch)"
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Error: Working tree is dirty. Commit or stash changes first."
  exit 1
fi

echo "1. Switching to $COMMUNITY_BRANCH branch..."
git checkout "$COMMUNITY_BRANCH"

echo "2. Merging $PRO_BRANCH into $COMMUNITY_BRANCH..."
git merge "$PRO_BRANCH" --no-edit

echo "3. Removing pro-only files and directories..."
while IFS= read -r line; do
  line=$(echo "$line" | sed 's/#.*//' | xargs)
  [ -z "$line" ] && continue

  if [ -e "$line" ]; then
    git rm -rf "$line" 2>/dev/null || true
    echo "   Removed: $line"
  fi
done < "$PRO_ONLY_FILE"

echo "4. Stripping PRO-BEGIN/PRO-END blocks from Python files..."
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" -not -path "./node_modules/*" | while read -r pyfile; do
  if grep -q "# --- PRO-BEGIN ---" "$pyfile" 2>/dev/null; then
    sed -i '/# --- PRO-BEGIN ---/,/# --- PRO-END ---/d' "$pyfile"
    echo "   Stripped PRO blocks: $pyfile"
  fi
done

echo "5. Stripping PRO-BEGIN/PRO-END blocks from TypeScript files..."
find . \( -name "*.ts" -o -name "*.tsx" \) -not -path "./.git/*" -not -path "./node_modules/*" | while read -r tsfile; do
  if grep -q "// --- PRO-BEGIN ---" "$tsfile" 2>/dev/null; then
    sed -i '/\/\/ --- PRO-BEGIN ---/,/\/\/ --- PRO-END ---/d' "$tsfile"
    echo "   Stripped PRO blocks: $tsfile"
  fi
done

echo "6. Replacing auth.ts with community stub..."
cat > apps/desktop/lib/auth.ts << 'AUTH_STUB'
/**
 * Desktop authentication helpers — Community edition.
 *
 * Auth is disabled in Community edition. All functions return safe defaults.
 */

export function isAuthEnabled(): boolean {
  return false;
}

export function getAccessToken(): string | null {
  return null;
}

export function setAccessToken(_token: string): void {}

export function clearAccessToken(): void {}

export function getTokenPayload(): Record<string, unknown> | null {
  return null;
}

export function getUserRole(): string {
  return "admin";
}

export function getUserId(): string {
  return "local";
}

export async function login(_provider: string): Promise<void> {}

export type OAuthCallbackResult =
  | { status: "ok" }
  | { status: "totp"; partialToken: string }
  | { status: "error" };

export async function handleCallback(
  _provider: string,
  _code: string,
  _state?: string,
): Promise<OAuthCallbackResult> {
  return { status: "error" };
}

export async function refreshToken(): Promise<boolean> {
  return false;
}

export function logout(): void {
  if (typeof window !== "undefined") {
    window.location.href = "/";
  }
}

export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  return fetch(input, init);
}
AUTH_STUB
echo "   Replaced: apps/desktop/lib/auth.ts"

echo "7. Removing Pro package names from PyInstaller spec..."
if [ -f "scripts/pyinstaller/pnlclaw-server.spec" ]; then
  sed -i 's/"pnlclaw_pro_auth", "pnlclaw_pro_storage", //' scripts/pyinstaller/pnlclaw-server.spec
  echo "   Cleaned: scripts/pyinstaller/pnlclaw-server.spec"
fi

echo "8. Cleaning up empty lines left by block stripping..."
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" -not -path "./node_modules/*" | while read -r pyfile; do
  # Collapse 3+ consecutive blank lines into 2
  sed -i '/^$/N;/^\n$/N;/^\n\n$/d' "$pyfile" 2>/dev/null || true
done

echo "9. Verifying no Pro references remain..."
LEAK_COUNT=0
# Check for pnlclaw_pro imports (excluding comments)
if grep -r "from pnlclaw_pro_auth\|from pnlclaw_pro_storage\|import pnlclaw_pro" --include="*.py" -l . 2>/dev/null | grep -v ".git"; then
  echo "   WARNING: pnlclaw_pro import found!"
  LEAK_COUNT=$((LEAK_COUNT + 1))
fi
# Check for PRO-BEGIN markers still present
if grep -r "PRO-BEGIN" --include="*.py" --include="*.ts" --include="*.tsx" -l . 2>/dev/null | grep -v ".git"; then
  echo "   WARNING: PRO-BEGIN marker still present!"
  LEAK_COUNT=$((LEAK_COUNT + 1))
fi
# Check for pro-only directories
for dir in "packages/pro-auth" "packages/pro-storage" "services/admin-api" "apps/admin"; do
  if [ -d "$dir" ]; then
    echo "   WARNING: Pro directory still exists: $dir"
    LEAK_COUNT=$((LEAK_COUNT + 1))
  fi
done
# Check for .env files (should not exist in repo)
if find . -name ".env" -not -name ".env.example" -not -path "./.git/*" | grep -q .; then
  echo "   WARNING: .env file found in tree!"
  LEAK_COUNT=$((LEAK_COUNT + 1))
fi

if [ "$LEAK_COUNT" -gt 0 ]; then
  echo "   FAILED: $LEAK_COUNT potential Pro leaks detected. Please fix manually."
  echo "   (You are on the $COMMUNITY_BRANCH branch — review and fix before committing.)"
  exit 1
fi
echo "   OK: No Pro code leaks detected."

if [ -n "$(git status --porcelain)" ]; then
  echo "10. Committing community sync..."
  git add -A
  git commit -m "chore: sync from Pro and strip Pro-only code"
fi

echo "11. Done. Community branch is up to date."
echo ""
echo "To push:  git push $COMMUNITY_REMOTE $COMMUNITY_BRANCH:main"
echo ""

echo "Switching back to $PRO_BRANCH..."
git checkout "$PRO_BRANCH"

echo "=== Sync complete ==="
