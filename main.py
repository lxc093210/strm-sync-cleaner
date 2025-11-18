import os
import hashlib
import time

# ========= 配置 =========
# 未整理 STRM（导出目录）
SOURCE_DIR = "/raw"
# 整理后 STRM + NFO 目录
TARGET_DIR = "/sorted"

EXT = ".strm"
SCAN_INTERVAL = 86400  # 每 24 小时扫描一次（86400秒）


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


print("=== STRM Sync Cleaner Started ===")
print(f"Source (未整理目录): {SOURCE_DIR}")
print(f"Target (整理后目录): {TARGET_DIR}")
print("================================")


# ========= 主循环：根据哈希同步删除 =========
while True:
    try:
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
                # 1. 删除目标目录中的 .strm
                if os.path.exists(strm_path):
                    try:
                        os.remove(strm_path)
                        print(f"[DEL] STRM: {strm_path}")
                    except Exception as e:
                        print(f"[ERR] 删除 STRM 失败: {strm_path} -> {e}")

                # 2. 删除同名 .nfo
                base, _ = os.path.splitext(strm_path)
                nfo_path = base + ".nfo"
                if os.path.exists(nfo_path):
                    try:
                        os.remove(nfo_path)
                        print(f"[DEL] NFO : {nfo_path}")
                    except Exception as e:
                        print(f"[ERR] 删除 NFO 失败: {nfo_path} -> {e}")

        print(f"[SLEEP] {SCAN_INTERVAL} 秒后再次扫描\n")

    except Exception as e:
        print(f"[FATAL] 主循环异常: {e}")

    time.sleep(SCAN_INTERVAL)
