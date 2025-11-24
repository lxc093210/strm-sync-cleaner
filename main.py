import os
import hashlib
import time
from datetime import datetime

# ========== 基本配置 ==========

# 未整理 STRM（导出目录，对应宿主机 /vol3/1000/docker/AppData/strm）
SOURCE_DIR = "/raw"

# 整理后 STRM + NFO + 图片 目录（对应宿主机 /vol3/1000/lxcemby/emby/video）
TARGET_DIR = "/sorted"

# 识别为 STRM 的扩展名
EXT = ".strm"

# 默认 24 小时扫一次；如需调频，可通过环境变量 SCAN_INTERVAL 覆盖（单位：秒）
DEFAULT_INTERVAL = 86400
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", str(DEFAULT_INTERVAL)))

# 会一起清理的图片封面扩展名
COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# 需要“完全排除、不做任何删除”的目录（容器内路径）
# 注意：这里是容器里看到的路径，不是宿主机路径
EXCLUDE_DIRS = [
    os.path.join(TARGET_DIR, "115媒体库"),   # /sorted/115媒体库
]


# ========== 工具函数 ==========

def norm(path: str) -> str:
    """规范化路径，避免 /a//b 这类问题"""
    return os.path.normpath(path)


# 规范化排除目录
EXCLUDE_DIRS = [norm(p) for p in EXCLUDE_DIRS]


def is_excluded_path(path: str) -> bool:
    """
    判断一个文件/目录是否在排除目录中：
    - path 等于某个排除目录
    - 或 path 在某个排除目录的子目录下
    """
    p = norm(path)
    for ex in EXCLUDE_DIRS:
        if p == ex or p.startswith(ex + os.sep):
            return True
    return False


def strm_hash(path: str) -> str | None:
    """读取 STRM 文件内容并计算 md5，用于匹配"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"[WARN] 计算哈希失败: {path} -> {e}")
        return None


def build_index(root: str) -> dict[str, list[str]]:
    """构建某个目录下所有 .strm 文件的哈希索引：hash -> [路径列表]"""
    index: dict[str, list[str]] = {}

    root = norm(root)
    if not os.path.exists(root):
        print(f"[WARN] 目录不存在: {root}")
        return index

    for base, dirs, files in os.walk(root):
        for name in files:
            if not name.lower().endswith(EXT):
                continue
            full = norm(os.path.join(base, name))
            h = strm_hash(full)
            if not h:
                continue
            index.setdefault(h, []).append(full)

    return index


def try_remove_empty_dirs(root: str):
    """
    尝试删除 TARGET_DIR 下的空目录（自底向上）：
    - 排除 EXCLUDE_DIRS 以及其子目录，不做删除
    """
    root = norm(root)
    if not os.path.exists(root):
        return

    for base, dirs, files in os.walk(root, topdown=False):
        base = norm(base)

        # 在排除目录或其子目录下，一律不删目录
        if is_excluded_path(base):
            continue

        # 没有子目录也没有文件 → 认定为空目录
        if not dirs and not files:
            try:
                os.rmdir(base)
                print(f"[RMDIR] 删除空目录: {base}")
            except Exception as e:
                print(f"[WARN] 删除空目录失败: {base} -> {e}")


# ========== 启动信息 ==========

print("=== STRM Sync Cleaner Started (NO-WEB) ===")
print(f"Time  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Source(未整理目录): {SOURCE_DIR}")
print(f"Target(整理后目录): {TARGET_DIR}")
print(f"Interval(扫描间隔): {SCAN_INTERVAL} 秒")
if EXCLUDE_DIRS:
    for d in EXCLUDE_DIRS:
        print(f"Exclude(不清理目录): {d}")
print("==========================================\n")


# ========== 主循环：根据哈希同步删除 ==========

while True:
    try:
        print(f"[INFO] 开始新一轮扫描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        source_index = build_index(SOURCE_DIR)
        target_index = build_index(TARGET_DIR)

        print(
            f"[INFO] 本轮统计：源目录 {len(source_index)} 条哈希，"
            f"目标目录 {len(target_index)} 条哈希"
        )

        # 遍历目标目录中的所有哈希，如果在源目录中找不到，就认为是“孤立的”
        for h, target_paths in target_index.items():
            # 源里面有同样 hash，就不处理
            if h in source_index:
                continue

            for strm_path in target_paths:
                strm_path = norm(strm_path)

                # ★★★ 关键：排除 115媒体库 等目录 ★★★
                if is_excluded_path(strm_path):
                    print(f"[SKIP] 排除目录，不处理: {strm_path}")
                    continue

                base_dir = os.path.dirname(strm_path)

                # 1. 删除目标目录中的 .strm
                if os.path.exists(strm_path):
                    try:
                        os.remove(strm_path)
                        print(f"[DEL] STRM : {strm_path}")
                    except Exception as e:
                        print(f"[ERR] 删除 STRM 失败: {strm_path} -> {e}")

                # 2. 删除同名 .nfo
                base_no_ext, _ = os.path.splitext(strm_path)
                nfo_path = base_no_ext + ".nfo"
                if os.path.exists(nfo_path):
                    try:
                        os.remove(nfo_path)
                        print(f"[DEL] NFO  : {nfo_path}")
                    except Exception as e:
                        print(f"[ERR] 删除 NFO 失败: {nfo_path} -> {e}")

                # 3. 删除同目录下封面图（backdrop.jpg / poster.png / thumb.jpg 等）
                if os.path.isdir(base_dir) and not is_excluded_path(base_dir):
                    try:
                        for name in os.listdir(base_dir):
                            lower = name.lower()
                            _, ext = os.path.splitext(lower)
                            if ext in COVER_EXTS:
                                cover_full = norm(os.path.join(base_dir, name))
                                try:
                                    os.remove(cover_full)
                                    print(f"[DEL] COVER: {cover_full}")
                                except Exception as e:
                                    print(f"[ERR] 删除图片失败: {cover_full} -> {e}")
                    except Exception as e:
                        print(f"[WARN] 遍历封面目录失败: {base_dir} -> {e}")

        # 4. 尝试删除空目录（不动排除目录）
        try_remove_empty_dirs(TARGET_DIR)

        print(f"[SLEEP] {SCAN_INTERVAL} 秒后再次扫描\n")

    except Exception as e:
        print(f"[FATAL] 主循环异常: {e}")

    time.sleep(SCAN_INTERVAL)
