#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"

if [[ "${CONDA_DEFAULT_ENV:-}" != "inquiry-analysis" ]]; then
  echo "请先执行：conda activate inquiry-analysis" >&2
  exit 1
fi

# Some shell profiles initialize nvm after Conda and put an older Node ahead of
# the environment. Ensure this project's Conda binaries take precedence.
export PATH="${CONDA_PREFIX}/bin:${PATH}"
hash -r

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if (( node_major < 22 )); then
  echo "当前 Node.js 版本过低：$(node --version)，需要 22 或更高。" >&2
  exit 1
fi

cd "${project_dir}"
python -m pytest -q backend/tests
npm --prefix web test
npm --prefix web run lint
