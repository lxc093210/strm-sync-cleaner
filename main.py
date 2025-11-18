import os
import hashlib
import time
from datetime import datetime

# ========= 配置 =========
# 未整理 STRM（导出目录）
SOURCE_DIR = "/raw"
# 整理后 STRM + NFO + 图片 目录
TARGET_DIR = "/sorted"

EXT = ".strm"

# 默认 24 小时扫一次，如需调整，可通过环境变量 SCAN_INTERVAL 覆盖（单位：秒）
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "86400"))

# 会一起清理的封面扩展名
COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# ========= 读取 STRM 文件内容 hash，用于匹配 =========
def strm_hash(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"[WARN] 计算哈希失败: {path} -> {e}")
        return None


# ========= 构建某个目录下所有 .strm 的索引 =========
def build_index(root: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    if not os.path.exists(root):
        print(f"[WARN] 目录不存在: {root}")
        return index

    for base, dirs, files in os.walk(root):
        for name in files:
            if not name.lower().endswith(EXT):
                continue
            full = os.path.join(base, name)
            h = strm_hash(full)
            if not h:
                continue
            index.setdefault(h, []).append(full)

    return index


def try_remove_empty_dirs(root: str):
    """尝试删除空目录（自底向上）"""
    if not os.path.exists(root):
        return
    for base, dirs, files in os.walk(root, topdown=False):
        if not dirs and not files:
            try:
                os.rmdir(base)
                print(f"[RMDIR] 删除空目录: {base}")
            except Exception as e:
                print(f"[WARN] 删除空目录失败: {base} -> {e}")


print("=== STRM Sync Cleaner Started (NO-WEB) ===")
print(f"Source (未整理目录): {SOURCE_DIR}")
print(f"Target (整理后目录): {TARGET_DIR}")
print(f"Scan Interval: {SCAN_INTERVAL} 秒")
print("==========================================")


# ========= 主循环：根据哈希同步删除 =========
while True:
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[START] 本轮扫描开始于: {now}")

        source_index = build_index(SOURCE_DIR)
        target_index = build_index(TARGET_DIR)

        print(
            f"[INFO] 本轮扫描：源目录 {len(source_index)} 条哈希，"
            f"目标目录 {len(target_index)} 条哈希"
        )

        # 遍历目标目录中的所有哈希，如果在源目录中找不到，就认为是“孤立的”
        for h, target_paths in target_index.items():
            if h in source_index:
                continue

            for strm_path in target_paths:
                base_dir = os.path.dirname(strm_path)

                # 1. 删除目标目录中的 .strm
                if os.path.exists(strm_path):
                    try:
                        os.remove(strm_path)
                        print(f"[DEL] STRM: {strm_path}")
                    except Exception as e:
                        print(f"[ERR] 删除 STRM 失败: {strm_path} -> {e}")

                # 2. 删除同名 .nfo
                base_no_ext, _ = os.path.splitext(strm_path)
                nfo_path = base_no_ext + ".nfo"
                if os.path.exists(nfo_path):
                    try:
                        os.remove(nfo_path)
                        print(f"[DEL] NFO : {nfo_path}")
                    except Exception as e:
                        print(f"[ERR] 删除 NFO 失败: {nfo_path} -> {e}")

                # 3. 删除同目录下封面图（backdrop.jpg / poster.png 等）
                if os.path.isdir(base_dir):
                    for name in os.listdir(base_dir):
                        lower = name.lower()
                        _, ext = os.path.splitext(lower)
                        if ext in COVER_EXTS:
                            cover_full = os.path.join(base_dir, name)
                            try:
                                os.remove(cover_full)
                                print(f"[DEL] COVER: {cover_full}")
                            except Exception as e:
                                print(f"[ERR] 删除图片失败: {cover_full} -> {e}")

        # 4. 尝试删除空目录
        try_remove_empty_dirs(TARGET_DIR)

        print(f"[SLEEP] 接下来休眠 {SCAN_INTERVAL} 秒（约 {SCAN_INTERVAL // 3600} 小时）\n")

    except Exception as e:
        print(f"[FATAL] 主循环异常: {e}")

    time.sleep(SCAN_INTERVAL)
