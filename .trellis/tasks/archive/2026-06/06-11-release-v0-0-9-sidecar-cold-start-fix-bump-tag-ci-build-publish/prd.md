# release v0.0.9 — sidecar cold-start fix, bump, tag, CI build & publish

## Goal

发布 v0.0.9：包含 8bd9f2c sidecar 冷启动修复（首次启动被 Defender 冷扫描拖慢导致 "sidecar not ready within 30s" 的问题——SIDECAR_BOOT 存活标记 + 分级超时 45s/240s/30s + splash 提示区分慢扫描与挂死）。

## Requirements

* 用 `node scripts/bump-version.mjs 0.0.9` 一次性同步 5 处版本号
* 提交 bump commit，打 `v0.0.9` tag
* 推送 main + tag，CI（ci.yml）与 Release workflow（release.yml）构建并发布
* 确认 release workflow 通过 tag==版本一致性门禁并产出安装包

## Acceptance Criteria

* [ ] 5 处版本号均为 0.0.9（脚本输出确认）
* [ ] `v0.0.9` tag 推送成功，release workflow 被触发
* [ ] release workflow 的 tag==version 校验步骤通过
* [ ] GitHub release 产出（CI 完成为准；构建时长较长，可异步确认）

## Out of Scope

* macOS 构建（release.yml 中仍为禁用，独立追踪）
* 任何代码改动（sidecar 修复已在 8bd9f2c 合入 main）

## Technical Notes

* 发布流程文档：README "Releasing" 一节
* v0.0.8 已验证该流程（缓存、--locked、tag 门禁均通过），本次为常规重跑
