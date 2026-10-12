# -*- coding: utf-8 -*-
"""03 从 ModelScope 下载 Qwen3-Embedding-0.6B（课件第三课 P15 推荐的起步模型）。
不翻墙、不花钱；纯 CPU 可跑，1024 维。
用法：python 03_download_model.py
"""
import json
import os
import sys
import time

import requests

# 模型可从命令行换：python 03_download_model.py BAAI/bge-base-zh-v1.5
# 默认用小模型，原因见 README「为什么用 bge-small」：
# 实测 Qwen3-Embedding-0.6B 在这台笔记本上纯 CPU 编 9555 块要 5 小时
# （每块 18.9 CPU 秒），bge-small-zh-v1.5 只要十几分钟。
MODEL = sys.argv[1] if len(sys.argv) > 1 else "BAAI/bge-small-zh-v1.5"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(BASE, "models", MODEL.split("/")[-1])
SKIP_EXT = (".onnx", ".msgpack", ".h5", ".tflite", ".gguf")
SKIP_NAME = ("README.md", ".gitattributes")

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})


def list_files():
    u = f"https://www.modelscope.cn/api/v1/models/{MODEL}/repo/files"
    r = s.get(u, params={"Revision": "master", "Recursive": "True"}, timeout=30)
    r.raise_for_status()
    data = r.json()["Data"]["Files"]
    # 有的仓库同时放了 model.safetensors 和 pytorch_model.bin（同样内容两份）。
    # SentenceTransformer 优先读 safetensors，所以有 safetensors 就别下 .bin，省一半流量。
    has_st = any(f["Path"].endswith("model.safetensors") for f in data)
    out = []
    for f in data:
        p = f["Path"]
        if f.get("Type") != "blob":
            continue
        if has_st and p.endswith("pytorch_model.bin"):
            continue
        if p.endswith(SKIP_EXT) or os.path.basename(p) in SKIP_NAME:
            continue
        out.append((p, f.get("Size", 0)))
    return out


def download(path, size, retries=40):
    """带断点续传 + 自动重试：本机网络（Clash TUN）大文件常中途断，
    实测 1.19GB 的 safetensors 下到 138MB 就 IncompleteRead。"""
    dst = os.path.join(DEST, path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        print(f"  跳过 {path}")
        return True
    tmp = dst + ".part"
    u = f"https://www.modelscope.cn/api/v1/models/{MODEL}/repo"
    t0 = time.time()
    for attempt in range(1, retries + 1):
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if have >= size:
            break
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            r = s.get(u, params={"Revision": "master", "FilePath": path},
                      headers=headers, timeout=(30, 120), stream=True)
            r.raise_for_status()
            mode = "ab" if (have and r.status_code == 206) else "wb"
            if mode == "wb":
                have = 0
            with open(tmp, mode) as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        except Exception as e:
            print(f"  [{path}] 第{attempt}次中断于 {have/1e6:.0f}MB "
                  f"({type(e).__name__})，2秒后续传")
            time.sleep(2)
    final = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    if final == size:
        os.replace(tmp, dst)
        print(f"  OK {path}  {final/1e6:.1f}MB  {time.time()-t0:.0f}s")
        return True
    print(f"  失败 {path}: {final/1e6:.1f}MB / {size/1e6:.1f}MB")
    return False


def main():
    os.makedirs(DEST, exist_ok=True)
    files = list_files()
    print(f"共 {len(files)} 个文件，合计 {sum(sz for _,sz in files)/1e6:.0f}MB")
    for p, sz in files:
        download(p, sz)
    print("模型就绪:", DEST)


if __name__ == "__main__":
    main()
