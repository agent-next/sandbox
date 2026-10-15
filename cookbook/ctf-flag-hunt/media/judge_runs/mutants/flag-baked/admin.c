/*
 * admin -- challenge C5, logic bug.
 *
 * Reads a file for an operator-selected mode.  Modes 1 and 2 are the
 * documented, unprivileged ones.  Mode 0 is the retired privileged path:
 * it is still compiled in, and because the mode is parsed with atoi(), any
 * mode that does not parse as a number becomes 0 and lands there.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void read_file(const char *path) {
    FILE *f = fopen(path, "r");
    if (f == NULL) {
        printf("denied\n");
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
        fprintf(stderr, "usage: admin <mode> <path>\n");
        return 2;
    }

    int mode = atoi(argv[1]);
    const char *path = argv[2];

    if (mode == 0) {
        /* retired privileged read */
        printf("mode=%d content=", mode);
        read_file(path);
        return 0;
    }

    if (mode == 1 || mode == 2) {
        printf("mode=%d content=denied\n", mode);
        return 0;
    }

    printf("mode=%d content=denied\n", mode);
    return 0;
}
