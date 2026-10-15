/* nanousd_dump.c — dump a USDA/USDC stage read through the pinned nanousd
 * C API as JSON, for the nanousd-render judge (cookbook/nanousd-render).
 *
 * Usage: nanousd_dump <scene.usda>
 * Output: one JSON object per line on stdout:
 *   {"error": "..."} if the stage does not open, else a stage record:
 *   {"prims":[{"path":..,"type":..,"defined":0|1,"xform":[16 doubles],
 *              "attribs":{name:{"type":..,"f":[..]|"i":[..]|"d":[..]|"s":".."}}}]}
 * Local transforms are nanousd_get_local_transform() at time 0 (out[16]).
 *
 * Part of the judge; built by judge/setup.sh against the pinned nanousd.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <nanousd/nanousdapi.h>

static void dump_attrib(NanousdPrim prim, const char* name) {
    const char* t = nanousd_attribtype(prim, name);
    printf("{\"type\":\"%s\",\"value\":", t ? t : "?");
    int n = nanousd_attribarraylen(prim, name);
    if (n > 0) {
        /* array-typed attribute: try float, then int, then double payloads */
        float* f = (float*)malloc((size_t)n * sizeof(float));
        if (f && nanousd_attribarrayf(prim, name, f, n)) {
            printf("[");
            for (int i = 0; i < n; i++) printf("%s%.9g", i ? "," : "", f[i]);
            printf("]");
        } else if (f) {
            int* iv = (int*)malloc((size_t)n * sizeof(int));
            if (iv && nanousd_attribarrayi(prim, name, iv, n)) {
                printf("[");
                for (int i = 0; i < n; i++) printf("%s%d", i ? "," : "", iv[i]);
                printf("]");
            } else if (iv) {
                double* dv = (double*)malloc((size_t)n * sizeof(double));
                if (dv && nanousd_attribarrayd(prim, name, dv, n)) {
                    printf("[");
                    for (int i = 0; i < n; i++) printf("%s%.17g", i ? "," : "", dv[i]);
                    printf("]");
                } else {
                    printf("null");
                }
                free(dv);
            }
            free(iv);
        } else {
            printf("null");
        }
        free(f);
    } else {
        /* scalar, keyed on the reported type string */
        int ok = 0;
        const char* at = t ? t : "";
        if (strstr(at, "double")) {
            printf("%.17g", nanousd_attribd(prim, name, &ok));
        } else if (strstr(at, "int")) {
            printf("%d", nanousd_attribi(prim, name, &ok));
        } else if (strstr(at, "float")) {
            printf("%.9g", nanousd_attribf(prim, name, &ok));
        } else if (strstr(at, "bool")) {
            printf("%d", nanousd_attribi(prim, name, &ok));
        } else {
            /* string / token / anything else */
            const char* s = nanousd_attribs(prim, name, &ok);
            if (ok && s) {
                printf("\"");
                for (const char* p = s; *p; p++) {
                    if (*p == '"' || *p == '\\') putchar('\\');
                    putchar(*p);
                }
                printf("\"");
            }
        }
        if (!ok) printf("null");
    }
    printf("}");
}

static void dump_prim(NanousdPrim prim, int* first) {
    if (!nanousd_prim_isvalid(prim)) return;
    const char* path = nanousd_path(prim);
    const char* type = nanousd_typename(prim);
    printf("%s{\"path\":\"%s\",\"type\":\"%s\",\"defined\":%d,\"xform\":[",
           *first ? "" : ",", path ? path : "?", type ? type : "?",
           nanousd_isdefined(prim));
    double xf[16];
    int reset = 0;
    if (nanousd_get_local_transform(prim, 0.0, xf, &reset)) {
        for (int i = 0; i < 16; i++) printf("%s%.17g", i ? "," : "", xf[i]);
    } else {
        for (int i = 0; i < 16; i++) printf("%s0", i ? "," : "");
        /* identity marker: xform present but not readable -> judge fails */
    }
    printf("],\"xform_ok\":%d,\"attribs\":{", nanousd_get_local_transform(prim, 0.0, xf, &reset));
    int na = nanousd_nattribs(prim);
    for (int i = 0; i < na; i++) {
        const char* name = nanousd_attribname(prim, i);
        if (!name) continue;
        printf("%s\"%s\":", i ? "," : "", name);
        dump_attrib(prim, name);
    }
    printf("}");
    *first = 0;
    int nc = nanousd_nchildren(prim);
    for (int c = 0; c < nc; c++) {
        NanousdPrim ch = nanousd_child(prim, c);
        dump_prim(ch, first);
        nanousd_freeprim(ch);
    }
}

int main(int argc, char** argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: nanousd_dump <scene.usda>\n");
        return 2;
    }
    NanousdStage stage = nanousd_open(argv[1]);
    if (!nanousd_isvalid(stage)) {
        const char* err = nanousd_error(stage);
        printf("{\"error\":\"%s\"}\n", err ? err : "open failed");
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
