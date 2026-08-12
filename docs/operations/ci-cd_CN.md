# CI/CD 设计

[English](ci-cd.md)

CI/CD 面向单人维护优化，同时避免某台个人电脑成为唯一事实来源。

## PR 与 Push CI

`ci.yml` 始终运行仓库契约检查。模块清单出现后，模块作业自动启用。稳定的最终 `quality-gate` 使分支保护不受可选 skipped 作业影响。

未来分支保护要求：

- 有协作者后，`main` 必须通过 PR；
- `quality-gate` 必需；
- 必须解决所有讨论；
- 禁止强推和删除；
- 存在第二维护者后，契约、安全和 workflow 要求 CODEOWNERS 评审。

## 安全自动化

`security.yml` 在 push 和每周计划运行轻量秘密/路径审计，PR 另外执行依赖审查。可执行 Python/TypeScript 代码落地后再加入 CodeQL 语言，禁止用空扫描制造安全假象。

Dependabot 当前只管理 GitHub Actions；npm/pip 清单出现后再添加对应生态。

## 发布工作流

`release.yml` 必须检测到真实 Windows 打包脚本和发布清单才可运行。在实现落地前，手工/标签发布会失败，而不是把文档打包伪装成产品二进制。

可发布版本必须：

1. 通过全部 CI 和安全检查；
2. 在干净托管 Windows runner 构建；
3. 运行单元/契约和安装后冒烟测试；
4. 生成 SBOM/来源证明、校验和和第三方声明；
5. 签名二进制与安装器；
6. 上传不可变产物；
7. 只从与应用版本一致的版本标签发布；
8. 保留回滚/撤销记录。

## 密钥

使用 GitHub Environment 管理发布审批和签名秘密。优先使用 OIDC 短期凭据，而非长期密钥。Fork PR 永远拿不到发布和签名秘密。

## 可复现性

固定语言/runtime 和 FFmpeg 版本、锁定依赖、保留迁移测试和产物哈希。只能在维护者工作站重建的版本不算完成发布。
