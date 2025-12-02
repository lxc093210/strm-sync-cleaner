import os
import time
import hashlib
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ==============================
#        配 置 区
# ==============================

# 多个源目录（未整理 STRM）
# 通过环境变量 SOURCE_DIRS 注入，使用 ":" 分隔
# 例如：SOURCE_DIRS=/raw/shuhua:/raw/tongxue
_env_source_dirs = os.getenv("SOURCE_DIRS", "/raw")
SOURCE_DIRS = [p for p in _env_source_dirs.split(":") if p]

# 整理后目录（只在这里删）
TARGET_DIR = os.getenv("TARGET_DIR", "/sorted")

# 扫描间隔（秒），默认 24 小时
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "86400"))

# DRY-RUN 模式：1=只打印不删，0=真实删除
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

# 识别的 STRM 后缀
EXT = ".strm"

# 一并删除的封面文件后缀
COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# 认为是“动态签名、不影响资源本体”的 query 参数键名
DYNAMIC_QUERY_KEYS = {
    "sign", "token", "timestamp", "ts", "expires", "expiry", "auth", "key",
}


# ==============================
#    STRM 内容归一化 + 哈希
# ==============================

def normalize_strm_content(raw: str) -> str:
    """
    对 STRM 内容做归一化：
    - 只取第一行
    - 若是 URL：
        * scheme / host 小写
        * 去掉部分动态 query 参数（签名、token 等）
        * 去掉 fragment / params
    - 否则当普通路径文本处理：strip + lower
    """
    raw = raw.strip()
    if not raw:
        return ""

    line = raw.splitlines()[0].strip()

    # 尝试按 URL 解析
    try:
        url = urlparse(line)
        if url.scheme and url.netloc:
            q = parse_qs(url.query, keep_blank_values=True)

            # 去掉动态参数
            for k in list(q.keys()):
                if k.lower() in DYNAMIC_QUERY_KEYS:
                    q.pop(k, None)

            new_query = urlencode(q, doseq=True)

            normalized = urlunparse((
                url.scheme.lower(),
                url.netloc.lower(),
                url.path,
                "",            # params
                new_query,
                "",            # fragment
            ))
            return normalized
    except Exception:
        # 解析失败就按普通文本处理
        pass

    # 非 URL：统一小写
    return line.lower()


def strm_hash(path: str):
    """
    读取 STRM 文件，归一化内容后做 MD5。
    同一资源在不同目录、不同文件名下，只要指向同一 URL/路径，得到的哈希就一样。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        norm = normalize_strm_content(content)
        if not norm:
            return None

        return hashlib.md5(norm.encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"[HASH-ERR] {path} -> {e}")
        return None


# ==============================
#        构建哈希索引
# ==============================

def build_index(roots):
    """
    roots 可以是：
    - 字符串：单个目录
    - 列表：多个目录
    返回：{ hash: [full_path1, full_path2, ...] }
    """
    index = {}

    if isinstance(roots, str):
        roots = [roots]

    for root in roots:
        if not os.path.exists(root):
            print(f"[WARN] 目录不存在：{root}")
            continue

        for base, dirs, files in os.walk(root):
            for name in files:
                if not name.lower().endswith(EXT):
                    continue
                full = os.path.join(base, name)
                h = strm_hash(full)
                if h:
                    index.setdefault(h, []).append(full)

    return index


# ==============================
#          删除空目录
# ==============================

def try_remove_empty_dirs(root: str):
    for base, dirs, files in os.walk(root, topdown=False):
        if not dirs and not files:
            try:
                if DRY_RUN:
                    print(f"[DRY-RUN] 会删空目录：{base}")
                else:
                    os.rmdir(base)
                    print(f"[RMDIR] 删除空目录：{base}")
            except Exception:
                pass


# ==============================
#            主 循 环
# ==============================

print("=== STRM Sync Cleaner (MULTI-SOURCE + NORMALIZED) ===")
print("源目录（不会被删）:")
for d in SOURCE_DIRS:
    print(f"  - {d}")
print(f"整理目录（会被删）：{TARGET_DIR}")
print(f"SCAN_INTERVAL: {SCAN_INTERVAL} 秒")
print(f"DRY_RUN      : {DRY_RUN}")
print("======================================================\n")

while True:
    try:
        # 源：多个未整理目录的并集（A、B、C……）
        src = build_index(SOURCE_DIRS)

        # 目标：整理后目录 C
        tgt = build_index(TARGET_DIR)

        print(f"[INFO] 本轮扫描：源哈希 {len(src)}，目标哈希 {len(tgt)}")

        # 遍历全部目标 STRM 哈希
        for h, paths in tgt.items():

            # ⭐ 关键逻辑：
            # 只要“任一源目录中还有这个哈希”，就绝不删 C
            if h in src:
                continue

            # 只有当所有源目录都没有该资源时，才删 C 中对应文件
            for p in paths:
                base = os.path.dirname(p)
                base_no_ext = os.path.splitext(p)[0]

                # 删除 STRM
                if os.path.exists(p):
                    if DRY_RUN:
                        print(f"[DRY-RUN] 会删 STRM : {p}")
                    else:
                        os.remove(p)
                        print(f"[DEL] STRM : {p}")

                # 删除 NFO
                nfo = base_no_ext + ".nfo"
                if os.path.exists(nfo):
                    if DRY_RUN:
                        print(f"[DRY-RUN] 会删 NFO  : {nfo}")
                    else:
                        os.remove(nfo)
                        print(f"[DEL] NFO  : {nfo}")

                # 删除封面图片（同目录下 jpg/png/webp）
                try:
                    for name in os.listdir(base):
                        _, ext = os.path.splitext(name.lower())
                        if ext in COVER_EXTS:
                            cover = os.path.join(base, name)
                            if os.path.exists(cover):
                                if DRY_RUN:
                                    print(f"[DRY-RUN] 会删 COVER: {cover}")
                                else:
                                    try:
                                        os.remove(cover)
                                        print(f"[DEL] COVER: {cover}")
                                    except Exception as e:
                                        print(f"[DEL-ERR] {cover} -> {e}")
                except FileNotFoundError:
                    # 目录可能刚被删，忽略
                    pass

        # 删除整理目录下的空目录
        try_remove_empty_dirs(TARGET_DIR)

        print(f"[SLEEP] {SCAN_INTERVAL} 秒后再次扫描\n")

    except Exception as e:
        print("[FATAL ERROR]", e)

    time.sleep(SCAN_INTERVAL)
