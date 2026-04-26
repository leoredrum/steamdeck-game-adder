# steamdeck-game-adder

Steam Deck 非Steam游戏一键添加工具 — 拖拽EXE和封面图，自动添加到Steam库并配置Proton兼容层。

## 状态

- 当前进度: 见 [`docs/handoff.md`](docs/handoff.md)
- 整体计划: 见 [`docs/spec.md`](docs/spec.md)
- 接棒协议: 见 [`AGENTS.md`](AGENTS.md)

## 功能

- 拖拽 / 点击选择游戏 EXE 和封面图片
- 自动识别中文游戏名（从 Game 文件夹下一级目录提取，过滤日文/英文/版本号后缀）
- 自动写入 Steam `shortcuts.vdf`，重复添加直接覆盖
- 自动设置 Proton 兼容层（写入 `config.vdf`）
- 封面图自动安装到 Steam grid 目录
- 一键清理无效游戏（EXE 已不存在的），连同文件夹删除

## 运行

```bash
# 依赖：Python 3 + GTK3（Steam Deck 自带）
python3 add_game.py
```

或双击桌面快捷方式 `AddSteamGame.desktop`。

## 安装到桌面

```bash
cp add_game.py ~/Desktop/
cp AddSteamGame.desktop ~/Desktop/
chmod +x ~/Desktop/AddSteamGame.desktop
```

## 目录

```
steamdeck-game-adder/
├── README.md              # 本文件
├── AGENTS.md              # 接棒 AI 的协议
├── docs/
│   ├── spec.md            # 长期计划书
│   └── handoff.md         # 当下进度
├── add_game.py            # 主程序
└── AddSteamGame.desktop   # 桌面快捷方式
```

## 凭证 / secrets

`.env` / `secrets.yaml` / `cookies.json` / `*.key` / `*.pem` 全部在 `.gitignore` 里，永远不 commit。
