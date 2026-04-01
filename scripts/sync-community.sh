#!/bin/bash
#
# Sync shared code from Pro (main) to Community branch
# Usage: ./scripts/sync-community.sh
#
# This script:
# 1. Reads .pro-only to know which files are exclusive to Pro
# 2. Merges main into community branch
# 3. Removes pro-only files from community
# 4. Commits and optionally pushes

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

echo "3. Removing pro-only files..."
while IFS= read -r line; do
  line=$(echo "$line" | sed 's/#.*//' | xargs)
  [ -z "$line" ] && continue

  if [ -e "$line" ]; then
    git rm -rf "$line" 2>/dev/null || true
    echo "   Removed: $line"
  fi
done < "$PRO_ONLY_FILE"

if [ -n "$(git status --porcelain)" ]; then
  echo "4. Committing pro-only file removal..."
  git add -A
  git commit -m "chore: remove pro-only files from community sync"
fi

echo "5. Done. Community branch is up to date."
echo ""
echo "To push:  git push $COMMUNITY_REMOTE $COMMUNITY_BRANCH"
echo ""

echo "Switching back to $PRO_BRANCH..."
git checkout "$PRO_BRANCH"

echo "=== Sync complete ==="
