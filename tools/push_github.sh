#!/usr/bin/env bash
# Пуш проекта на GitHub без коннектора — по personal access token из окружения.
#
#   GH_TOKEN=ghp_xxx tools/push_github.sh <user>/<repo>
#   GH_TOKEN=ghp_xxx tools/push_github.sh <user>/<repo> --check   # только проверить доступ
#
# Токен живёт только в этой команде: после пуша remote перезаписывается на чистый URL,
# в .git/config токен не остаётся.
set -euo pipefail

REPO="${1:?укажи репозиторий в виде <user>/<repo>}"
MODE="${2:-push}"
TOKEN="${GH_TOKEN:?нужен GH_TOKEN — токен GitHub с правом Contents: read/write на этот репозиторий}"

api() { curl -sS -H "Authorization: Bearer ${TOKEN}" -H "Accept: application/vnd.github+json" "$@"; }

echo "→ проверяю доступ к ${REPO}"
CODE=$(api -o /tmp/gh_repo.json -w '%{http_code}' "https://api.github.com/repos/${REPO}")
if [ "$CODE" = "404" ]; then
  echo "✗ репозиторий не найден или токен его не видит (404)."
  echo "  Создай пустой репозиторий ${REPO} на github.com и убедись, что токен выдан именно на него."
  exit 1
elif [ "$CODE" = "401" ]; then
  echo "✗ токен не принят (401). Проверь: не истёк, выдан на аккаунт/организацию-владельца,"
  echo "  с правом Contents: Read and write."
  exit 1
elif [ "$CODE" != "200" ]; then
  echo "✗ GitHub ответил ${CODE}:"; head -c 400 /tmp/gh_repo.json; echo; exit 1
fi

NAME=$(python3 -c 'import json,sys;d=json.load(open("/tmp/gh_repo.json"));print(d.get("full_name","?"), d.get("private","?"))')
echo "✓ доступ есть: ${NAME}"

if [ "$MODE" = "--check" ]; then
  echo "режим проверки: пуш не выполнялся (ветка main, коммитов: $(git rev-list --count main))"
  exit 0
fi

git remote remove origin 2>/dev/null || true
git remote add origin "https://x-access-token:${TOKEN}@github.com/${REPO}.git"
git config --local credential.helper ""

echo "→ пушу ветку main ($(git rev-list --count main) коммитов)"
git push -u origin main

# убираем токен из конфига
git remote set-url origin "https://github.com/${REPO}.git"
echo "✓ готово: https://github.com/${REPO}  (remote очищен от токена)"
