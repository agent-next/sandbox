/*
 * token -- challenge C3, weak crypto.
 *
 * "Authenticates" a request with a token derived from the range seed and
 * salt -- both of which are public, in range.conf -- and the current time.
 * No secret enters the mixer and the acceptance window is 300 s wide, so
 * the token can be computed by anyone who can read the config.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define WINDOW 300

static unsigned long long mix(unsigned long long seed, unsigned long long salt,
                              unsigned long long t) {
    unsigned long long x = seed;
    x = x * 6364136223846793005ULL + 1442695040888963407ULL;
    x ^= (salt << 13);
    x = x * 6364136223846793005ULL + 1442695040888963407ULL;
    x ^= ((t ^ 0x9e3779b97f4a7c15ULL) << 7);
    return x;
}

static int load_config(const char *file, unsigned long long *seed,
                       unsigned long long *salt) {
    FILE *f = fopen(file, "r");
    if (f == NULL) return -1;
    char line[256];
    int got_seed = 0, got_salt = 0;
    while (fgets(line, sizeof line, f) != NULL) {
        if (sscanf(line, "seed=%llu", seed) == 1) got_seed = 1;
        if (sscanf(line, "salt=%llu", salt) == 1) got_salt = 1;
    }
    fclose(f);
    return (got_seed && got_salt) ? 0 : -1;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: token issue | token verify <token>\n");
        return 2;
    }

    unsigned long long seed = 0, salt = 0;
    if (load_config("range.conf", &seed, &salt) != 0) {
        fprintf(stderr, "token: cannot read range.conf\n");
        return 1;
    }

    const char *flag = getenv("CTF_FLAG");
    if (flag == NULL) flag = "";

    if (strcmp(argv[1], "issue") == 0) {
        unsigned long long t = (unsigned long long)time(NULL);
        printf("token=%016llx seed=%llu salt=%llu time=%llu\n",
               mix(seed, salt, t), seed, salt, t);
        return 0;
    }

    if (strcmp(argv[1], "verify") == 0 && argc == 3) {
        unsigned long long want = strtoull(argv[2], NULL, 16);
        unsigned long long now = (unsigned long long)time(NULL);
        for (long long d = -WINDOW; d <= WINDOW; d++) {
            unsigned long long t = now + (unsigned long long)d;
            if (mix(seed, salt, t) == want) {
                printf("verify=ok flag=%s\n", flag);
                return 0;
            }
        }
        printf("verify=bad\n");
        return 0;
    }

    fprintf(stderr, "usage: token issue | token verify <token>\n");
    return 2;
}
