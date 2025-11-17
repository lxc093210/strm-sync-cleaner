import os
import hashlib
import time
import shutil

# ========== 配置 ==========
SOURCE_DIR = "/vol3/1000/docker/AppData/strm"        # 导出未整理的 strm
TARGET_DIR = "/vol3/1000/lxcemby/emby/video"         # 整理后的 strm

EXT = ".strm"
SCAN_INTERVAL = 5  # 秒

# ========== 读取 STRM 文件内容并计算哈希，用于匹配 ==========
def strm_hash(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return hashlib.md5(content.encode()).hexdigest()
    except:
        return None

# ========== 构建某个目录下所有 .strm 文件的哈希表 ==========
def build_index(root):
    index = {}
    for base, dirs, files in os.walk(root):
        for f in files:
            if f.endswith(EXT):
                full = os.path.join(base, f)
                h = strm_hash(full)
                if h:
                    index[h] = full
    return index

print("🚀 strm-sync-cleaner Started")
print(f"Watching folders:\n  Source: {SOURCE_DIR}\n  Target: {TARGET_DIR}")

# ========== 主循环 ==========
while True:
    source_hash = build_index(SOURCE_DIR)
    target_hash = build_index(TARGET_DIR)

    # 找出整理后目录中比整理前多出的哈希（代表已被删除）
    for h, path in target_hash.items():
        if h not in source_hash:
            print(f"🗑 删除整理后文件：{path}")
            try:
                os.remove(path)
            except:
                pass

    time.sleep(SCAN_INTERVAL)
