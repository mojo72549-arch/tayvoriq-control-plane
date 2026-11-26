from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_vps_preflight_has_only_an_explicit_manual_trigger():
    workflow = yaml.load((ROOT / '.github/workflows/tayvoriq-vps-preflight.yml').read_text(), Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'workflow_dispatch'}
    assert workflow['permissions'] == {'contents': 'read'}
    assert workflow['jobs']['verify']['runs-on'] == ['self-hosted', 'Linux', 'X64', 'tayvoriq-contabo']


def test_production_moves_compute_and_model_cache_together():
    workflow = yaml.load((ROOT / '.github/workflows/tayvoriq-deliver-video-now.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'pull_request' not in workflow['on']
    assert "vars.TAYVORIQ_VPS_ENABLED == 'true'" in workflow['jobs']['orchestrate']['runs-on']
    env = workflow['env']
    for field in ('TAYVORIQ_LOCAL_LLM_REQUIRED', 'TAYVORIQ_VENV', 'HF_HOME', 'TORCH_HOME'):
        assert "vars.TAYVORIQ_VPS_ENABLED == 'true'" in env[field]
    assert '/var/cache/tayvoriq/' in env['HF_HOME']
    assert '/var/cache/tayvoriq/' in env['TORCH_HOME']


def test_setup_scripts_parse_and_ollama_is_loopback_only():
    for name in ('bootstrap.sh', 'install-runner.sh', 'prepare-studio.sh'):
        subprocess.run(['bash', '-n', str(ROOT / 'deploy/contabo' / name)], check=True)
    config = yaml.safe_load((ROOT / 'deploy/contabo/compose.yaml').read_text())
    ollama = config['services']['ollama']
    assert ollama['ports'] == ['127.0.0.1:11434:11434']
    assert ollama['environment']['OLLAMA_MAX_LOADED_MODELS'] == '1'
    assert ollama['environment']['OLLAMA_NO_CLOUD'] == '1'
