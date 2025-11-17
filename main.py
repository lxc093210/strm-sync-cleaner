import os
import time
import hashlib
import threading
from datetime import datetime
from collections import deque

from flask import Flask, jsonify, render_template_string

# ========= 配置 =========
# 未整理 STRM（导出目录）
SOURCE_DIR = "/raw"
# 整理后 STRM + NFO 目录
TARGET_DIR = "/sorted"

EXT = ".strm"
SCAN_INTERVAL = 5  # 秒

# Web 端口（容器内部）
WEB_PORT = 8000

# 要额外删除的封面图扩展名（可以自己再加）
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ========= 内存事件日志（给 Web UI 用） =========
# 最近 200 条操作记录
events = deque(maxlen=200)


def add_event(level: str, message: str):
    """记录一条事件：打印到控制台 + 写入内存队列（给 Web UI 用）"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {message}"
    print(line, flush=True)
    events.appendleft({"time": ts, "level": level, "message": message})


# ========= 读取 STRM 文件内容 hash，用于匹配 =========
def strm_hash(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    except Exception as e:
        add_event("WARN", f"计算哈希失败: {path} -> {e}")
        return None


# ========= 构建某个目录下所有 .strm 的索引 =========
def build_index(root: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    if not os.path.exists(root):
        add_event("WARN", f"目录不存在: {root}")
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


# ========= 删除空目录 =========
def cleanup_empty_dirs(root: str) -> list[str]:
    """
    删除 root 下的空目录，返回删除掉的目录列表。
    只删完全空的目录（没有文件、没有子目录）。
    """
    removed: list[str] = []
    if not os.path.exists(root):
        return removed

    # bottom-up 遍历，先从最里层开始删
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        # 跳过根目录本身
        if dirpath == root:
            continue

        if not dirnames and not filenames:
            try:
                os.rmdir(dirpath)
                removed.append(dirpath)
            except OSError:
                # 可能被别的进程占用，忽略即可
                pass

    return removed


# ========= 删除“孤儿目录”里的封面图 =========
def cleanup_sidecar_images_if_orphan(dirpath: str) -> list[str]:
    """
    如果这个目录里已经没有任何 .strm 文件，
    就把 IMAGE_EXTS 里定义的封面图一起删掉。
    返回删除掉的文件路径列表。
    """
    removed: list[str] = []

    if not os.path.isdir(dirpath):
        return removed

    try:
        entries = os.listdir(dirpath)
    except OSError:
        return removed

    # 如果目录里还有其他 .strm，就不要动封面图
    for name in entries:
        if name.lower().endswith(EXT):
            return removed

    # 没有 .strm 了，可以清理封面图
    for name in entries:
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXTS:
            continue

        path = os.path.join(dirpath, name)
        if not os.path.isfile(path):
            continue

        try:
            os.remove(path)
            removed.append(path)
        except Exception as e:
            add_event("ERR", f"删除封面文件失败: {path} -> {e}")

    return removed


# ========= 主循环：根据哈希同步删除 + 清理封面 + 清理空目录 =========
def scanner_loop():
    print("=== STRM Sync Cleaner Started ===", flush=True)
    print(f"Source (未整理目录): {SOURCE_DIR}", flush=True)
    print(f"Target (整理后目录): {TARGET_DIR}", flush=True)
    print("================================", flush=True)

    add_event("INFO", "扫描线程已启动")

    while True:
        try:
            source_index = build_index(SOURCE_DIR)
            target_index = build_index(TARGET_DIR)

            info_msg = (
                f"本轮扫描：源目录 {len(source_index)} 条哈希，"
                f"目标目录 {len(target_index)} 条哈希"
            )
            add_event("INFO", info_msg)

            # 遍历目标目录中的所有哈希，如果在源目录中找不到，就认为是“孤立的”
            for h, target_paths in target_index.items():
                if h in source_index:
                    continue

                for strm_path in target_paths:
                    # 1. 删除目标目录中的 .strm
                    if os.path.exists(strm_path):
                        try:
                            os.remove(strm_path)
                            add_event("DEL", f"STRM: {strm_path}")
                        except Exception as e:
                            add_event("ERR", f"删除 STRM 失败: {strm_path} -> {e}")

                    # 2. 删除同名 .nfo
                    base, _ = os.path.splitext(strm_path)
                    nfo_path = base + ".nfo"
                    if os.path.exists(nfo_path):
                        try:
                            os.remove(nfo_path)
                            add_event("DEL", f"NFO : {nfo_path}")
                        except Exception as e:
                            add_event("ERR", f"删除 NFO 失败: {nfo_path} -> {e}")

                    # 3. 如果目录里已经没有别的 .strm 了，把封面 jpg/png 一起删掉
                    dirpath = os.path.dirname(strm_path)
                    removed_imgs = cleanup_sidecar_images_if_orphan(dirpath)
                    for p in removed_imgs:
                        add_event("DEL", f"封面: {p}")

            # 4. 全局清理整理目录中的空目录
            removed_dirs = cleanup_empty_dirs(TARGET_DIR)
            if removed_dirs:
                for d in removed_dirs:
                    add_event("DEL", f"空目录: {d}")
            else:
                add_event("INFO", "本轮未发现可删除的空目录")

            add_event("SLEEP", f"{SCAN_INTERVAL} 秒后再次扫描")
        except Exception as e:
            add_event("FATAL", f"主循环异常: {e}")

        time.sleep(SCAN_INTERVAL)


# ========= Web UI =========
app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>STRM Sync Cleaner</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 20px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 14px; }
    th { background: #f4f4f4; }
    tr:nth-child(even) { background: #fafafa; }
    .level-INFO { color: #333; }
    .level-DEL  { color: #006400; }
    .level-ERR, .level-FATAL { color: #b22222; font-weight: bold; }
    .level-WARN { color: #d2691e; }
    .level-SLEEP { color: #888; font-style: italic; }
    .footer { margin-top: 10px; font-size: 12px; color: #666; }
  </style>
</head>
<body>
  <h1>STRM Sync Cleaner</h1>
  <p>最近 {{ events|length }} 条记录（最新在最上面）</p>
  <table>
    <thead>
      <tr>
        <th style="width: 150px;">时间</th>
        <th style="width: 80px;">级别</th>
        <th>内容</th>
      </tr>
    </thead>
    <tbody>
      {% for e in events %}
      <tr>
        <td>{{ e.time }}</td>
        <td class="level-{{ e.level }}">{{ e.level }}</td>
        <td style="word-break: break-all;">{{ e.message }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="footer">
    <p>每 {{ scan_interval }} 秒扫描一次。接口：
      <code>/api/events</code> 返回 JSON。</p>
  </div>
</body>
</html>
"""


@app.get("/")
def index():
    # 直接用内存队列渲染页面
    return render_template_string(
        INDEX_HTML,
        events=list(events),
        scan_interval=SCAN_INTERVAL,
    )


@app.get("/api/events")
def api_events():
    # 提供简单 JSON 接口
    return jsonify(list(events))


def main():
    # 启动扫描线程
    t = threading.Thread(target=scanner_loop, daemon=True)
    t.start()

    # 启动 Web 服务器（阻塞）
    add_event("INFO", f"Web UI 启动，端口 {WEB_PORT}")
    app.run(host="0.0.0.0", port=WEB_PORT, threaded=True)


if __name__ == "__main__":
    main()
