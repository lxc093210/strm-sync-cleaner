import os
import time
import hashlib
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ========== 配置 ==========

# 多个「未整理 STRM」目录（源目录：A、B、C……，只读，不删）
SOURCE_DIRS = [
    "/raw",      # 例如：未整理目录 A
    # "/vol1/1000/happyemby/date/alist/书画影音",  # 例如：未整理目录 B（按你实际路径加）
]

# 「整理后 STRM/NFO/图片」目录（目标目录：C，只删这里）
TARGET_DIR = "/sorted"

# 只处理的后缀
EXT = ".strm"
COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# 扫描间隔（秒），默认 24 小时，可用环境变量覆盖
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "86400"))

# DRY-RUN 模式（1 = 只打印不删，0 = 真删）
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

# 认为是「动态、不影响资源本体」的 query 参数键名（按需增减）
DYNAMIC_QUERY_KEYS = {
    "sign", "token", "timestamp", "ts", "expires", "expiry", "auth", "key",
}


# ========== 工具函数：归一化 STRM 内容 ==========

def normalize_strm_content(raw: str) -> str:
    """
    对 STRM 内容做归一化：
    - 只取第一行
    - 如果像 URL：
        * scheme / host 小写
        * 去掉部分动态 query 参数（签名、token 等）
        * 去掉 fragment / params
    - 否则当普通文本路径处理：strip + lower
    """
    raw = raw.strip()
    if not raw:
        return ""

    # 只取第一行
    line = raw.splitlines()[0].strip()

    # 尝试 URL 解析
    try:
        url = urlparse(line)
        if url.scheme and url.netloc:
            # 解析 query，去掉动态参数
            q = parse_qs(url.query, keep_blank_values=True)

            for k in list(q.keys()):
                if k.lower() in DYNAMIC_QUERY_KEYS:
                    q.pop(k, None)

            new_query = urlencode(q, doseq=True)

            normalized = urlunparse((
                url.scheme.lower(),
                url.netloc.lower(),
                url.path,
                "",             # params 不用
                new_query,
                "",             # fragment 去掉
            ))
            return normalized

    except Exception:
        # 解析失败就当普通文本处理
        pass

    # 非 URL：统一成小写文本
    return line.lower()


def strm_hash(path: str) -> str | None:
    """
    读取 STRM 文件，归一化其内容后做 MD5。
    同一资源（URL 核心不变）应得到相同哈希。
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


# ========== 构建索引：哈希 -> 路径列表 ==========

def build_index(roots):
    """
    roots 可以是单个目录字符串，也可以是目录列表。
    返回：{ hash: [full_path1, full_path2, ...] }
    """
    index: dict[str, list[str]] = {}

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


# ========== 删除空目录 ==========

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


# ========== 启动信息 ==========

print("=== STRM Sync Cleaner (MULTI-SOURCE + NORMALIZED CONTENT) ===")
print("Source Dirs:")
for d in SOURCE_DIRS:
    print(f"  - {d}")
print(f"Target      : {TARGET_DIR}")
print(f"Scan Interval: {SCAN_INTERVAL} 秒")
print(f"DRY_RUN      : {DRY_RUN}")
print("===============================================================")


# ========== 主循环 ==========

while True:
    try:
        # 源：多个未整理目录的并集（A、B、C……）
        src = build_index(SOURCE_DIRS)
        # 目标：整理后目录 C
        tgt = build_index(TARGET_DIR)

        print(f"[INFO] 本轮扫描：源哈希 {len(src)}，目标哈希 {len(tgt)}")

        # 遍历全部目标 STRM 哈希
        for h, paths in tgt.items():

            # ⭐ 核心判断：
            # 只有当「所有源目录中都找不到这个哈希」时，才允许删 C 中对应文件
            if h not in src:
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

            # 否则：源目录中至少有一个还有该资源 → 不删 C，对应哈希保留

        # 删除空目录
        try_remove_empty_dirs(TARGET_DIR)

        print(f"[SLEEP] {SCAN_INTERVAL} 秒后再次扫描\n")

    except Exception as e:
        print("[FATAL ERROR]", e)

    time.sleep(SCAN_INTERVAL)
