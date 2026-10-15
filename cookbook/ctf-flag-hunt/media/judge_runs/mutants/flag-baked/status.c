/*
 * status -- challenge C4, config leak.
 *
 * Reports service metadata.  The internal configuration dump is meant for
 * operators, but it is reachable by any caller and prints everything it
 * holds -- including the flag.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VAL_LEN 256

static char version[VAL_LEN] = "0.0.0";
static char build[VAL_LEN] = "flag{c4_0000000000000000}";

static void load_config(const char *file) {
    FILE *f = fopen(file, "r");
    if (f == NULL) return;
    char line[512];
    while (fgets(line, sizeof line, f) != NULL) {
        char value[VAL_LEN];
        if (sscanf(line, "version=%255s", value) == 1)
            snprintf(version, VAL_LEN, "%s", value);
        if (sscanf(line, "build=%255s", value) == 1)
            snprintf(build, VAL_LEN, "%s", value);
    }
    fclose(f);
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: status <key>\n");
        return 2;
    }

    load_config("range.conf");

    const char *flag = getenv("CTF_FLAG");
    if (flag == NULL) flag = "";

    if (strcmp(argv[1], "version") == 0) {
        printf("version=%s\n", version);
        return 0;
    }
    if (strcmp(argv[1], "build") == 0) {
        printf("build=%s\n", build);
        return 0;
    }
    if (strcmp(argv[1], "config") == 0) {
        /* the operator dump: everything this process knows */
        printf("config=version=%s;build=%s;flag=%s\n", version, build, flag);
        return 0;
    }

    printf("error=unknown-key\n");
    return 0;
}
