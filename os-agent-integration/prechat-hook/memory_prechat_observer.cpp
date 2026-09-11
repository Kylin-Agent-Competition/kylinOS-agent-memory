#include <dlfcn.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

namespace {

const char* log_path()
{
    const char* p = std::getenv("MEMORY_PRECHAT_LOG");
    return (p && *p) ? p : "/tmp/memory_prechat_observer.log";
}

void write_log(const char* message)
{
    FILE* fp = std::fopen(log_path(), "a");
    if (!fp)
        return;

    std::fprintf(fp, "%s\n", message);
    std::fflush(fp);
    std::fclose(fp);
}

__attribute__((constructor))
void observer_loaded()
{
    char buf[256];
    std::snprintf(
        buf,
        sizeof(buf),
        "[memory-prechat] library-loaded pid=%ld",
        static_cast<long>(getpid())
    );
    write_log(buf);
}

} // namespace


namespace kyai {
namespace assistant {

class OsAssistant {
public:
    void chatAsync(const std::string& request);
};

void OsAssistant::chatAsync(const std::string& request)
{
    static constexpr const char* SYMBOL =
        "_ZN4kyai9assistant11OsAssistant9chatAsyncERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE";

    using RealFn = void (*)(OsAssistant*, const std::string&);

    static RealFn real_fn =
        reinterpret_cast<RealFn>(dlsym(RTLD_NEXT, SYMBOL));

    char buf[256];

    if (!real_fn) {
        const char* err = dlerror();

        std::snprintf(
            buf,
            sizeof(buf),
            "[memory-prechat] ERROR real-chatAsync-not-found error=%s",
            err ? err : "(none)"
        );

        write_log(buf);

        // Observer 模式下不能安全继续真实调用，因此直接返回。
        // 正式测试前必须先确保 real_fn 可解析。
        return;
    }

    std::snprintf(
        buf,
        sizeof(buf),
        "[memory-prechat] chatAsync-intercepted pid=%ld request_bytes=%zu",
        static_cast<long>(getpid()),
        request.size()
    );

    write_log(buf);

    // Observer 阶段：完全不修改模型请求。
    real_fn(this, request);
}

} // namespace assistant
} // namespace kyai
