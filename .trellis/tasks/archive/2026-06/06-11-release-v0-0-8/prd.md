# release v0.0.8 — bump, tag, CI build & publish

## Goal

发布 v0.0.8：包含 06-10 优化任务的全部 12 项改动（性能/UX/构建）+ 此前的 settings 本地化工作。首次使用本仓新增的 `scripts/bump-version.mjs` 单源版本流程和加固后的 release workflow（uv.lock 锁定、tag==版本门禁、缓存）。

## Requirements

* 用 `node scripts/bump-version.mjs 0.0.8` 一次性同步 5 处版本号
* 提交 bump commit，打 `v0.0.8` tag
* 推送 main + tag，CI（ci.yml）与 Release workflow（release.yml）构建并发布
* 确认 release workflow 通过 tag/版本一致性门禁并产出安装包

## Acceptance Criteria

* [ ] 5 处版本号均为 0.0.8（脚本输出确认）
* [ ] `v0.0.8` tag 推送成功，release workflow 被触发
* [ ] release workflow 的 tag==version 校验步骤通过
* [ ] GitHub release 产出（CI 完成为准；构建时长较长，可异步确认）

## Out of Scope

* macOS 构建（release.yml 中仍为禁用，独立追踪）
* 任何代码改动

## Technical Notes

* 发布流程文档：README "Releasing" 一节（本次优化任务新增）
* 风险：release.yml 本次改动（缓存、--locked、tag 门禁）首次在真实 tag 上运行；若失败需查 workflow 日志修复后重新打 tag
