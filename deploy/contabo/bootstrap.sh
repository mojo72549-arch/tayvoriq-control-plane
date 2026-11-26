#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID != 0 ]]; then
    printf '%s\n' 'Run with sudo on the dedicated TAYVORIQ VPS.' >&2
    exit 1
fi

. /etc/os-release
if [[ ${ID:-} != ubuntu || ${VERSION_ID:-} != 24.04 || $(uname -m) != x86_64 ]]; then
    printf '%s\n' 'This installer targets the Ubuntu 24.04 x86-64 VPS.' >&2
    exit 1
fi

package_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
compose=(docker compose --file "$package_dir/compose.yaml")

apt-get update
apt-get install -y --no-install-recommends ca-certificates docker.io docker-compose-v2 ffmpeg python3
systemctl enable --now docker
"${compose[@]}" config --quiet
"${compose[@]}" up --detach --wait --wait-timeout 120
for model in qwen3.5:9b gemma4:12b; do
    "${compose[@]}" exec --no-TTY ollama ollama pull "$model"
done
"${compose[@]}" exec --no-TTY ollama ollama list
printf '%s\n' 'Local models and ffmpeg installed for the TAYVORIQ editorial pilot.'
