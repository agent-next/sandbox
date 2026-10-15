/*
 * retrieve -- challenge C2, path traversal.
 *
 * Serves a file from a document root.  The name is checked for a "../"
 * prefix, but only at the front of the string, so a name that walks up
 * through the middle of the path still escapes the root.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PATH_LEN 1024

static void serve(const char *path) {
    FILE *f = fopen(path, "r");
    if (f == NULL) {
        printf("not found\n");
        return;
    }
    char line[4096];
    int wrote = 0;
    while (fgets(line, sizeof line, f) != NULL) {
        fputs(line, stdout);
        wrote = 1;
    }
    fclose(f);
    if (!wrote) printf("\n");
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: retrieve <docroot> <name>\n");
        return 2;
    }

    const char *root = argv[1];
    const char *name = argv[2];

    /* Reject only a name that starts by walking up. */
    if (strstr(name, "..") != NULL) {
        printf("not found\n");
        return 0;
    }

    char path[PATH_LEN];
    snprintf(path, sizeof path, "%s/%s", root, name);
    serve(path);
    return 0;
}
