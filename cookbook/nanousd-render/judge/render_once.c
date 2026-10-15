/* render_once.c — render a USDA scene headlessly through the pinned
 * nanousd-opengl-renderer's public viewer.h API and write raw RGBA8.
 *
 * Part of the judge for cookbook/nanousd-render. The judge's Python side
 * computes the view/proj matrices (numpy pinhole math) and hands them to
 * this driver as a little binary float file, so ALL camera math lives in
 * the independent oracle, none of it here.
 *
 * Usage:
 *   render_once <scene.usda> <cam.bin> <out1.raw> <out2.raw>
 * where cam.bin is 39 float32: view16 (col-major), proj16 (col-major),
 * eye3, width, height, pad, render_mode (raster=0, material=1). The scene
 * is rendered twice into two separate buffers so the judge can assert
 * byte-determinism (G3).
 *
 * Exit codes: 0 ok, 1 render failure (message on stderr).
 */
#include "viewer.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static float* read_f32(const char* path, size_t expect) {
    FILE* f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "render_once: cannot open %s\n", path); return NULL; }
    float* v = (float*)malloc(expect * sizeof(float));
    if (!v || fread(v, sizeof(float), expect, f) != expect) {
        fprintf(stderr, "render_once: %s must hold %zu float32\n", path, expect);
        free(v); fclose(f); return NULL;
    }
    fclose(f);
    return v;
}

static int write_raw(const char* path, const unsigned char* buf, size_t n) {
    FILE* f = fopen(path, "wb");
    if (!f) { fprintf(stderr, "render_once: cannot write %s\n", path); return 0; }
    size_t w = fwrite(buf, 1, n, f);
    fclose(f);
    return w == n;
}

int main(int argc, char** argv) {
    if (argc != 5) {
        fprintf(stderr,
            "usage: render_once <scene.usda> <cam.bin> <out1.raw> <out2.raw>\n");
        return 2;
    }
    const int N_FLOATS = 16 + 16 + 3 + 4; /* view, proj, eye, w/h/pad/mode */
    float* cam = read_f32(argv[2], (size_t)N_FLOATS);
    if (!cam) return 1;

    float* view = cam;
    float* proj = cam + 16;
    float* eye  = cam + 32;
    int   w     = (int)(cam[35] + 0.5f);
    int   h     = (int)(cam[36] + 0.5f);
    int   mode  = (int)(cam[38] + 0.5f);  /* [37] unused pad */
    if (w <= 0 || h <= 0 || w > 4096 || h > 4096) {
        fprintf(stderr, "render_once: bad render size %dx%d\n", w, h);
        free(cam);
        return 1;
    }

    Viewer* v = viewer_create(argv[1], w, h, /*max_tex_size=*/64,
                             /*envmap_path=*/NULL, /*headless=*/1,
                             /*enable_materials=*/1);
    if (!v) {
        fprintf(stderr, "render_once: viewer_create failed (no EGL device / bad file?)\n");
        free(cam);
        return 1;
    }
    viewer_resize(v, w, h);
    viewer_set_overlay_enabled(v, 0);     /* no HUD: it defeats determinism */
    viewer_set_render_mode(v,
        mode == 1 ? VIEWER_MODE_MATERIAL : VIEWER_MODE_RASTER);
    viewer_set_tone_mapping(v, 1.0f, 1.0f, 1.0f, 0u);

    size_t npix = (size_t)w * h * 4;
    unsigned char* a = (unsigned char*)malloc(npix);
    unsigned char* b = (unsigned char*)malloc(npix);
    if (!a || !b) { fprintf(stderr, "render_once: alloc failed\n"); goto fail; }

    if (!viewer_render_to_rgba(v, w, h, view, proj, eye, a)) {
        fprintf(stderr, "render_once: first render failed\n");
        goto fail;
    }
    if (!viewer_render_to_rgba(v, w, h, view, proj, eye, b)) {
        fprintf(stderr, "render_once: second render failed\n");
        goto fail;
    }
    if (memcmp(a, b, npix) != 0) {
        fprintf(stderr, "render_once: two renders differ (non-deterministic)\n");
        goto fail;
    }
    int ok = write_raw(argv[3], a, npix) && write_raw(argv[4], b, npix);
    if (!ok) goto fail;
    printf("%d %d\n", w, h);

    free(a); free(b); free(cam);
    viewer_destroy(v);
    return 0;

fail:
    free(a); free(b); free(cam);
    viewer_destroy(v);
    return 1;
}
