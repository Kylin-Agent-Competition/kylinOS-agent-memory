/**
 * libconnect_hook.c — LD_PRELOAD connect() interception
 * ======================================================
 * 拦截 libc connect() 系统调用。
 * 当检测到目标 AF_UNIX socket 路径包含 "kylin-ai-runtime-unix" 时，
 * 透明替换为 Memory Echo Service 路径。
 *
 * 用途: 无需修改当前已安装的 libkyai-assistant.so，即可将 kylin-aiassistant
 *       的 Socket 连接重定向到自定义 Memory Service。
 *
 * 环境变量:
 *   CONNECT_HOOK_REDIRECT  重定向目标 socket 路径
 *                          (默认: /tmp/kylin-memory-echo/echo.sock)
 *   CONNECT_HOOK_MATCH     路径匹配子串
 *                          (默认: kylin-ai-runtime-unix)
 *   CONNECT_HOOK_DEBUG     设为 1 启用 stderr 调试日志
 *
 * 编译 (麒麟 VM):
 *   gcc -shared -fPIC -O2 -ldl -o libconnect_hook.so libconnect_hook.c
 *
 * 使用:
 *   CONNECT_HOOK_DEBUG=1 LD_PRELOAD=./libconnect_hook.so ./kylin-aiassistant
 *
 * 协议: 与 Memory Echo Service 的 4 字节 Big-Endian 长度 + UTF-8 JSON 协议
 *       完全兼容。connect() 重定向对上层协议透明。
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stddef.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <stdarg.h>
#include <errno.h>
#include <unistd.h>

/* ---- 原始 connect() 函数指针 ---- */
static int (*real_connect)(int sockfd, const struct sockaddr *addr, socklen_t addrlen) = NULL;

/* ---- 配置（运行时从环境变量读取） ---- */
static const char *g_match_substring = NULL;
static const char *g_redirect_path = NULL;
static int g_debug = 0;
static pthread_once_t init_once = PTHREAD_ONCE_INIT;

/* ---- 工具函数 ---- */
static void hook_debug(const char *fmt, ...) {
    if (!g_debug) return;
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "[connect_hook] ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    fflush(stderr);
    va_end(ap);
}

static void hook_error(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "[connect_hook] ERROR: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    fflush(stderr);
    va_end(ap);
}

/* ---- 一次性线程安全初始化 ---- */
static void init_hook(void) {
    /* 获取真实 connect() */
    if (!real_connect) {
        real_connect = dlsym(RTLD_NEXT, "connect");
        if (!real_connect) {
            hook_error("dlsym(RTLD_NEXT, \"connect\") failed: %s", dlerror());
            _exit(1);
        }
    }

    /* 读取调试标志 */
    const char *debug_env = getenv("CONNECT_HOOK_DEBUG");
    if (debug_env && (strcmp(debug_env, "1") == 0 || strcmp(debug_env, "true") == 0)) {
        g_debug = 1;
    }

    /* 读取匹配子串 */
    g_match_substring = getenv("CONNECT_HOOK_MATCH");
    if (!g_match_substring || g_match_substring[0] == '\0') {
        g_match_substring = "kylin-ai-runtime-unix";
    }

    /* 读取重定向目标路径 */
    g_redirect_path = getenv("CONNECT_HOOK_REDIRECT");
    if (!g_redirect_path || g_redirect_path[0] == '\0') {
        g_redirect_path = "/tmp/kylin-memory-echo/echo.sock";
    }

    hook_debug("initialized: match='%s' redirect='%s' debug=%d",
               g_match_substring, g_redirect_path, g_debug);
}

/* ---- 被拦截的 connect() ---- */
int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    pthread_once(&init_once, init_hook);

    /* 前置边界检查: NULL 地址或过短 addrlen 直接透传, 避免无符号下溢与越界读取 */
    if (addr == NULL || addrlen < offsetof(struct sockaddr_un, sun_path)) {
        return real_connect(sockfd, addr, addrlen);
    }

    /* 只处理 AF_UNIX (本地 socket) */
    if (addr->sa_family != AF_UNIX) {
        hook_debug("pass-through: non-AF_UNIX family=%d", addr->sa_family);
        return real_connect(sockfd, addr, addrlen);
    }

    const struct sockaddr_un *un_addr = (const struct sockaddr_un *)addr;

    /* sun_path 可能不包含空终止符 (Linux abstract socket) */
    /* 安全提取路径字符串 */
    char path_buf[108];  /* UNIX_PATH_MAX = 108 */
    memset(path_buf, 0, sizeof(path_buf));

    /* 处理 abstract socket (sun_path[0] == '\0') */
    if (un_addr->sun_path[0] == '\0') {
        hook_debug("pass-through: abstract socket (sun_path[0]=='\\0')");
        return real_connect(sockfd, addr, addrlen);
    }

    /* 复制路径，限制长度 */
    size_t path_len = addrlen - offsetof(struct sockaddr_un, sun_path);
    if (path_len >= sizeof(path_buf)) {
        path_len = sizeof(path_buf) - 1;
    }
    memcpy(path_buf, un_addr->sun_path, path_len);
    path_buf[sizeof(path_buf) - 1] = '\0';

    hook_debug("connect() called: path='%s' addrlen=%d", path_buf, (int)addrlen);

    /* 检查是否匹配 kylin-ai-runtime-unix */
    if (strstr(path_buf, g_match_substring) == NULL) {
        hook_debug("pass-through: path does not contain '%s'", g_match_substring);
        return real_connect(sockfd, addr, addrlen);
    }

    /* ---- 匹配！重定向到 Memory Echo Service ---- */
    hook_debug("MATCH! Redirecting '%s' -> '%s'", path_buf, g_redirect_path);

    /* 构建新的 sockaddr_un */
    struct sockaddr_un new_addr;
    memset(&new_addr, 0, sizeof(new_addr));
    new_addr.sun_family = AF_UNIX;
    strncpy(new_addr.sun_path, g_redirect_path, sizeof(new_addr.sun_path) - 1);

    /* 计算新的 addrlen */
    socklen_t new_addrlen = offsetof(struct sockaddr_un, sun_path) 
                            + strlen(g_redirect_path) + 1;
    if (new_addrlen > sizeof(struct sockaddr_un)) {
        new_addrlen = sizeof(struct sockaddr_un);
    }

    hook_debug("calling real_connect() with redirected path='%s' addrlen=%d",
               g_redirect_path, (int)new_addrlen);

    int ret = real_connect(sockfd, (const struct sockaddr *)&new_addr, new_addrlen);

    if (ret == 0) {
        hook_debug("redirected connect() SUCCESS: '%s' -> '%s' fd=%d",
                   path_buf, g_redirect_path, sockfd);
    } else {
        hook_error("redirected connect() FAILED: '%s' -> '%s' errno=%d (%s)",
                   path_buf, g_redirect_path, errno, strerror(errno));
    }

    return ret;
}

/**
 * If the target also uses QLocalSocket which calls socket() + connect() on Linux,
 * we also need to handle the case where socket() may be used with AF_UNIX.
 * However, socket() does not carry path info, so only connect() interception is needed.
 *
 * Note: Some applications may use socketpair() or other mechanisms.
 * This hook only covers the standard connect() path used by QLocalSocket
 * and raw POSIX socket() + connect() pairs.
 */