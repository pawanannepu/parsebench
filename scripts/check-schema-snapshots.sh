#!/usr/bin/env sh
# Fail if any committed JSON Schema snapshot was edited instead of added (spec 0002, AC-9).
# Snapshots are append only: a shape change needs a version bump, a new
# `<kind>.v<N>.json`, and an upgrade function. Run in CI after fetching the base branch.
#
#   scripts/check-schema-snapshots.sh            # compares against origin/main
#   scripts/check-schema-snapshots.sh origin/dev # or another base
set -eu

BASE="${1:-origin/main}"
DIR="src/parsebench/schemas/json"

EXISTING=$(git ls-tree --name-only "$BASE" -- "$DIR/" | grep -E '\.v[0-9]+\.json$' || true)
if [ -z "$EXISTING" ]; then
  echo "No snapshots on $BASE yet, nothing to guard."
  exit 0
fi

# shellcheck disable=SC2086
if ! git diff --exit-code "$BASE" -- $EXISTING; then
  echo "A committed schema snapshot changed. Bump the record's schema_version and add a new snapshot instead." >&2
  exit 1
fi
echo "Schema snapshots unchanged."
