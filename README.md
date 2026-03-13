# astrbot_plugin_kuro_sign

基于已验证通过的登录与签到链路封装的独立版 AstrBot 插件。

## 功能

- 通过本地网页登录完成 GeeTest、短信验证码和 Kuro 登录
- 登录链路固定为 `getSmsCodeForH5 -> sdkLogin`
- 提供 AstrBot 指令触发:
  - 鸣潮签到
  - 社区签到任务

## 指令

- `/kuro_login`
  - 返回本地登录页地址
- `/kuro_status`
  - 查看当前登录状态
- `/kuro_waves_sign`
  - 执行鸣潮签到
- `/kuro_bbs_sign`
  - 执行社区签到任务

## 说明

- 插件已自带网页登录、token 会话、鸣潮签到、社区任务逻辑
- 当前实现把 AstrBot 用户和本地网页登录会话做了映射，映射文件保存在 `data/owner_map.json`
- 进程重启后，网页登录会话会丢失，需要重新登录
- GeeTest 仍然需要用户自己在浏览器中手动完成

## 安装

把整个 `astrbot_plugin_kuro_sign` 目录直接放进 AstrBot 的 `data/plugins/` 目录即可。
