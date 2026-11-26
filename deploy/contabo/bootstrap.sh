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

available_kb=$(df --output=avail "$package_dir" | tail -1 | tr -d ' ')
if (( available_kb < 40 * 1024 * 1024 )); then
    printf '%s\n' 'At least 40 GiB free disk space is required for models, dependencies and renders.' >&2
    exit 1
fi

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git git-lfs rsync jq unzip \
    docker.io docker-compose-v2 ffmpeg python3 python3-venv build-essential \
    libsndfile1 fonts-dejavu-core libicu74 libssl3t64 libkrb5-3 zlib1g
if ! id tayvoriq >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash tayvoriq
fi
install -d -o tayvoriq -g tayvoriq -m 0750 /var/cache/tayvoriq /opt/tayvoriq-runner
systemctl enable --now docker
"${compose[@]}" config --quiet
"${compose[@]}" up --detach --wait --wait-timeout 120
for model in qwen3.5:9b gemma4:12b; do
    "${compose[@]}" exec --no-TTY ollama ollama pull "$model"
done
"${compose[@]}" exec --no-TTY ollama ollama list
printf '%s\n' 'Local models, FFmpeg and the dedicated runner account are prepared.'
