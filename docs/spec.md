# steamdeck-game-adder — 计划书

> 长期计划书. 目标 / 设计决策 / 里程碑 / 已否决方案.
> 当下进度在 `handoff.md`, 此文件是全局视图.

## 目标 (Why)

Steam Deck 上一键添加非Steam游戏，省去手动操作的麻烦。

**更详细**:

- 要解决的问题: Steam Deck 添加第三方游戏（特别是Windows exe）流程繁琐，需要手动编辑shortcuts.vdf、设置Proton、复制封面图
- 谁用: Steam Deck 用户
- 成功长什么样: 拖入exe+封面图 → 点确定 → 重启Steam就能玩

## 范围

### 在范围内

- GUI拖拽添加exe和封面图
- 自动识别中文游戏名（从文件夹名提取）
- 自动写入shortcuts.vdf
- 自动设置Proton兼容层
- 封面图自动安装到grid目录
- 清理无效游戏（exe已不存在的）

### 不在范围内 (刻意不做)

- 在线搜索游戏封面（SteamGridDB API等）
- 自动下载/安装游戏
- 支持非Steam Deck的Linux发行版（可能兼容但不主动适配）

## 架构 / 设计决策

### 决策 1: 使用GTK3而非tkinter

- **选择**: GTK3 (gi.repository)
- **Why**: tkinter不支持原生拖拽，Steam Deck上GTK3自带可用，无需安装额外依赖
- **考虑过的 alternatives**:
  - tkinter: 不支持Linux原生DnD，放弃
  - PyQt5: Steam Deck上未预装，pip不可用（只读文件系统），放弃

### 决策 2: 直接解析二进制VDF

- **选择**: 用struct手写二进制VDF解析器
- **Why**: Steam Deck无pip，不能安装第三方vdf库，只能用标准库
- **考虑过的 alternatives**:
  - python-vdf库: 无法安装，放弃

### 决策 3: 游戏名从Game文件夹下一级目录提取中文

- **选择**: 取exe所在路径中Game/下的第一级子文件夹名，提取中文部分
- **Why**: 用户的游戏文件夹命名规范通常是"中文名 英文名 版本号 描述"，中文在最前面

## 里程碑

- [x] M1 — 基础功能：添加游戏、设置Proton、安装封面图
- [x] M2 — GTK3拖拽界面
- [x] M3 — 中文游戏名智能识别
- [x] M4 — 重复添加自动覆盖 + 清理无效游戏
- [ ] M5 — 用户反馈后的优化迭代

## 未解决问题

- Q1: 是否需要支持批量添加多个游戏？(等用户反馈)

## 变更历史

- 2026-04-26 — 项目初始化，完成M1-M4全部功能
