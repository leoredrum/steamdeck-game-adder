#!/usr/bin/env python3
"""
Steam Deck 非Steam游戏一键添加工具
- 拖拽游戏exe文件和封面图片
- 自动识别游戏名称
- 自动添加到Steam非Steam游戏
- 自动设置Proton兼容层
"""

import struct
import shutil
import os
import re
import zlib
from pathlib import Path
from urllib.parse import unquote, urlparse

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango

# ==================== 路径配置 ====================
STEAM_ROOT = Path.home() / ".local/share/Steam"
USERDATA_DIR = STEAM_ROOT / "userdata"
CONFIG_VDF_PATH = STEAM_ROOT / "config" / "config.vdf"


def find_user_id():
    for uid in USERDATA_DIR.iterdir():
        if uid.is_dir() and (uid / "config" / "shortcuts.vdf").exists():
            return uid.name
    for uid in USERDATA_DIR.iterdir():
        if uid.is_dir() and (uid / "config").is_dir():
            return uid.name
    return None


USER_ID = find_user_id()
if USER_ID:
    SHORTCUTS_VDF = USERDATA_DIR / USER_ID / "config" / "shortcuts.vdf"
    GRID_DIR = USERDATA_DIR / USER_ID / "config" / "grid"
else:
    SHORTCUTS_VDF = None
    GRID_DIR = None


# ==================== 二进制VDF解析 ====================

def read_binary_vdf(data):
    pos = [0]

    def read_byte():
        b = data[pos[0]]
        pos[0] += 1
        return b

    def read_string():
        start = pos[0]
        while data[pos[0]] != 0:
            pos[0] += 1
        s = data[start:pos[0]].decode('utf-8', errors='replace')
        pos[0] += 1
        return s

    def read_int32():
        val = struct.unpack_from('<i', data, pos[0])[0]
        pos[0] += 4
        return val

    def read_object():
        obj = {}
        while pos[0] < len(data):
            typ = read_byte()
            if typ == 0x08:
                break
            key = read_string()
            if typ == 0x00:
                obj[key] = read_object()
            elif typ == 0x01:
                obj[key] = read_string()
            elif typ == 0x02:
                obj[key] = read_int32()
            else:
                break
        return obj

    typ = read_byte()
    if typ == 0x00:
        key = read_string()
        return {key: read_object()}
    return {}


def write_binary_vdf(obj):
    buf = bytearray()

    def write_object(d):
        for key, val in d.items():
            if isinstance(val, dict):
                buf.append(0x00)
                buf.extend(key.encode('utf-8'))
                buf.append(0x00)
                write_object(val)
                buf.append(0x08)
            elif isinstance(val, str):
                buf.append(0x01)
                buf.extend(key.encode('utf-8'))
                buf.append(0x00)
                buf.extend(val.encode('utf-8'))
                buf.append(0x00)
            elif isinstance(val, int):
                buf.append(0x02)
                buf.extend(key.encode('utf-8'))
                buf.append(0x00)
                buf.extend(struct.pack('<i', val))

    for key, val in obj.items():
        buf.append(0x00)
        buf.extend(key.encode('utf-8'))
        buf.append(0x00)
        if isinstance(val, dict):
            write_object(val)
        buf.append(0x08)

    buf.append(0x08)
    return bytes(buf)


# ==================== shortcuts.vdf 操作 ====================

def load_shortcuts():
    if SHORTCUTS_VDF and SHORTCUTS_VDF.exists():
        data = SHORTCUTS_VDF.read_bytes()
        parsed = read_binary_vdf(data)
        return parsed.get("shortcuts", {})
    return {}


def save_shortcuts(shortcuts):
    SHORTCUTS_VDF.parent.mkdir(parents=True, exist_ok=True)
    if SHORTCUTS_VDF.exists():
        backup = SHORTCUTS_VDF.with_suffix('.vdf.bak')
        shutil.copy2(SHORTCUTS_VDF, backup)
    data = write_binary_vdf({"shortcuts": shortcuts})
    SHORTCUTS_VDF.write_bytes(data)


def calc_appid(exe_path, app_name):
    key = (exe_path + app_name).encode('utf-8')
    crc = zlib.crc32(key) & 0xFFFFFFFF
    unsigned_id = crc | 0x80000000
    if unsigned_id >= 0x80000000:
        signed_id = unsigned_id - 0x100000000
    else:
        signed_id = unsigned_id
    return signed_id, unsigned_id


def get_next_index(shortcuts):
    if not shortcuts:
        return 0
    indices = [int(k) for k in shortcuts.keys() if k.isdigit()]
    return max(indices) + 1 if indices else 0


# ==================== 游戏名识别 ====================

# CJK统一汉字范围
_CJK = '\u4e00-\u9fff'
# 中文标点
_CN_PUNCT = '\uff0c\u3001\uff1a\uff01\uff1f\u300a\u300b\u3010\u3011\uff08\uff09\u201c\u201d\uff0c\u3002'
# 日文平假名+片假名
_JP = '\u3040-\u309f\u30a0-\u30ff'

# 版本描述后缀词列表（长的在前优先匹配）
_SUFFIX_WORDS = [
    '\u5b98\u65b9\u4e2d\u6587\u6b65\u5175\u7248',  # 官方中文步兵版
    '\u5b98\u65b9\u4e2d\u6587\u7248',  # 官方中文版
    '\u5b98\u4e2d\u6b65\u5175\u7248',  # 官中步兵版
    '\u5b98\u65b9\u4e2d\u6587',  # 官方中文
    '\u5b98\u4e2d\u7248',  # 官中版
    '\u5b98\u65b9\u7248',  # 官方版
    '\u4e2d\u6587\u7248',  # 中文版
    '\u6b65\u5175\u7248',  # 步兵版
    '\u6c49\u5316\u7248',  # 汉化版
    '\u7b80\u4f53\u7248',  # 简体版
    '\u7e41\u4f53\u7248',  # 繁体版
    '\u5b8c\u6574\u7248',  # 完整版
    '\u8c6a\u534e\u7248',  # 豪华版
    '\u6b63\u5f0f\u7248',  # 正式版
    'AI\u6c49\u5316\u7248',  # AI汉化版
    '\u5b98\u4e2d',  # 官中
    '\u5b98\u65b9',  # 官方
    '\u6c49\u5316',  # 汉化
]


def detect_game_name(exe_path):
    p = Path(exe_path)
    parts = p.parts

    # 找游戏根目录（Game/Games等），取其下一级文件夹名
    game_roots = {'game', 'games'}
    folder_name = None
    for i, part in enumerate(parts):
        if part.lower() in game_roots and i + 1 < len(parts) - 1:
            folder_name = parts[i + 1]
            break

    # 没找到game根目录，取挂载设备根目录下的第一级子文件夹
    if not folder_name:
        mount_depths = {
            'run': 5,    # /run/media/deck/DEVICE/FOLDER
            'home': 4,   # /home/deck/XXX/FOLDER
            'mnt': 3,    # /mnt/DEVICE/FOLDER
        }
        root_part = parts[1] if len(parts) > 1 else ''
        depth = mount_depths.get(root_part, 4)
        if depth < len(parts) - 1:
            folder_name = parts[depth]

    if not folder_name:
        folder_name = p.parent.name

    # 先把文件夹名中含日文的段整个去掉（如 "孤独少女との50日間" → 去掉）
    # 按空格分词，每个词如果含日文就整个丢弃
    jp_pattern = re.compile(r'[' + _JP + r']')
    tokens = folder_name.split(' ')
    clean_tokens = []
    for t in tokens:
        if jp_pattern.search(t):
            continue
        clean_tokens.append(t)
    cleaned = ' '.join(clean_tokens)

    # 从清理后的文件夹名开头提取中文
    name_match = re.match(
        r'([' + _CJK + _CN_PUNCT + r'][' + _CJK + _CN_PUNCT + r'0-9 ]*[' + _CJK + _CN_PUNCT + r'0-9])',
        cleaned
    )
    if name_match:
        raw_name = name_match.group(1)
    else:
        chinese_chunks = re.findall(r'[' + _CJK + r']+', cleaned)
        raw_name = ' '.join(chinese_chunks) if chinese_chunks else None

    if raw_name:
        # 去掉版本描述后缀
        for sw in _SUFFIX_WORDS:
            if raw_name.endswith(sw):
                raw_name = raw_name[:-len(sw)]
                break

        raw_name = raw_name.strip('\uff1a: \uff0c,\u3001-\u2013\u2014')
        if raw_name:
            return raw_name

    # 没有中文，用文件夹名清理后返回
    name = re.sub(r'[-_.]', ' ', folder_name)
    name = re.sub(r'\s+', ' ', name).strip()
    if name == name.lower() or name == name.upper():
        name = name.title()
    return name


# ==================== Proton兼容层设置 ====================

def get_available_proton():
    proton_list = []
    common_dir = STEAM_ROOT / "steamapps" / "common"
    if common_dir.exists():
        for d in sorted(common_dir.iterdir(), reverse=True):
            if d.name.lower().startswith("proton") and d.is_dir():
                name_lower = d.name.lower().replace(" ", "_").replace("-", "_")
                if "experimental" in name_lower:
                    proton_list.append(("proton_experimental", d.name))
                else:
                    m = re.search(r'(\d+)', d.name)
                    if m:
                        proton_list.append((f"proton_{m.group(1)}", d.name))

    custom_dir = STEAM_ROOT / "compatibilitytools.d"
    if custom_dir.exists():
        for d in sorted(custom_dir.iterdir(), reverse=True):
            if d.is_dir():
                vdf_file = d / "compatibilitytool.vdf"
                if vdf_file.exists():
                    content = vdf_file.read_text(errors='replace')
                    m = re.search(r'"(\w[\w\-\.]*)"[\s\n]*\{', content)
                    if m:
                        internal_name = m.group(1)
                        if internal_name != "compatibilitytools":
                            proton_list.append((internal_name, d.name))

    return proton_list


def set_proton_compat(unsigned_appid, proton_name):
    if not CONFIG_VDF_PATH.exists():
        return False
    content = CONFIG_VDF_PATH.read_text(errors='replace')
    appid_str = str(unsigned_appid)
    if '"CompatToolMapping"' not in content:
        return False
    if f'"{appid_str}"' in content:
        pattern = rf'(\s*)"{appid_str}"\s*\{{[^}}]*\}}'
        replacement = f'''\\1"{appid_str}"
\\1{{
\\1\t"name"\t\t"{proton_name}"
\\1\t"config"\t\t""
\\1\t"priority"\t\t"250"
\\1}}'''
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    else:
        entry = f'''\t\t\t\t\t"{appid_str}"
\t\t\t\t\t{{
\t\t\t\t\t\t"name"\t\t"{proton_name}"
\t\t\t\t\t\t"config"\t\t""
\t\t\t\t\t\t"priority"\t\t"250"
\t\t\t\t\t}}
'''
        idx = content.find('"CompatToolMapping"')
        if idx == -1:
            return False
        brace_idx = content.find('{', idx)
        if brace_idx == -1:
            return False
        content = content[:brace_idx + 1] + '\n' + entry + content[brace_idx + 1:]

    backup = CONFIG_VDF_PATH.with_suffix('.vdf.bak')
    shutil.copy2(CONFIG_VDF_PATH, backup)
    CONFIG_VDF_PATH.write_text(content)
    return True


# ==================== 封面图处理 ====================

def _norm_ext(path):
    ext = Path(path).suffix.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.bmp', '.webp'):
        ext = '.png'
    if ext == '.jpeg':
        ext = '.jpg'
    return ext


def install_portrait_image(unsigned_appid, image_path):
    """安装竖版封面 {appid}p.ext — 600x900，库网格视图"""
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    ext = _norm_ext(image_path)
    shutil.copy2(image_path, GRID_DIR / f"{unsigned_appid}p{ext}")


def install_landscape_image(unsigned_appid, image_path):
    """安装横版封面 {appid}.ext — 920x430，库横版/最近游戏"""
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    ext = _norm_ext(image_path)
    shutil.copy2(image_path, GRID_DIR / f"{unsigned_appid}{ext}")


# ==================== 自动匹配文件 ====================

_IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}


def _find_game_root(file_path):
    """找到Game文件夹的子文件夹（扫描上限）"""
    p = Path(file_path)
    game_roots = {'game', 'games'}
    for parent in p.parents:
        if parent.name.lower() in game_roots:
            # 返回Game下的第一级子文件夹
            # file_path在Game/X/...里，X就是游戏根目录
            rel = p.relative_to(parent)
            return parent / rel.parts[0]
    return None


def _scan_folders_up(start_path, game_root=None):
    """从start_path所在文件夹向上扫描，直到game_root，返回所有要扫描的文件夹"""
    folders = []
    current = Path(start_path).parent
    while True:
        folders.append(current)
        if game_root and current == game_root:
            break
        if current.parent == current:
            break
        current = current.parent
        if game_root and not str(current).startswith(str(game_root.parent)):
            break
    return folders


def find_images_near_exe(exe_path):
    """从exe所在文件夹向上扫描找图片，返回排序后的图片列表"""
    game_root = _find_game_root(exe_path)
    folders = _scan_folders_up(exe_path, game_root)

    images = []
    seen = set()
    for folder in folders:
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in _IMG_EXTS and f not in seen:
                seen.add(f)
                images.append(str(f))
    return images


def find_exe_near_image(image_path):
    """从图片所在文件夹及子文件夹找exe"""
    game_root = _find_game_root(image_path)
    search_root = game_root if game_root else Path(image_path).parent

    # 收集所有exe
    candidates = []
    for f in search_root.rglob('*.exe'):
        candidates.append(f)
    for f in search_root.rglob('*.EXE'):
        if f not in candidates:
            candidates.append(f)

    if not candidates:
        return None

    # 优先级排序：文件夹名相关 > game.exe > 其他
    folder_name = search_root.name.lower()
    scored = []
    for f in candidates:
        name_lower = f.stem.lower()
        if name_lower == folder_name or folder_name.startswith(name_lower):
            scored.append((0, f))
        elif name_lower == 'game':
            scored.append((1, f))
        elif name_lower in ('launcher', 'start', 'play', 'main'):
            scored.append((2, f))
        else:
            scored.append((3, f))
    scored.sort(key=lambda x: (x[0], x[1].name))
    return str(scored[0][1])


# ==================== 解析拖拽URI ====================

def parse_drop_uris(data):
    text = data.strip()
    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('file://'):
            parsed = urlparse(line)
            path = unquote(parsed.path)
        else:
            path = unquote(line)
        if os.path.exists(path):
            paths.append(path)
    return paths


# ==================== GTK GUI ====================

CSS = b"""
window {
    background-color: #1b2838;
}
.title-label {
    color: #66c0f4;
    font-size: 20px;
    font-weight: bold;
}
.section-label {
    color: #c7d5e0;
    font-size: 13px;
}
.drop-zone {
    background-color: #2a475e;
    border: 2px dashed #66c0f4;
    border-radius: 10px;
    padding: 10px;
}
.drop-zone-active {
    background-color: #3a5a7a;
    border: 2px solid #66c0f4;
    border-radius: 10px;
    padding: 10px;
}
.drop-zone-filled {
    background-color: #2a475e;
    border: 2px solid #4a8;
    border-radius: 10px;
    padding: 10px;
}
.drop-label {
    color: #8f98a0;
    font-size: 14px;
}
.drop-label-filled {
    color: #a0d0a0;
    font-size: 13px;
}
.name-entry {
    background-color: #2a475e;
    color: #ffffff;
    border: 1px solid #66c0f4;
    border-radius: 5px;
    padding: 8px;
    font-size: 14px;
}
.confirm-button {
    background-color: #1a9f29;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 12px;
    font-size: 16px;
    font-weight: bold;
}
.confirm-button:hover {
    background-color: #22c234;
}
.cleanup-button {
    background-color: #c23;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 10px;
    font-size: 13px;
    font-weight: bold;
}
.cleanup-button:hover {
    background-color: #e34;
}
.proton-combo {
    background-color: #2a475e;
    color: #ffffff;
    border: 1px solid #66c0f4;
    border-radius: 5px;
    padding: 6px;
    font-size: 13px;
}
"""


class DropZone(Gtk.EventBox):

    def __init__(self, hint_text, file_filter_func=None, on_file_set=None):
        super().__init__()
        self.file_filter_func = file_filter_func
        self.on_file_set = on_file_set
        self.file_path = None

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box.set_halign(Gtk.Align.CENTER)
        self.box.set_valign(Gtk.Align.CENTER)
        self.add(self.box)

        self.label = Gtk.Label()
        self.label.set_markup(f'<span size="large">{hint_text}</span>')
        self.label.get_style_context().add_class('drop-label')
        self.label.set_line_wrap(True)
        self.label.set_max_width_chars(35)
        self.label.set_justify(Gtk.Justification.CENTER)
        self.box.pack_start(self.label, True, True, 0)

        self.file_label = Gtk.Label()
        self.file_label.get_style_context().add_class('drop-label-filled')
        self.file_label.set_line_wrap(True)
        self.file_label.set_max_width_chars(40)
        self.file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.file_label.set_no_show_all(True)
        self.box.pack_start(self.file_label, False, False, 0)

        self.preview = Gtk.Image()
        self.preview.set_no_show_all(True)
        self.box.pack_start(self.preview, False, False, 0)

        self.set_size_request(-1, 120)
        self.get_style_context().add_class('drop-zone')

        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.drag_dest_add_text_targets()

        self.connect('drag-data-received', self._on_drag_data)
        self.connect('drag-motion', self._on_drag_motion)
        self.connect('drag-leave', self._on_drag_leave)
        self.connect('button-press-event', self._on_click)

    def _on_drag_motion(self, widget, context, x, y, time):
        sc = self.get_style_context()
        sc.remove_class('drop-zone')
        sc.remove_class('drop-zone-filled')
        sc.add_class('drop-zone-active')
        Gdk.drag_status(context, Gdk.DragAction.COPY, time)
        return True

    def _on_drag_leave(self, widget, context, time):
        sc = self.get_style_context()
        sc.remove_class('drop-zone-active')
        if self.file_path:
            sc.add_class('drop-zone-filled')
        else:
            sc.add_class('drop-zone')

    def _on_drag_data(self, widget, context, x, y, selection, info, time):
        data = selection.get_data().decode('utf-8', errors='replace')
        paths = parse_drop_uris(data)
        for path in paths:
            if self.file_filter_func and not self.file_filter_func(path):
                continue
            self.set_file(path)
            break
        sc = self.get_style_context()
        sc.remove_class('drop-zone-active')

    def _on_click(self, widget, event):
        dialog = Gtk.FileChooserDialog(
            title="选择文件",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            if path:
                self.set_file(path)
        dialog.destroy()

    def set_file(self, path):
        self.file_path = path
        filename = os.path.basename(path)
        self.file_label.set_text(filename)
        self.file_label.set_tooltip_text(path)
        self.file_label.show()

        ext = os.path.splitext(path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp'):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 160, 90, True)
                self.preview.set_from_pixbuf(pixbuf)
                self.preview.show()
            except Exception:
                self.preview.hide()
        else:
            self.preview.hide()

        self.label.set_markup('<span size="large">OK</span>')
        sc = self.get_style_context()
        sc.remove_class('drop-zone')
        sc.remove_class('drop-zone-active')
        sc.add_class('drop-zone-filled')

        if self.on_file_set:
            self.on_file_set(path)


class AddGameWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Steam Deck - \u6dfb\u52a0\u975eSteam\u6e38\u620f")
        self.set_default_size(680, 580)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        self.add(vbox)

        title = Gtk.Label()
        title.set_markup('<span size="x-large" weight="bold" color="#66c0f4">\u6dfb\u52a0\u975eSteam\u6e38\u620f</span>')
        vbox.pack_start(title, False, False, 4)

        drop_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        vbox.pack_start(drop_row, False, False, 8)

        exe_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        exe_label = Gtk.Label()
        exe_label.set_markup('<span color="#c7d5e0">\u6e38\u620f\u7a0b\u5e8f</span>')
        exe_box.pack_start(exe_label, False, False, 0)
        self.exe_drop = DropZone(
            "\u5c06 EXE \u62d6\u5230\u8fd9\u91cc\n\u6216\u70b9\u51fb\u9009\u62e9",
            file_filter_func=lambda p: p.lower().endswith('.exe') or '.' not in os.path.basename(p),
            on_file_set=self._on_exe_set
        )
        exe_box.pack_start(self.exe_drop, True, True, 0)
        drop_row.pack_start(exe_box, True, True, 0)

        img_filter = lambda p: os.path.splitext(p)[1].lower() in ('.png', '.jpg', '.jpeg', '.bmp', '.webp')

        portrait_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        portrait_label = Gtk.Label()
        portrait_label.set_markup('<span color="#c7d5e0">\u7ad6\u7248\u5c01\u9762 (\u53ef\u9009)</span>')
        portrait_box.pack_start(portrait_label, False, False, 0)
        self.portrait_drop = DropZone(
            "\u7ad6\u7248 600x900\n\u62d6\u5165\u6216\u70b9\u51fb",
            file_filter_func=img_filter,
            on_file_set=self._on_portrait_set,
        )
        portrait_box.pack_start(self.portrait_drop, True, True, 0)
        drop_row.pack_start(portrait_box, True, True, 0)

        landscape_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        landscape_label = Gtk.Label()
        landscape_label.set_markup('<span color="#c7d5e0">\u6a2a\u7248\u5c01\u9762 (\u53ef\u9009)</span>')
        landscape_box.pack_start(landscape_label, False, False, 0)
        self.landscape_drop = DropZone(
            "\u6a2a\u7248 920x430\n\u62d6\u5165\u6216\u70b9\u51fb",
            file_filter_func=img_filter,
            on_file_set=self._on_landscape_set,
        )
        landscape_box.pack_start(self.landscape_drop, True, True, 0)
        drop_row.pack_start(landscape_box, True, True, 0)

        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        name_label = Gtk.Label()
        name_label.set_markup('<span color="#c7d5e0">\u6e38\u620f\u540d\u79f0 (\u81ea\u52a8\u8bc6\u522b\uff0c\u53ef\u4fee\u6539)</span>')
        name_label.set_halign(Gtk.Align.START)
        name_box.pack_start(name_label, False, False, 0)
        self.name_entry = Gtk.Entry()
        self.name_entry.get_style_context().add_class('name-entry')
        self.name_entry.set_placeholder_text("\u62d6\u5165EXE\u540e\u81ea\u52a8\u586b\u5199...")
        name_box.pack_start(self.name_entry, False, False, 0)
        vbox.pack_start(name_box, False, False, 4)

        proton_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        proton_label = Gtk.Label()
        proton_label.set_markup('<span color="#c7d5e0">\u517c\u5bb9\u5c42 (Proton)</span>')
        proton_label.set_halign(Gtk.Align.START)
        proton_box.pack_start(proton_label, False, False, 0)

        self.proton_list = get_available_proton()
        self.proton_combo = Gtk.ComboBoxText()
        self.proton_combo.get_style_context().add_class('proton-combo')
        for internal, display in self.proton_list:
            self.proton_combo.append(internal, display)
        if self.proton_list:
            self.proton_combo.set_active(0)
        proton_box.pack_start(self.proton_combo, False, False, 0)
        vbox.pack_start(proton_box, False, False, 4)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        vbox.pack_start(btn_row, False, False, 12)

        self.confirm_btn = Gtk.Button(label="\u786e\u5b9a - \u6dfb\u52a0\u6e38\u620f")
        self.confirm_btn.get_style_context().add_class('confirm-button')
        self.confirm_btn.set_size_request(-1, 50)
        self.confirm_btn.connect('clicked', self._on_confirm)
        btn_row.pack_start(self.confirm_btn, True, True, 0)

        self.cleanup_btn = Gtk.Button(label="\u6e05\u7406\u65e0\u6548\u6e38\u620f")
        self.cleanup_btn.get_style_context().add_class('cleanup-button')
        self.cleanup_btn.set_size_request(-1, 50)
        self.cleanup_btn.connect('clicked', self._on_cleanup)
        btn_row.pack_start(self.cleanup_btn, False, False, 0)

        self.connect('destroy', Gtk.main_quit)

    def _on_exe_set(self, path):
        name = detect_game_name(path)
        self.name_entry.set_text(name)
        # 自动匹配图片
        if not self.portrait_drop.file_path and not self.landscape_drop.file_path:
            images = find_images_near_exe(path)
            if len(images) >= 2:
                self.portrait_drop.set_file(images[0])
                self.landscape_drop.set_file(images[1])
            elif len(images) == 1:
                self.portrait_drop.set_file(images[0])
                self.landscape_drop.set_file(images[0])

    def _on_portrait_set(self, path):
        # 拖入竖版图片时，自动匹配exe和横版图片
        if not self.exe_drop.file_path:
            exe = find_exe_near_image(path)
            if exe:
                self.exe_drop.set_file(exe)
                name = detect_game_name(exe)
                self.name_entry.set_text(name)
        if not self.landscape_drop.file_path:
            # 找同目录下的其他图片
            images = find_images_near_exe(path)
            others = [img for img in images if img != path]
            if others:
                self.landscape_drop.set_file(others[0])

    def _on_landscape_set(self, path):
        # 拖入横版图片时，自动匹配exe和竖版图片
        if not self.exe_drop.file_path:
            exe = find_exe_near_image(path)
            if exe:
                self.exe_drop.set_file(exe)
                name = detect_game_name(exe)
                self.name_entry.set_text(name)
        if not self.portrait_drop.file_path:
            images = find_images_near_exe(path)
            others = [img for img in images if img != path]
            if others:
                self.portrait_drop.set_file(others[0])

    def _reset_drop_zone(self, drop, hint_text):
        drop.file_path = None
        drop.label.set_markup(f'<span size="large">{hint_text}</span>')
        drop.file_label.hide()
        drop.preview.hide()
        sc = drop.get_style_context()
        sc.remove_class('drop-zone-filled')
        sc.add_class('drop-zone')

    def _on_confirm(self, button):
        exe = self.exe_drop.file_path
        name = self.name_entry.get_text().strip()

        if not exe:
            self._show_msg("\u9519\u8bef", "\u8bf7\u62d6\u5165\u6216\u9009\u62e9\u6e38\u620fEXE\u6587\u4ef6\uff01", Gtk.MessageType.ERROR)
            return
        if not name:
            self._show_msg("\u9519\u8bef", "\u6e38\u620f\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a\uff01", Gtk.MessageType.ERROR)
            return
        if not USER_ID:
            self._show_msg("\u9519\u8bef", "\u672a\u627e\u5230Steam\u7528\u6237\u6570\u636e\u76ee\u5f55\uff01", Gtk.MessageType.ERROR)
            return

        exe_quoted = f'"{exe}"'
        start_dir = f'"{str(Path(exe).parent)}"'
        signed_id, unsigned_id = calc_appid(exe_quoted, name)

        shortcuts = load_shortcuts()

        # 重复游戏直接覆盖
        existing_idx = None
        for idx, entry in shortcuts.items():
            if isinstance(entry, dict) and entry.get("AppName") == name:
                existing_idx = idx
                break

        target_idx = existing_idx if existing_idx is not None else str(get_next_index(shortcuts))
        shortcuts[target_idx] = {
            "appid": signed_id,
            "AppName": name,
            "Exe": exe_quoted,
            "StartDir": start_dir,
            "icon": "",
            "ShortcutPath": "",
            "LaunchOptions": "",
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": 0,
            "FlatpakAppID": "",
            "sortas": "",
            "tags": {}
        }

        try:
            save_shortcuts(shortcuts)
        except Exception as e:
            self._show_msg("\u9519\u8bef", f"\u4fdd\u5b58\u5931\u8d25\uff1a\n{e}", Gtk.MessageType.ERROR)
            return

        portrait = self.portrait_drop.file_path
        landscape = self.landscape_drop.file_path
        # 如果只有一张图，两种��面都用同一张
        if portrait and not landscape:
            landscape = portrait
        if landscape and not portrait:
            portrait = landscape
        try:
            if portrait and os.path.isfile(portrait):
                install_portrait_image(unsigned_id, portrait)
            if landscape and os.path.isfile(landscape):
                install_landscape_image(unsigned_id, landscape)
        except Exception as e:
            self._show_msg("\u8b66\u544a", f"\u5c01\u9762\u56fe\u5b89\u88c5\u5931\u8d25\uff1a\n{e}", Gtk.MessageType.WARNING)

        proton_id = self.proton_combo.get_active_id()
        if proton_id:
            try:
                set_proton_compat(unsigned_id, proton_id)
            except Exception as e:
                self._show_msg("\u8b66\u544a", f"Proton\u8bbe\u7f6e\u5931\u8d25\uff1a\n{e}", Gtk.MessageType.WARNING)

        is_overwrite = existing_idx is not None
        action_text = "\u5df2\u8986\u76d6" if is_overwrite else "\u5df2\u6dfb\u52a0"
        self._show_msg("\u6210\u529f",
                       f"\u6e38\u620f \"{name}\" {action_text}\uff01\n"
                       f"AppID: {unsigned_id}\n\n"
                       "\u8bf7\u91cd\u542fSteam\u540e\u751f\u6548\u3002",
                       Gtk.MessageType.INFO)

        self._reset_drop_zone(self.exe_drop, "\u5c06 EXE \u62d6\u5230\u8fd9\u91cc\n\u6216\u70b9\u51fb\u9009\u62e9")
        self._reset_drop_zone(self.portrait_drop, "\u7ad6\u7248 600x900\n\u62d6\u5165\u6216\u70b9\u51fb")
        self._reset_drop_zone(self.landscape_drop, "\u6a2a\u7248 920x430\n\u62d6\u5165\u6216\u70b9\u51fb")
        self.name_entry.set_text("")

    def _on_cleanup(self, button):
        shortcuts = load_shortcuts()
        invalid_games = []

        for idx, entry in shortcuts.items():
            if not isinstance(entry, dict):
                continue
            exe_raw = entry.get("Exe", "")
            exe_path = exe_raw.strip('"').strip("'")
            app_name = entry.get("AppName", f"\u672a\u77e5\u6e38\u620f[{idx}]")
            if not exe_path:
                continue
            if not os.path.isfile(exe_path):
                game_dir = str(Path(exe_path).parent)
                invalid_games.append((idx, app_name, exe_path, game_dir))

        if not invalid_games:
            self._show_msg("\u63d0\u793a",
                           "\u6240\u6709\u5df2\u6dfb\u52a0\u6e38\u620f\u7684\u6587\u4ef6\u90fd\u6b63\u5e38\uff0c\u65e0\u9700\u6e05\u7406\u3002",
                           Gtk.MessageType.INFO)
            return

        dialog = Gtk.Dialog(
            title="\u6e05\u7406\u65e0\u6548\u6e38\u620f",
            transient_for=self,
            modal=True,
        )
        dialog.set_default_size(550, 400)
        dialog.add_buttons("\u53d6\u6d88", Gtk.ResponseType.CANCEL,
                           "\u5220\u9664\u9009\u4e2d", Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_top(8)

        hint = Gtk.Label()
        hint.set_markup(
            f'<span color="#ff6666">\u53d1\u73b0 {len(invalid_games)} \u4e2a\u6e38\u620f\u7684EXE\u6587\u4ef6\u5df2\u4e0d\u5b58\u5728\u3002</span>\n'
            '<span color="#c7d5e0">\u52fe\u9009\u8981\u6e05\u7406\u7684\u6e38\u620f\uff0c\u5c06\u4ece Steam \u79fb\u9664\u5e76\u5220\u9664\u5176\u6240\u5728\u6587\u4ef6\u5939\u3002</span>'
        )
        hint.set_line_wrap(True)
        content.pack_start(hint, False, False, 4)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content.pack_start(scrolled, True, True, 0)

        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled.add(listbox)

        checkboxes = []
        for idx, app_name, exe_path, game_dir in invalid_games:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            row.set_margin_start(4)
            row.set_margin_end(4)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            cb = Gtk.CheckButton(label=app_name)
            cb.set_active(True)
            row.pack_start(cb, False, False, 0)

            detail = Gtk.Label()
            detail.set_markup(
                f'<span size="small" color="#8f98a0">EXE: {exe_path}\n'
                f'\u6587\u4ef6\u5939: {game_dir}</span>'
            )
            detail.set_halign(Gtk.Align.START)
            detail.set_line_wrap(True)
            detail.set_margin_start(24)
            row.pack_start(detail, False, False, 0)

            listbox.pack_start(row, False, False, 0)
            checkboxes.append((cb, idx, app_name, game_dir))

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            removed = []
            errors = []
            for cb, idx, app_name, game_dir in checkboxes:
                if not cb.get_active():
                    continue
                if idx in shortcuts:
                    del shortcuts[idx]
                if os.path.isdir(game_dir):
                    try:
                        shutil.rmtree(game_dir)
                        removed.append(f"{app_name}\n  (\u5df2\u5220\u9664: {game_dir})")
                    except Exception as e:
                        errors.append(f"{app_name}: {e}")
                        removed.append(f"{app_name} (\u4ec5\u4eceSteam\u79fb\u9664)")
                else:
                    removed.append(f"{app_name} (\u6587\u4ef6\u5939\u5df2\u4e0d\u5b58\u5728\uff0c\u4ec5\u4eceSteam\u79fb\u9664)")

            new_shortcuts = {}
            for i, (k, v) in enumerate(sorted(shortcuts.items(),
                                              key=lambda x: int(x[0]) if x[0].isdigit() else 999)):
                new_shortcuts[str(i)] = v

            try:
                save_shortcuts(new_shortcuts)
            except Exception as e:
                dialog.destroy()
                self._show_msg("\u9519\u8bef", f"\u4fdd\u5b58\u5931\u8d25\uff1a\n{e}", Gtk.MessageType.ERROR)
                return

            msg = "\u5df2\u6e05\u7406:\n" + "\n".join(removed)
            if errors:
                msg += "\n\n\u5220\u9664\u51fa\u9519:\n" + "\n".join(errors)
            msg += "\n\n\u8bf7\u91cd\u542fSteam\u540e\u751f\u6548\u3002"
            dialog.destroy()
            self._show_msg("\u6e05\u7406\u5b8c\u6210", msg, Gtk.MessageType.INFO)
        else:
            dialog.destroy()

    def _show_msg(self, title, text, msg_type):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=msg_type,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()


if __name__ == "__main__":
    win = AddGameWindow()
    win.show_all()
    Gtk.main()
