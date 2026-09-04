# 部署信息

- 部署日期：2026-09-04
- 服务器：`ChengLanServer`（`47.121.189.62`）
- 访问地址：`https://prompt-3d.chenglan.tech`
- 当前版本：`3.0.0`，部署提交以 `git -C /home/projects/Prompt-To-3D-World/current rev-parse HEAD` 为准
- 当前发布：以服务器 `current` 链接和本文记录的 Git 提交为准
- 稳定入口：`/home/projects/Prompt-To-3D-World/current`
- 持久数据：`/home/projects/Prompt-To-3D-World/shared/data`
- 运行方式：Nginx 托管前端，后端由 `prompt-3d-api.service` 运行在 `127.0.0.1:8030`

## 当前能力

生产构建、后端 28 项测试、前端 3 项测试和端到端生成流程均已通过。服务器已配置 Kimi K3，并于 2026-09-04 通过真实增强生成验证；模型不可用时仍会保留本地可探索草稿。

Kimi 配置保存在权限为 `600` 的 `/home/projects/Prompt-To-3D-World/shared/.env`。如需更换密钥：

```dotenv
MOONSHOT_API_KEY=<your-key>
KIMI_BASE_URL=https://api.moonshot.cn/v1
```

随后执行：

```bash
systemctl restart prompt-3d-api
```

## 运维命令

```bash
systemctl status prompt-3d-api
journalctl -u prompt-3d-api -n 100 --no-pager
nginx -t
curl http://127.0.0.1:8030/api/v3/health
```

HTTPS 已启用，HTTP 会自动跳转至 HTTPS。证书到期日为 2026-12-03，由 `certbot.timer` 自动续期；续期演练已通过。

```bash
systemctl status certbot.timer
certbot renew --dry-run
```
