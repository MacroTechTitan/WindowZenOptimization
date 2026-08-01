"""AI Storage Report — READ ONLY.

Detects and sizes local AI/ML tool caches so the user can see where tens
or hundreds of GB have gone. This module contains NO deletion or pruning
code and routes/ai_storage.py exposes no destructive endpoint. Cache
management is explicitly out of scope for this sprint
(see docs/BACKLOG_PHASE2.md — "Model cache policy engine").
"""
import os
import json
import re
import threading
from datetime import datetime

from core.state import IS_WINDOWS
from core.util import log_activity, format_bytes


def _home():
    return os.path.expanduser("~")


def _dir_size(path):
    """(bytes, file_count) for a directory tree."""
    total = count = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                    count += 1
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total, count


def _entry(tool, path, present, size=0, files=0, models=None, note="",
           stale=0, extra=None):
    e = {
        "tool": tool,
        "path": path,
        "present": present,
        "bytes": size,
        "bytes_fmt": format_bytes(size),
        "files": files,
        "models": models or [],
        "stale_revisions": stale,
        "note": note,
    }
    if extra:
        e.update(extra)
    return e


# ─── Ollama ────────────────────────────────────────────────────
def scan_ollama():
    root = os.environ.get("OLLAMA_MODELS") or os.path.join(_home(), ".ollama", "models")
    if not os.path.isdir(root):
        return _entry("Ollama", root, False, note="Not installed / no models directory.")

    size, files = _dir_size(root)
    models = []
    manifests = os.path.join(root, "manifests")
    blobs = os.path.join(root, "blobs")

    blob_sizes = {}
    if os.path.isdir(blobs):
        try:
            for name in os.listdir(blobs):
                fp = os.path.join(blobs, name)
                try:
                    blob_sizes[name.replace("sha256-", "sha256:")] = os.path.getsize(fp)
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass

    if os.path.isdir(manifests):
        for dirpath, _, filenames in os.walk(manifests):
            for fname in filenames:
                mpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(mpath, manifests).replace(os.sep, "/")
                # registry.ollama.ai/library/<model>/<tag>
                parts = rel.split("/")
                label = f"{parts[-2]}:{parts[-1]}" if len(parts) >= 2 else rel
                total = 0
                try:
                    with open(mpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    layers = list(data.get("layers", []))
                    if data.get("config"):
                        layers.append(data["config"])
                    for layer in layers:
                        digest = layer.get("digest", "")
                        total += blob_sizes.get(digest, layer.get("size", 0) or 0)
                except Exception:
                    continue
                models.append({"name": label, "bytes": total,
                               "bytes_fmt": format_bytes(total)})

    models.sort(key=lambda m: m["bytes"], reverse=True)
    note = (f"{len(models)} model tag(s). Ollama shares blobs between tags, so the "
            f"per-model sizes can overlap and add up to more than the directory total.")
    return _entry("Ollama", root, True, size, files, models, note)


# ─── HuggingFace ───────────────────────────────────────────────
def scan_huggingface():
    root = (os.environ.get("HF_HOME")
            or os.environ.get("HUGGINGFACE_HUB_CACHE")
            or os.path.join(_home(), ".cache", "huggingface"))
    if not os.path.isdir(root):
        return _entry("HuggingFace", root, False, note="Not installed / no cache directory.")

    size, files = _dir_size(root)
    hub = os.path.join(root, "hub")
    scan_root = hub if os.path.isdir(hub) else root

    models = []
    stale_total = 0
    try:
        entries = [d for d in os.listdir(scan_root)
                   if d.startswith(("models--", "datasets--"))]
    except (OSError, PermissionError):
        entries = []

    for d in entries:
        mpath = os.path.join(scan_root, d)
        msize, mfiles = _dir_size(mpath)
        kind, _, name = d.partition("--")
        pretty = name.replace("--", "/")

        # Each snapshot dir is one revision; more than one means older
        # revisions are still on disk taking up space.
        snapshots = os.path.join(mpath, "snapshots")
        revisions = []
        if os.path.isdir(snapshots):
            try:
                revisions = sorted(os.listdir(snapshots))
            except (OSError, PermissionError):
                revisions = []
        orphaned = max(0, len(revisions) - 1)
        stale_total += orphaned

        models.append({
            "name": pretty,
            "kind": "dataset" if kind == "datasets" else "model",
            "bytes": msize,
            "bytes_fmt": format_bytes(msize),
            "files": mfiles,
            "revisions": len(revisions),
            "orphaned_revisions": orphaned,
        })

    models.sort(key=lambda m: m["bytes"], reverse=True)
    multi = [m for m in models if m["orphaned_revisions"] > 0]
    note = (f"{len(models)} cached repo(s). "
            + (f"{len(multi)} keep more than one revision on disk "
               f"({stale_total} orphaned revision(s) beyond the newest) — these are "
               f"the usual source of silent multi-GB growth."
               if multi else "No repo has more than one revision cached."))
    return _entry("HuggingFace", scan_root, True, size, files, models, note,
                  stale=stale_total)


# ─── LM Studio ─────────────────────────────────────────────────
def scan_lmstudio():
    candidates = [
        os.path.join(_home(), ".lmstudio", "models"),
        os.path.join(_home(), ".cache", "lm-studio", "models"),
    ]
    root = next((c for c in candidates if os.path.isdir(c)), candidates[0])
    if not os.path.isdir(root):
        return _entry("LM Studio", root, False, note="Not installed / no models directory.")

    size, files = _dir_size(root)
    models = []
    # Layout is <publisher>/<repo>/<file.gguf>
    try:
        for publisher in os.listdir(root):
            ppath = os.path.join(root, publisher)
            if not os.path.isdir(ppath):
                continue
            for repo in os.listdir(ppath):
                rpath = os.path.join(ppath, repo)
                if not os.path.isdir(rpath):
                    continue
                rsize, rfiles = _dir_size(rpath)
                models.append({"name": f"{publisher}/{repo}", "bytes": rsize,
                               "bytes_fmt": format_bytes(rsize), "files": rfiles})
    except (OSError, PermissionError):
        pass
    models.sort(key=lambda m: m["bytes"], reverse=True)
    return _entry("LM Studio", root, True, size, files, models,
                  f"{len(models)} local model repo(s).")


# ─── ComfyUI / Stable Diffusion checkpoints ────────────────────
COMFY_SUBDIRS = ("checkpoints", "loras", "vae", "controlnet", "clip",
                 "unet", "embeddings", "upscale_models")


def scan_comfyui():
    candidates = [
        os.path.join(_home(), "ComfyUI", "models"),
        os.path.join(_home(), "Documents", "ComfyUI", "models"),
        os.path.join(_home(), "AppData", "Local", "Programs", "ComfyUI", "models"),
        os.path.join(_home(), "stable-diffusion-webui", "models"),
    ]
    root = next((c for c in candidates if os.path.isdir(c)), None)
    if not root:
        return _entry("ComfyUI / SD checkpoints", candidates[0], False,
                      note="No ComfyUI or Stable Diffusion models directory found.")

    size, files = _dir_size(root)
    models = []
    for sub in COMFY_SUBDIRS:
        spath = os.path.join(root, sub)
        if not os.path.isdir(spath):
            continue
        ssize, sfiles = _dir_size(spath)
        if sfiles:
            models.append({"name": sub, "bytes": ssize,
                           "bytes_fmt": format_bytes(ssize), "files": sfiles})
    models.sort(key=lambda m: m["bytes"], reverse=True)
    return _entry("ComfyUI / SD checkpoints", root, True, size, files, models,
                  f"{len(models)} model categor(ies) in use.")


# ─── pip / conda / torch ───────────────────────────────────────
def scan_pip_cache():
    root = (os.environ.get("PIP_CACHE_DIR")
            or os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(_home(), "AppData", "Local")),
                            "pip", "Cache"))
    if not os.path.isdir(root):
        alt = os.path.join(_home(), ".cache", "pip")
        root = alt if os.path.isdir(alt) else root
    if not os.path.isdir(root):
        return _entry("pip cache", root, False, note="No pip cache directory found.")
    size, files = _dir_size(root)
    return _entry("pip cache", root, True, size, files, [],
                  "Downloaded wheels kept for reinstall speed.")


def scan_conda_cache():
    candidates = []
    for base in (os.environ.get("CONDA_PKGS_DIRS"),
                 os.path.join(_home(), "anaconda3", "pkgs"),
                 os.path.join(_home(), "miniconda3", "pkgs"),
                 os.path.join(_home(), ".conda", "pkgs"),
                 os.path.join(_home(), "miniforge3", "pkgs")):
        if base:
            candidates.extend(base.split(os.pathsep))
    root = next((c for c in candidates if c and os.path.isdir(c)), None)
    if not root:
        return _entry("conda pkgs cache", candidates[0] if candidates else "", False,
                      note="No conda package cache found.")
    size, files = _dir_size(root)
    return _entry("conda pkgs cache", root, True, size, files, [],
                  "Extracted and tarball conda packages.")


def scan_torch_hub():
    root = (os.environ.get("TORCH_HOME")
            or os.path.join(_home(), ".cache", "torch"))
    if not os.path.isdir(root):
        return _entry("torch hub cache", root, False, note="No torch cache directory found.")
    size, files = _dir_size(root)
    models = []
    for sub in ("hub", "checkpoints", os.path.join("hub", "checkpoints")):
        spath = os.path.join(root, sub)
        if os.path.isdir(spath):
            ssize, sfiles = _dir_size(spath)
            if sfiles:
                models.append({"name": sub, "bytes": ssize,
                               "bytes_fmt": format_bytes(ssize), "files": sfiles})
    return _entry("torch hub cache", root, True, size, files, models,
                  "Pretrained weights downloaded by torch.hub / torchvision.")


SCANNERS = (
    scan_ollama,
    scan_huggingface,
    scan_lmstudio,
    scan_comfyui,
    scan_pip_cache,
    scan_conda_cache,
    scan_torch_hub,
)

ai_storage_results = {
    "status": "idle",
    "tools": [],
    "total_bytes": 0,
    "total_fmt": "0 B",
    "detected": 0,
    "stale_revisions": 0,
    "last_scan": None,
    "read_only": True,
}

_lock = threading.Lock()


def scan_ai_storage():
    """Build the full read-only report. Deletes and prunes nothing."""
    log_activity("AI Storage Report started (read-only)", "TASK")
    tools = []
    for fn in SCANNERS:
        try:
            tools.append(fn())
        except Exception as e:
            log_activity(f"AI Storage: {fn.__name__} failed: {e}", "WARN")

    present = [t for t in tools if t["present"]]
    total = sum(t["bytes"] for t in present)
    stale = sum(t.get("stale_revisions", 0) for t in present)
    present.sort(key=lambda t: t["bytes"], reverse=True)
    missing = [t for t in tools if not t["present"]]

    with _lock:
        ai_storage_results.update({
            "status": "complete",
            "tools": present + missing,
            "total_bytes": total,
            "total_fmt": format_bytes(total),
            "detected": len(present),
            "stale_revisions": stale,
            "last_scan": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "read_only": True,
            "platform_supported": IS_WINDOWS,
        })

    log_activity(f"AI Storage Report complete — {len(present)} tool(s) detected, "
                 f"{format_bytes(total)} total, {stale} orphaned revision(s)", "SUCCESS")
    return dict(ai_storage_results)
