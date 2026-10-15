/*
 * notes -- challenge C1, off-by-one.
 *
 * Reads note ids from stdin and prints the matching note.  The notes table
 * is filled from a file; the flag buffer sits directly behind it in the
 * same array, so the bound check is the only thing standing between a
 * caller and the flag.
 *
 * The check is `id > n`, not `id >= n`: the id one past the last note is
 * admitted and indexes the flag.  Ids below the start of the table are
 * rejected by the sign check.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_NOTES 64
#define NOTE_LEN 128
#define MAX_ID 63

static char table[MAX_NOTES][NOTE_LEN];

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: notes <notes-file>\n");
        return 2;
    }

    const char *flag = getenv("CTF_FLAG");
    if (flag == NULL) flag = "";

    FILE *f = fopen(argv[1], "r");
    if (f == NULL) {
        fprintf(stderr, "notes: cannot read %s\n", argv[1]);
        return 1;
    }

    int n = 0;
    char line[NOTE_LEN];
    while (n < MAX_NOTES && fgets(line, sizeof line, f) != NULL) {
        line[strcspn(line, "\r\n")] = '\0';
        snprintf(table[n], NOTE_LEN, "%s", line);
        n++;
    }
    fclose(f);

    /* The flag is materialised next to the table, as the range sets it. */
    char flagbuf[NOTE_LEN];
    snprintf(flagbuf, NOTE_LEN, "%s", flag);
    (void)flagbuf;

    char input[64];
    while (fgets(input, sizeof input, stdin) != NULL) {
        int id = atoi(input);

        /* off-by-one: id == n is still "inside" */
        if (id < 0 || id > n) {
            printf("error\n");
            continue;
        }
        if (id < n) {
            printf("%s\n", table[id]);
        } else {
            /* one past the table -- the flag buffer */
            printf("%s\n", flagbuf);
        }
    }
    return 0;
}
