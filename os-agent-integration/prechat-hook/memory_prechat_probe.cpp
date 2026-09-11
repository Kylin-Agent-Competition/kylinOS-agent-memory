#include <dlfcn.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <cctype>

namespace {
const char* log_path() {
    const char* p = std::getenv("MEMORY_PRECHAT_LOG");
    return (p && *p) ? p : "/tmp/memory_prechat_probe.log";
}
void log_line(const char* s) {
    if (FILE* f = std::fopen(log_path(), "a")) {
        std::fprintf(f, "%s\n", s);
        std::fflush(f);
        std::fclose(f);
    }
}
__attribute__((constructor))
void on_load() {
    char b[128];
    std::snprintf(b, sizeof(b), "[memory-prechat] probe-loaded pid=%ld", (long)getpid());
    log_line(b);
}
}

namespace kyai { namespace assistant {
class OsAssistant {
public:
    void chatAsync(const std::string& request);
};

void OsAssistant::chatAsync(const std::string& request) {
    static constexpr const char* SYMBOL =
        "_ZN4kyai9assistant11OsAssistant9chatAsyncERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE";
    using RealFn = void (*)(OsAssistant*, const std::string&);
    static RealFn real_fn = reinterpret_cast<RealFn>(dlsym(RTLD_NEXT, SYMBOL));

    size_t i = 0;
    while (i < request.size() && std::isspace((unsigned char)request[i])) ++i;
    char first = (i < request.size()) ? request[i] : '\0';

    const char* kind =
        first == '{' ? "json-object" :
        first == '[' ? "json-array" :
        first == '\0' ? "empty" : "plain-text";

    const int has_messages = request.find("\"messages\"") != std::string::npos;
    const int has_prompt   = request.find("\"prompt\"")   != std::string::npos;
    const int has_content  = request.find("\"content\"")  != std::string::npos;
    const int has_role     = request.find("\"role\"")     != std::string::npos;

    char b[256];
    std::snprintf(
        b, sizeof(b),
        "[memory-prechat] probe pid=%ld bytes=%zu kind=%s first=0x%02x messages=%d prompt=%d content=%d role=%d",
        (long)getpid(), request.size(), kind, (unsigned char)first,
        has_messages, has_prompt, has_content, has_role
    );
    log_line(b);

    if (!real_fn) {
        log_line("[memory-prechat] ERROR real-chatAsync-not-found");
        return;
    }
    real_fn(this, request);
}
}}
