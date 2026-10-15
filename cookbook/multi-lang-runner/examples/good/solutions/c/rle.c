#include <stdio.h>
#include <string.h>

int main(void) {
    char s[10005];
    if (!fgets(s, sizeof(s), stdin)) return 1;
    int len = (int)strlen(s);
    while (len > 0 && (s[len-1] == '\n' || s[len-1] == '\r')) s[--len] = '\0';
    if (len == 0) return 0;
    char prev = s[0];
    int count = 1;
    for (int i = 1; i < len; i++) {
        if (s[i] == prev) {
            count++;
        } else {
            printf("%d%c", count, prev);
            prev = s[i];
            count = 1;
        }
    }
    printf("%d%c\n", count, prev);
    return 0;
}
