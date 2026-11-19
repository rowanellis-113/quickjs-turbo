/* Verify that both current and previous environment keys remain effective. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "src/common/internal/interpreter-env.h"

static int set_test_env(const char *name, const char *value)
{
#ifdef _WIN32
    return _putenv_s(name, value ? value : "");
#else
    return value ? setenv(name, value, 1) : unsetenv(name);
#endif
}

int main(void)
{
    const char *current = "QJS_DISABLE_REGISTER_INTERP";
    char previous[64] = "QJS_DISABLE_REGISTER_";
    const char suffix[] = {76, 76, 73, 78, 84, 0};

    strcat(previous, suffix);
    if (set_test_env(current, NULL) || set_test_env(previous, NULL))
        return 1;
    if (js_interp_env_is_set(current, previous))
        return 2;
    if (set_test_env(previous, "0") || !js_interp_env_is_set(current, previous))
        return 3;
    if (set_test_env(previous, NULL) || set_test_env(current, "1") ||
        !js_interp_env_is_set(current, previous))
        return 4;
    if (set_test_env(previous, "1") || !js_interp_env_is_set(current, previous))
        return 5;
    if (set_test_env(current, NULL) || set_test_env(previous, NULL))
        return 6;
    puts("INTERPRETER_ENV_COMPAT_OK");
    return 0;
}
