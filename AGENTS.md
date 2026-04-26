# Agent 接棒协议

> 本文件面向任何接手本项目的 AI。人类开发者也可参考。

## 必读文件（按顺序）

1. `docs/handoff.md` — 当前进度、正在做什么、下一步
2. `docs/spec.md` — 项目目标、设计决策、里程碑
3. `README.md` — 项目概览、运行方式

## 接棒步骤

1. 读完上面三个文件
2. 跟用户打招呼，一句话复述"现状 + 下一步"，让用户确认
3. 开工
4. 每完成一个工作单元：更新 `docs/handoff.md` → commit → push

## 工作单元规范

- 一个语义完整的改动 = 一个 commit
- commit message 用 conventional commits 格式：
  - `feat: 新增XX功能`
  - `fix: 修复XX问题`
  - `refactor: 重构XX`
  - `docs: 更新文档`
  - `chore: 杂项`

## 禁止事项

- 不要 `git push --force` 到 main
- 不要 commit secrets（.env、密钥等）
- 不要在不理解现有代码的情况下大规模重写

## 收工前

更新 `docs/handoff.md`：
- 把完成的移到 ✅ 已完成
- 把进行中的写到 🚧 正在做
- 把下一步写到 🔜 下一步
- 记录踩过的坑到 ⚠️ 已知坑
