#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p .runtime/npm .runtime/home
cp browser-package.json .runtime/npm/package.json
cp browser-package-lock.json .runtime/npm/package-lock.json
npm ci --ignore-scripts --prefix .runtime/npm --cache "$PWD/.runtime/npm-cache"
HOME="$PWD/.runtime/home" .runtime/npm/node_modules/.bin/agent-browser install
