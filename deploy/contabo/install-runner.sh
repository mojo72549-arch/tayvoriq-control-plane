#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID != 0 ]]; then
    printf '%s\n' 'Run with sudo after bootstrap.sh on the TAYVORIQ VPS.' >&2
    exit 1
fi

runner_dir=/opt/tayvoriq-runner
test -d "$runner_dir"
id tayvoriq >/dev/null
cd "$runner_dir"

if [[ ! -f .runner ]]; then
    # The digest is published with this release in actions/runner.
    version=2.338.2
    archive="actions-runner-linux-x64-${version}.tar.gz"
    checksum=baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40
    curl --fail --location --retry 3 --output "$archive" \
        "https://github.com/actions/runner/releases/download/v${version}/${archive}"
    printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --status
    tar -xzf "$archive"
    chown -R tayvoriq:tayvoriq "$runner_dir"
    read -r -s -p 'Short-lived runner registration token from GitHub Settings / Actions / Runners: ' runner_token
    printf '\n'
    test -n "$runner_token"
    runuser -u tayvoriq -- ./config.sh --unattended \
        --url https://github.com/mojo72549-arch/tayvoriq-control-plane \
        --token "$runner_token" --name tayvoriq-contabo \
        --labels tayvoriq-contabo --work _work
    unset runner_token
fi

if [[ ! -f .service ]]; then
    ./svc.sh install tayvoriq
fi
service=$(cat .service)
[[ $service == actions.runner.*.service && $service != */* ]]
install -d -m 0755 "/etc/systemd/system/${service}.d"
cat > "/etc/systemd/system/${service}.d/tayvoriq.conf" <<'SERVICE'
[Unit]
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Restart=always
RestartSec=10
Environment=PIP_CACHE_DIR=/var/cache/tayvoriq/pip
SERVICE
systemctl daemon-reload
systemctl enable --now "$service"
systemctl is-active "$service"
printf '%s\n' 'The runner is ready for the manual VPS preflight workflow.'
