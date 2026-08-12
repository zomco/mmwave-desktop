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

模块清单落地后，以各模块 README/清单为准。CI 预期常规命令：

```text
engine:  python -m pytest engine/tests
gateway: python -m pytest gateway/tests
desktop backend: python -m pytest desktop/backend/tests
desktop frontend: npm ci --prefix desktop/frontend && npm test --prefix desktop/frontend && npm run build --prefix desktop/frontend
```

禁止只断言框架能启动的占位测试。测试应保护产品不变量、协议观测或失败模式。

## Fixture 策略

- 脱敏凭据、序列号、公网 IP、客户名称和图片 URL；
- 保留 namespace、可选字段缺失、畸形样本和分页边界；
- Fixture 元数据记录型号/固件和采集日期；
- 禁止客户录像；媒体 fixture 必须是合成或明确获准素材。

## 硬件承诺

无硬件 CI 只能验证解析器和契约，不能证明真机兼容。支持承诺必须有可重复硬件场景和已记录预期结果。
