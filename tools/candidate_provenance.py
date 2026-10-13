"""Write exact source/build provenance alongside candidate firmware."""
import json
import os
import platform
import subprocess
from pathlib import Path

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

data = {
    'candidate_version': '0.1.33-tuya',
    'source_commit': git('rev-parse', 'HEAD'),
    'source_parents': git('show', '-s', '--format=%P', 'HEAD').split(),
    'prior_candidate': 'bd0a9c0dd2e0109544a6aa2a441e92e2670df62a',
    'upstream_0133': 'ace09b31e322c2dc5e8823862b66802494360860',
    'upstream_feature': '84030ab578a205754ed43bc8c9d39aca83923aba',
    'microlink': git('-C', 'external/microlink', 'rev-parse', 'HEAD'),
    'tracked_worktree_clean': not bool(git('status', '--porcelain', '--untracked-files=no')),
    'workflow_run_url': 'https://github.com/' + os.getenv('GITHUB_REPOSITORY', '') + '/actions/runs/' + os.getenv('GITHUB_RUN_ID', ''),
    'python': platform.python_version(),
    'platformio': subprocess.check_output(['pio', '--version'], text=True).strip(),
    'hardware_acceptance': 'pending',
    'installed_device_changed': False,
}
assert data['tracked_worktree_clean'], 'Tracked source changed during build'
Path('artifacts/provenance.json').write_text(json.dumps(data, indent=2) + '\n')
