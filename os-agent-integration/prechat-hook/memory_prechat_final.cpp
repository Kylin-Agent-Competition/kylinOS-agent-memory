
#include <dlfcn.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <cctype>

namespace {

const char* log_path() {
    const char* p = std::getenv("MEMORY_PRECHAT_LOG");
    return (p && *p) ? p : "/tmp/memory_prechat.log";
}

void log_line(const std::string& s) {
    if (FILE* f = std::fopen(log_path(), "a")) {
        std::fprintf(f, "%s\n", s.c_str());
        std::fflush(f);
        std::fclose(f);
    }
}

std::string read_context() {
    const char* p = std::getenv("MEMORY_ACTIVE_CONTEXT");
    std::string path;
    if (p && *p) {
        path = p;
    } else {
        const char* runtime = std::getenv("XDG_RUNTIME_DIR");
        if (runtime && *runtime) {
            path = std::string(runtime) + "/kylin-memory/active-context.txt";
        } else {
            path = "/run/user/" + std::to_string(static_cast<unsigned long>(getuid()))
                 + "/kylin-memory/active-context.txt";
        }
    }

    std::ifstream in(path, std::ios::binary);
    if (!in) return {};

    std::ostringstream ss;
    char buf[1024];
    std::size_t total = 0;
    while (in && total < 4096) {
        std::size_t want = sizeof(buf);
        if (4096 - total < want) want = 4096 - total;
        in.read(buf, static_cast<std::streamsize>(want));
        auto n = in.gcount();
        if (n <= 0) break;
        ss.write(buf, n);
        total += static_cast<std::size_t>(n);
    }
    return ss.str();
}

std::size_t skip_ws(const std::string& s, std::size_t p) {
    while (p < s.size() && std::isspace(static_cast<unsigned char>(s[p]))) ++p;
    return p;
}

bool parse_json_string_end(const std::string& s, std::size_t quote_pos, std::size_t& end_quote) {
    if (quote_pos >= s.size() || s[quote_pos] != '"') return false;
    bool esc = false;
    for (std::size_t i = quote_pos + 1; i < s.size(); ++i) {
        char c = s[i];
        if (esc) {
            esc = false;
            continue;
        }
        if (c == '\\') {
            esc = true;
            continue;
        }
        if (c == '"') {
            end_quote = i;
            return true;
        }
    }
    return false;
}

std::string json_escape(const std::string& s) {
    static const char* hex = "0123456789abcdef";
    std::string out;
    out.reserve(s.size() + 32);
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    out += "\\u00";
                    out += hex[(c >> 4) & 0xF];
                    out += hex[c & 0xF];
                } else {
                    out.push_back(static_cast<char>(c));
                }
        }
    }
    return out;
}

// Finds a direct child key of an object whose opening '{' is at object_pos.
// Returns the value start position after ':'.
bool find_direct_key_value(
    const std::string& s,
    std::size_t object_pos,
    const std::string& wanted,
    std::size_t& value_pos
) {
    if (object_pos >= s.size() || s[object_pos] != '{') return false;

    int depth_obj = 1;
    int depth_arr = 0;
    bool in_str = false;
    bool esc = false;

    for (std::size_t i = object_pos + 1; i < s.size(); ++i) {
        char c = s[i];

        if (in_str) {
            if (esc) { esc = false; continue; }
            if (c == '\\') { esc = true; continue; }
            if (c == '"') in_str = false;
            continue;
        }

        if (c == '"') {
            // At depth 1 and not in nested arrays, this may be a direct key.
            if (depth_obj == 1 && depth_arr == 0) {
                std::size_t endq = 0;
                if (!parse_json_string_end(s, i, endq)) return false;
                std::string key = s.substr(i + 1, endq - i - 1);
                std::size_t p = skip_ws(s, endq + 1);
                if (p < s.size() && s[p] == ':') {
                    if (key == wanted) {
                        value_pos = skip_ws(s, p + 1);
                        return value_pos < s.size();
                    }
                }
                i = endq;
                continue;
            }
            in_str = true;
            continue;
        }

        if (c == '{') ++depth_obj;
        else if (c == '}') {
            --depth_obj;
            if (depth_obj == 0) return false;
        } else if (c == '[') ++depth_arr;
        else if (c == ']') {
            if (depth_arr > 0) --depth_arr;
        }
    }
    return false;
}

bool contains_top_level_tool_call(const std::string& req) {
    std::size_t p = skip_ws(req, 0);
    if (p >= req.size() || req[p] != '{') return false;

    std::size_t v = 0;
    if (find_direct_key_value(req, p, "message_type", v) && v < req.size() && req[v] == '"') {
        std::size_t e = 0;
        if (parse_json_string_end(req, v, e)) {
            std::string val = req.substr(v + 1, e - v - 1);
            if (val == "tool_call") return true;
        }
    }
    if (find_direct_key_value(req, p, "event", v) && v < req.size() && req[v] == '"') {
        std::size_t e = 0;
        if (parse_json_string_end(req, v, e)) {
            std::string val = req.substr(v + 1, e - v - 1);
            if (val == "tool_invocation") return true;
        }
    }
    return false;
}

bool inject_into_string_value(
    const std::string& req,
    std::size_t quote_pos,
    const std::string& context,
    std::string& out
) {
    std::size_t endq = 0;
    if (!parse_json_string_end(req, quote_pos, endq)) return false;
    out = req;
    out.insert(quote_pos + 1, json_escape(context));
    return true;
}

bool inject_context(
    const std::string& req,
    const std::string& context,
    std::string& out,
    std::string& mode
) {
    if (context.empty()) {
        mode = "context-empty";
        return false;
    }

    std::size_t root = skip_ws(req, 0);
    if (root >= req.size() || req[root] != '{') {
        mode = "skip-not-object";
        return false;
    }

    if (contains_top_level_tool_call(req)) {
        mode = "skip-tool";
        return false;
    }

    std::size_t content = 0;
    if (!find_direct_key_value(req, root, "content", content)) {
        mode = "skip-no-content";
        return false;
    }

    // Common ordinary chat shape: {"content":"..."}
    if (req[content] == '"') {
        mode = "content-string";
        return inject_into_string_value(req, content, context, out);
    }

    // Alternative shape: {"content":[{"type":"text","text":"..."}]}
    if (req[content] == '[') {
        int arr_depth = 1;
        int obj_depth = 0;
        bool in_str = false;
        bool esc = false;

        for (std::size_t i = content + 1; i < req.size(); ++i) {
            char c = req[i];

            if (in_str) {
                if (esc) { esc = false; continue; }
                if (c == '\\') { esc = true; continue; }
                if (c == '"') in_str = false;
                continue;
            }

            if (c == '"') { in_str = true; continue; }
            if (c == '[') { ++arr_depth; continue; }
            if (c == ']') {
                --arr_depth;
                if (arr_depth == 0) break;
                continue;
            }
            if (c == '{') {
                ++obj_depth;
                if (arr_depth == 1 && obj_depth == 1) {
                    std::size_t textv = 0;
                    if (find_direct_key_value(req, i, "text", textv) &&
                        textv < req.size() && req[textv] == '"') {
                        mode = "content-array-text";
                        return inject_into_string_value(req, textv, context, out);
                    }
                }
                continue;
            }
            if (c == '}' && obj_depth > 0) --obj_depth;
        }

        mode = "skip-content-array-no-text";
        return false;
    }

    mode = "skip-unsupported-content";
    return false;
}

__attribute__((constructor))
void on_load() {
    std::ostringstream ss;
    ss << "[memory-prechat] final-loaded pid=" << static_cast<long>(getpid());
    log_line(ss.str());
}

} // namespace

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

    if (!real_fn) {
        log_line("[memory-prechat] ERROR real-chatAsync-not-found");
        return;
    }

    std::string context = read_context();
    std::string output;
    std::string mode;
    bool injected = inject_context(request, context, output, mode);

    std::ostringstream ss;
    ss << "[memory-prechat] chatAsync pid=" << static_cast<long>(getpid())
       << " injected=" << (injected ? 1 : 0)
       << " mode=" << mode
       << " request_bytes=" << request.size()
       << " context_bytes=" << context.size()
       << " output_bytes=" << (injected ? output.size() : request.size());
    log_line(ss.str());

    if (injected) real_fn(this, output);
    else real_fn(this, request);
}

}} // namespace kyai::assistant
