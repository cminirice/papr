#!/usr/bin/env bash
# Shared entry for the four production start scripts.
set -euo pipefail
service="${1:-}"
case "$service" in
  web|admin|api|worker) ;;
  *) echo '用法：start-service.sh {web|admin|api|worker}' >&2; exit 2 ;;
esac
if [[ "$EUID" -ne 0 ]]; then
  echo '请使用 sudo 执行启动脚本。' >&2
  exit 1
fi
if [[ "$service" == api || "$service" == worker ]]; then
  systemctl start "papr-$service.service"
  systemctl is-active --quiet "papr-$service.service"
  echo "papr-$service 已启动；日志：sudo journalctl -u papr-$service -n 80 --no-pager"
  if [[ "$service" == worker ]]; then
    echo '请确认日志出现“PDF真实探针通过，用户worker就绪”；进程启动不等于PDF就绪。'
  fi
  exit 0
fi
site="papr-$service"
source="/etc/nginx/sites-available/$site"
link="/etc/nginx/sites-enabled/$site"
[[ "$service" == web ]] && dist=web || dist=admin
if [[ ! -f "$source" || ! -f "/opt/papr/$dist/dist/index.html" ]]; then
  echo "缺少 $source 或 /opt/papr/$dist/dist/index.html，请先配置站点并构建前端。" >&2
  exit 1
fi
created=false
if [[ -e "$link" || -L "$link" ]]; then
  if [[ ! -L "$link" || "$(readlink "$link")" != "$source" ]]; then
    echo "$link 已存在且不是预期链接，请检查；未覆盖。" >&2
    exit 1
  fi
else
  ln -s "$source" "$link"
  created=true
fi
if ! nginx -t; then
  if [[ "$created" == true ]]; then rm -- "$link"; fi
  echo 'Nginx配置检查失败，未重载；本次新增的站点链接已撤回。' >&2
  exit 1
fi
if systemctl is-active --quiet nginx; then
  systemctl reload nginx
else
  systemctl start nginx
fi
systemctl is-active --quiet nginx
echo "$site 已启用；Nginx同时托管两个前端，其他站点配置保持不变。"
