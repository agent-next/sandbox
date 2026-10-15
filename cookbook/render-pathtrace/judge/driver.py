"""Local-only WebGPU bridge. The artifact is data, never browser source."""

import base64
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading

import numpy as np
from playwright.sync_api import sync_playwright

ROOT = Path.home() / ".local/share/render-pathtrace"
HERE = Path(__file__).resolve().parent


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class Renderer:
    def __init__(self, backend="cpu", api="webgpu"):
        self.backend = backend
        self.api = api

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pathtrace-serve-")
        serve = Path(self.temp.name)
        shutil.copy2(HERE / "harness.html", serve / "index.html")
        (serve / "dist").symlink_to(ROOT / "package/dist", target_is_directory=True)
        handler = functools.partial(QuietHandler, directory=str(serve))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/ms-playwright")
        self.pw = sync_playwright().start()
        args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                "--enable-unsafe-webgpu"]
        if self.backend == "cpu":
            args += ["--enable-unsafe-swiftshader", "--use-webgpu-adapter=swiftshader",
                     "--disable-gpu-watchdog"]
        else:
            args += ["--enable-features=Vulkan", "--use-angle=vulkan",
                     "--ignore-gpu-blocklist", "--disable-vulkan-surface"]
        try:
            self.browser = self.pw.chromium.launch(
                channel="chromium", headless=True, args=args
            )
            self.page = self.browser.new_page()
            self.page.set_default_timeout(130000)
            port = self.server.server_address[1]
            # Block external URLs, including any unexpected upstream asset fallback.
            origin = f"http://localhost:{port}"
            self.page.route("**/*", lambda route: route.continue_()
                            if route.request.url.startswith(origin + "/")
                            else route.abort())
            self.page.goto(origin)
            self.page.wait_for_function("typeof renderScene === 'function'")
            if self.backend == "gpu":
                # Chromium silently falls back to SwiftShader when the NVIDIA device
                # cannot be created; fail in seconds instead of rendering in software.
                vendor = self.page.evaluate(
                    "async () => (await navigator.gpu?.requestAdapter("
                    "{powerPreference: 'high-performance'}))?.info?.vendor ?? null")
                if vendor != "nvidia":
                    raise RuntimeError(f"GPU backend requested but the WebGPU adapter is "
                                       f"{vendor!r}, not NVIDIA")
            self.version = self.browser.version
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def render(self, scene, spp, seed):
        try:
            result = self.page.evaluate(
                "async ([scene,spp,seed,api]) => await renderScene(scene,spp,seed,api)",
                [scene, spp, seed, self.api],
            )
        except Exception:
            try:
                self.info = self.page.evaluate(
                    "() => window.renderInfo || {}"
                )
            except Exception:
                self.info = {"backend": self.api, "adapter": "unavailable"}
            raise
        assert result["backend"] == self.api, result
        if self.backend == "cpu":
            identity = json.dumps([result["adapter"], result.get("adapter_info")]).lower()
            assert "swiftshader" in identity, "CPU adapter identity is not SwiftShader"
        else:
            info = result.get("adapter_info") or {}
            assert info.get("vendor", "").lower() == "nvidia", \
                f"GPU adapter is not NVIDIA: {info}"
            assert "swiftshader" not in json.dumps(info).lower(), \
                "GPU adapter is SwiftShader"
        assert result["samples"] == spp, result["samples"]
        self.info = {k: result[k] for k in ("backend", "adapter", "adapter_info")}
        image = np.frombuffer(base64.b64decode(result["data"]), dtype="<f4")
        image = image.reshape(result["height"], result["width"], 4).copy()
        assert [result["width"], result["height"]] == scene["resolution"], \
            "unexpected HDR dimensions"
        if not np.isfinite(image).all():
            raise ValueError(f"nonfinite HDR values: {int((~np.isfinite(image)).sum())}")
        return image

    def __exit__(self, *args):
        if hasattr(self, "browser"):
            self.browser.close()
        self.pw.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()
