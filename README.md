# astrbot_plugin_kuro_sign

AstrBot 插件：基于网页登录获取 Kuro token，支持鸣潮签到、社区签到、定时签到和管理员 WebUI。

## 功能

- 网页登录流程：`getSmsCodeForH5 -> sdkLogin`
- 单用户快捷签到：游戏 + 社区
- 管理员定时全量签到（按绑定账号批量执行）
- 管理员 WebUI 控制台（开关定时、改时间、手动触发）

## 指令

- `/kuro_login` 获取登录链接
- `/kuro_status` 查看当前账号状态
- `/kuro_sign` 一键执行鸣潮+社区签到
- `/kuro_waves_sign` 仅鸣潮签到
- `/kuro_bbs_sign` 仅社区任务签到
- `/kuro_auto_status` 查看定时任务状态

管理员专用（需配置 `admin_ids`）：

- `/kuro_admin` 获取 WebUI 管理链接
- `/kuro_auto_on HH:MM` 开启定时签到
- `/kuro_auto_off` 关闭定时签到
- `/kuro_auto_run` 立即执行一次全量签到

## 配置说明

- `host`: 监听地址，公网部署建议 `0.0.0.0`
- `port`: 网页和 WebUI 端口，默认 `8765`
- `public_ip`: 填公网 IP 或域名，插件自动拼接 URL
- `admin_ids`: 管理员 ID 列表（`sender_id` 或 `unified_msg_origin`）
- `admin_url_ttl_seconds`: 管理链接有效期，默认 `900`
- `auto_sign_enabled`: 是否启用定时签到
- `auto_sign_time`: 定时执行时间（`HH:MM`）

## 公网部署

只需要配置 `public_ip` 即可，例如：

- `public_ip = 1.2.3.4`

插件会返回：

- `http://1.2.3.4:8765/?user=...`（登录页）
- `http://1.2.3.4:8765/admin?token=...`（管理员页，临时）
