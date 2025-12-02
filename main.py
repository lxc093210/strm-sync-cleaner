import os
import hashlib
import time

# ========== 配置 ==========
SOURCE_DIR = "/raw"      # 未整理 STRM
TARGET_DIR = "/sorted"   # 整理后 STRM/NFO/图片

EXT = ".strm"
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "86400"))   # 默认 24 小时
COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# ========== STRM 内容哈希 ==========
def strm_hash(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    except:
        return None


# ========== 构建 STRM 文件哈希索引 ==========
def build_index(root: str):
    index = {}

    if not os.path.exists(root):
        print(f"[WARN] 目录不存在：{root}")
        return index

    for base, dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(EXT):
                full = os.path.join(base, name)
                h = strm_hash(full)
                if h:
                    index.setdefault(h, []).append(full)

    return index


# ========== 删除空目录 ==========
def try_remove_empty_dirs(root: str):
    for base, dirs, files in os.walk(root, topdown=False):
        if not dirs and not files:
            try:
                os.rmdir(base)
                print(f"[RMDIR] 删除空目录：{base}")
            except:
                pass


# ========== 启动信息 ==========
print("=== STRM Sync Cleaner (NO-EXCLUDE) ===")
print(f"Source: {SOURCE_DIR}")
print(f"Target: {TARGET_DIR}")
print(f"Scan Interval: {SCAN_INTERVAL} 秒")
print("========================================")


# ========== 主循环 ==========
while True:
    try:
        src = build_index(SOURCE_DIR)
        tgt = build_index(TARGET_DIR)

        print(f"[INFO] 本轮扫描：源 {len(src)}，目标 {len(tgt)}")

        # 遍历全部目标 STRM 哈希
        for h, paths in tgt.items():

            # 源目录找不到 → 缺失 → 删除
            if h not in src:

                for p in paths:
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

                    # 删除封面图片
                    for name in os.listdir(base):
                        _, ext = os.path.splitext(name.lower())
                        if ext in COVER_EXTS:
                            cover = os.path.join(base, name)
                            try:
                                os.remove(cover)
                                print(f"[DEL] COVER: {cover}")
                            except:
                                pass

        # 删除空目录
        try_remove_empty_dirs(TARGET_DIR)

        print(f"[SLEEP] {SCAN_INTERVAL} 秒后再次扫描\n")

    except Exception as e:
        print("[FATAL ERROR]", e)

    time.sleep(SCAN_INTERVAL)

