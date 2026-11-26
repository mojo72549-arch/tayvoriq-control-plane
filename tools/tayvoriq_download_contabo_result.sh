#!/usr/bin/env bash
set -euo pipefail

repository=$1
review_id=$2
destination=$3
[[ "$review_id" =~ ^[0-9]+$ ]]

asset=$(gh api --paginate "repos/$repository/releases?per_page=100" \
  --jq ".[] | select(.tag_name == \"contabo-result-$review_id\") | .assets[] | select(.name == \"result.zip\") | .id")
[[ "$asset" =~ ^[0-9]+$ ]] || {
  echo 'Expected exactly one Contabo result asset.' >&2
  exit 1
}
gh api "repos/$repository/releases/assets/$asset" -H 'Accept: application/octet-stream' > "$destination"
