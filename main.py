import os
import hashlib
import time

SOURCE_DIR = "/raw"
TARGET_DIR = "/sorted"

# 1) 你要保护的路径（必须写绝对路径）
EXCLUDE_DIRS = [
    "/sorted/115媒体库",
    "/sorted/115媒体库/CMS",
    "/sorted/115媒体库/CMS/115媒体库",
]

EXT = ".strm"
SCAN_INTERVAL = 86400   # 24小时扫描一次
COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

def is_excluded(path: str) -> bool:
    """判断是否属于排除目录"""
    full = os.path.abspath(path)
    for e in EXCLUDE_DIRS:
        if full.startswith(os.path.abspath(e)):
            return True
    return False

def strm_hash(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    except:
        return None

def build_index(root: str):
    index = {}
    for base, dirs, files in os.walk(root):
        if is_excluded(base):  
            continue

        for name in files:
            if not name.endswith(EXT):
                continue

            full = os.path.join(base, name)
            if is_excluded(full):
                continue

            h = strm_hash(full)
            if h:
                index.setdefault(h, []).append(full)
    return index


def try_remove_empty_dirs(root: str):
    for base, dirs, files in os.walk(root, topdown=False):
        if is_excluded(base):
            continue

        if not dirs and not files:
            try:
                os.rmdir(base)
                print(f"[RMDIR] 删除空目录：{base}")
            except:
                pass


print("=== STRM Sync Cleaner Started ===")
print(f"Source: {SOURCE_DIR}")
print(f"Target: {TARGET_DIR}")
print("Exclude:")
for e in EXCLUDE_DIRS:
    print("   ", e)
print("===================================")

while True:
    try:
        src = build_index(SOURCE_DIR)
        tgt = build_index(TARGET_DIR)

        for h, target_paths in tgt.items():
            if h in src:
                continue

            for p in target_paths:
                if is_excluded(p):
                    print(f"[SKIP] 排除目录跳过：{p}")
                    continue

                base = os.path.dirname(p)
                base_no_ext = os.path.splitext(p)[0]

                # 删除 STRM
                if os.path.exists(p):
                    os.remove(p)
                    print(f"[DEL] STRM: {p}")

                # 删除 NFO
                nfo = base_no_ext + ".nfo"
                if os.path.exists(nfo):
                    os.remove(nfo)
                    print(f"[DEL] NFO : {nfo}")

                # 删除封面
                for name in os.listdir(base):
                    _, ext = os.path.splitext(name.lower())
                    if ext in COVER_EXTS:
                        full = os.path.join(base, name)
                        if os.path.exists(full):
                            os.remove(full)
                            print(f"[DEL] COVER: {full}")

        try_remove_empty_dirs(TARGET_DIR)
        print(f"[SLEEP] {SCAN_INTERVAL} 秒后再次扫描\n")

    except Exception as e:
        print("[FATAL ERROR]", e)

    time.sleep(SCAN_INTERVAL)
