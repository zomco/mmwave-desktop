# 常驻融合回查服务

[English](resident.md)

回查界面可以关掉。雷达历史由只监听 `127.0.0.1` 的后台进程保存
（[ADR-0008](../architecture/decisions/0008-local-clip-review_CN.md)）。

```powershell
python -m tracecue_gateway.resident
```

`tracecue_gateway.resident.serve_events` 把已保存的融合事件列成 JSON。
它不会打开 NVR 时间轴。

## Linux LTS

用 `systemd` 安装 `ExecStart=/usr/bin/python -m tracecue_gateway.resident`，
`Restart=on-failure`，并 enable。

## Windows

用服务控制管理器或任务计划程序「开机启动」注册同一模块。不要要求用户已登录桌面。

## macOS

`launchd` agent 设 `KeepAlive`，`ProgramArguments` 指向
`python -m tracecue_gateway.resident`。这一刀不做公证安装包。
