# 测试策略

[English](testing.md)

## 测试分层

1. **仓库契约：** 双语配对、本地链接、必需文件和 JSON 有效性；
2. **Engine 单元/性质测试：** Interval 不变量、时区、确定性合并和质量行为；
3. **适配器契约测试：** 脱敏海康 XML/JSON fixture、分页和错误映射；
4. **媒体集成测试：** 本地生成 RTSP/媒体样本，覆盖 H.264、H.265、音频和缺口；
5. **硬件兼容测试：** 明确 NVR 型号/固件矩阵；
6. **Windows 端到端：** 安装、启动、添加测试 NVR、检索、导出、卸载/保留数据。

## 命令

始终执行：

```powershell
python scripts/ci/verify_repo.py
```

各模块 README/清单是权威命令来源。先安装精确的共享开发环境：

```powershell
python -m pip install -r requirements-dev.lock.txt
python -m pip install --no-build-isolation --no-deps -e ./engine -e ./integrations/hikvision -e ./gateway -e ./desktop/backend
```

CI 约定使用：

```text
engine:  python -m pytest engine/tests
海康：python -m pytest integrations/hikvision/tests
gateway: python -m pytest gateway/tests
desktop backend: python -m pytest desktop/backend/tests
desktop frontend: npm ci --prefix desktop/frontend && npm test --prefix desktop/frontend && npm run build --prefix desktop/frontend
```

`packaging/windows/build.ps1 -Mode Verify` 在 Windows 上运行全部软件检查。除非许可证、FFmpeg 哈希/声明和签名输入得到明确满足，`-Mode Release` 会按设计阻止发布。

Windows 验证脚本会为 pytest 使用仓库本地 `build/` 下的唯一基础目录。这样即使 `%TEMP%\pytest-of-<user>` 曾由提权进程、IDE 沙箱或其他 Windows 身份创建，也不会触发 `WinError 5`。直接运行 pytest 时可使用相同方式：

```powershell
$pytestTemp = Join-Path (Resolve-Path ./build) ("pytest-manual-" + [guid]::NewGuid().ToString("N"))
python -m pytest engine/tests integrations/hikvision/tests gateway/tests desktop/backend/tests --basetemp $pytestTemp
```

禁止只断言框架能启动的占位测试。测试应保护产品不变量、协议观测或失败模式。

## Fixture 策略

- 脱敏凭据、序列号、公网 IP、客户名称和图片 URL；
- 保留 namespace、可选字段缺失、畸形样本和分页边界；
- Fixture 元数据记录型号/固件和采集日期；
- 禁止客户录像；媒体 fixture 必须是合成或明确获准素材。

## 硬件承诺

无硬件 CI 只能验证解析器和契约，不能证明真机兼容。支持承诺必须有可重复硬件场景和已记录预期结果。
