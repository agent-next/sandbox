/* nanousd_dump.c — dump a USDA stage read through the pinned nanousd
 * C API as JSON, for the nanousd-render judge (cookbook/nanousd-render).
 *
 * Usage: nanousd_dump <path/to/libnanousd.so> <scene.usda>
 * The backend path is pinned via NANOUSD_BACKEND because the nanousdapi
 * loader otherwise searches next to the *executable*, and the judge keeps
 * its binary apart from the library.
 *
 * Output: one JSON object on stdout:
 *   {"error": "..."} if the stage does not open, else a stage record:
 *   {"prims":[{"path":..,"type":..,"defined":0|1,"xform":[16 doubles],
 *              "xform_ok":0|1,"attribs":{name:{"type":..,"value":..}}}]}
 * prims is the FLAT list nanousd_nprims() returns (nanousd's traversal
 * enumerates every prim in the stage); no children key.
 * attribs holds only the judge-probed attribute names that return a
 * readable value; local transforms are nanousd_get_local_transform()
 * at time 0.
 *
 * Part of the judge; built by judge/setup.sh against the pinned nanousd.
 */
#define _POSIX_C_SOURCE 200112L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <nanousd/nanousdapi.h>

static void print_json_string(const char* s) {
    putchar('"');
    for (const char* p = s; *p; p++) {
        unsigned char c = (unsigned char)*p;
        if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
        else if (c < 0x20) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}

static void print_flat_f(const float* v, int n) {
    printf("[");
    for (int i = 0; i < n; i++) printf("%s%.9g", i ? "," : "", v[i]);
    printf("]");
}
static void print_flat_d(const double* v, int n) {
    printf("[");
    for (int i = 0; i < n; i++) printf("%s%.17g", i ? "," : "", v[i]);
    printf("]");
}
static void print_flat_i(const int* v, int n) {
    printf("[");
    for (int i = 0; i < n; i++) printf("%s%d", i ? "," : "", v[i]);
    printf("]");
}

static void dump_attrib(NanousdPrim prim, const char* name) {
    const char* t = nanousd_attribtype(prim, name);
    printf("{\"type\":");
    if (t) print_json_string(t); else printf("\"?\"");
    printf(",\"value\":");
    const char* at = t ? t : "";
    int printed = 0;
    int is_arr = strstr(at, "[]") != NULL;

    if (is_arr) {
        int n = nanousd_attribarraylen(prim, name);
        if (n > 0) {
            if (strstr(at, "3f")) {
                /* point3f[], color3f[], float3[], normal3f[], ... */
                float* f = (float*)malloc((size_t)n * 3 * sizeof(float));
                if (f && nanousd_attribarrayv3f(prim, name, f, n) == n) {
                    print_flat_f(f, n * 3); printed = 1;
                }
                if (f) free(f);
            } else if (strstr(at, "3d")) {
                double* dv = (double*)malloc((size_t)n * 3 * sizeof(double));
                if (dv && nanousd_attribarrayv3d(prim, name, dv, n) == n) {
                    print_flat_d(dv, n * 3); printed = 1;
                }
                if (dv) free(dv);
            } else if (strstr(at, "float") || strstr(at, "half")) {
                float* f = (float*)malloc((size_t)n * sizeof(float));
                if (f && nanousd_attribarrayf(prim, name, f, n)) {
                    print_flat_f(f, n); printed = 1;
                }
                if (f) free(f);
            } else if (strstr(at, "double")) {
                double* dv = (double*)malloc((size_t)n * sizeof(double));
                if (dv && nanousd_attribarrayd(prim, name, dv, n)) {
                    print_flat_d(dv, n); printed = 1;
                }
                if (dv) free(dv);
            } else if (strstr(at, "int")) {
                int* iv = (int*)malloc((size_t)n * sizeof(int));
                if (iv && nanousd_attribarrayi(prim, name, iv, n)) {
                    print_flat_i(iv, n); printed = 1;
                }
                if (iv) free(iv);
            }
            /* token[] / string[] stay null — the judge only needs them to
             * confirm presence, and it reads the authored list itself. */
        }
    } else {
        int ok = 0;
        if (strstr(at, "float3") || strstr(at, "point3") || strstr(at, "color3")
            || strstr(at, "normal3") || strstr(at, "vector3")) {
            float v[3];
            if (nanousd_attribv3f(prim, name, v)) { print_flat_f(v, 3); printed = 1; }
        } else if (strstr(at, "double3")) {
            double v[3];
            if (nanousd_attribv3d(prim, name, v)) { print_flat_d(v, 3); printed = 1; }
        } else if (strstr(at, "float2") || strstr(at, "texCoord2")) {
            float v[2];
            if (nanousd_attribv2f(prim, name, v)) { print_flat_f(v, 2); printed = 1; }
        } else if (strstr(at, "double2")) {
            double v[2];
            if (nanousd_attribv2d(prim, name, v)) { print_flat_d(v, 2); printed = 1; }
        } else if (strstr(at, "double")) {
            double v = nanousd_attribd(prim, name, &ok);
            if (ok) { printf("%.17g", v); printed = 1; }
        } else if (strstr(at, "float") || strstr(at, "half")) {
            float v = nanousd_attribf(prim, name, &ok);
            if (ok) { printf("%.9g", v); printed = 1; }
        } else if (strstr(at, "int")) {
            int v = nanousd_attribi(prim, name, &ok);
            if (ok) { printf("%d", v); printed = 1; }
        } else if (strstr(at, "bool")) {
            int v = nanousd_attribb(prim, name, &ok);
            if (ok) { printf("%d", v); printed = 1; }
        } else {
            const char* s = nanousd_attribs(prim, name, &ok);
            if (ok && s) { print_json_string(s); printed = 1; }
        }
    }
    if (!printed) printf("null");
    printf("}");
}

/* The judge passes a fixed list of attribute names to probe on every prim
 * (nanousd_attribname returns type names, not property names, so we query
 * by name with nanousd_hasattrib). Names travel via a comma-separated env
 * var read once at startup. */
static char g_attr_names[64][64];
static int  g_n_attr = 0;

static void load_attr_names(void) {
    const char* env = getenv("NANOUSD_DUMP_ATTRS");
    if (!env) env = "points,faceVertexCounts,faceVertexIndices,primvars:displayColor,focalLength,horizontalAperture,verticalAperture,clippingRange,inputs:intensity";
    char buf[4096];
    strncpy(buf, env, sizeof(buf) - 1); buf[sizeof(buf) - 1] = 0;
    char* save = NULL;
    for (char* tok = strtok_r(buf, ",", &save); tok && g_n_attr < 64;
         tok = strtok_r(NULL, ",", &save)) {
        strncpy(g_attr_names[g_n_attr], tok, 63);
        g_attr_names[g_n_attr][63] = 0;
        g_n_attr++;
    }
}

static void dump_prim(NanousdPrim prim, int* first) {
    if (!nanousd_prim_isvalid(prim)) return;
    const char* path = nanousd_path(prim);
    const char* type = nanousd_typename(prim);
    printf("%s{\"path\":", *first ? "" : ",");
    print_json_string(path ? path : "?");
    printf(",\"type\":");
    print_json_string(type ? type : "?");
    printf(",\"defined\":%d,\"xform\":[", nanousd_isdefined(prim));
    double xf[16];
    int reset = 0;
    int xok = nanousd_get_local_transform(prim, 0.0, xf, &reset);
    if (xok) {
        for (int i = 0; i < 16; i++) printf("%s%.17g", i ? "," : "", xf[i]);
    } else {
        for (int i = 0; i < 16; i++) printf("%s0", i ? "," : "");
    }
    printf("],\"xform_ok\":%d,\"xform_reset\":%d,\"attribs\":{", xok, reset);
    int emitted = 0;
    for (int i = 0; i < g_n_attr; i++) {
        if (!nanousd_hasattrib(prim, g_attr_names[i])) continue;
        /* only emit if it has a readable value (skip schema fallbacks that
         * answer hasattrib=1 with a null payload) */
        printf("%s", emitted ? "," : "");
        print_json_string(g_attr_names[i]);
        printf(":");
        dump_attrib(prim, g_attr_names[i]);
        emitted = 1;
    }
    printf("}}");
    *first = 0;
}

int main(int argc, char** argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: nanousd_dump <libnanousd.so> <scene.usda>\n");
        return 2;
    }
    load_attr_names();
    if (setenv("NANOUSD_BACKEND", argv[1], 1) != 0) {
        fprintf(stderr, "nanousd_dump: setenv failed\n");
        return 2;
    }
    NanousdStage stage = nanousd_open(argv[2]);
    if (!nanousd_isvalid(stage)) {
        const char* err = nanousd_error(stage);
        printf("{\"error\":");
        if (err) print_json_string(err); else printf("\"open failed\"");
        printf("}\n");
        nanousd_close(stage);
        return 1;
    }
    printf("{\"prims\":[");
    int first = 1;
    int n = nanousd_nprims(stage);
    for (int i = 0; i < n; i++) {
        NanousdPrim prim = nanousd_prim(stage, i);
        dump_prim(prim, &first);
        nanousd_freeprim(prim);
    }
    printf("]}\n");
    nanousd_close(stage);
    return 0;
}
