#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
port="${1:-3001}"

if [[ "${CONDA_DEFAULT_ENV:-}" != "inquiry-analysis" ]] || [[ -z "${CONDA_PREFIX:-}" ]]; then
  echo "请先执行：conda activate inquiry-analysis" >&2
  exit 1
fi

# The user's nvm initialization currently puts Node 20 before Conda's Node 22.
export PATH="${CONDA_PREFIX}/bin:${PATH}"
hash -r

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if (( node_major < 22 )); then
  echo "当前 Node.js 版本为 $(node --version)，前端需要 Node.js 22 或更高。" >&2
  exit 1
fi

echo "使用 $(node --version)：$(command -v node)"
cd "${project_dir}/web"
exec npm run dev -- --port "${port}"
