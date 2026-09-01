// SPDX-License-Identifier: Apache-2.0
//
// Vector bridge CLI：通过 JSON 输入/输出调用 Vector SDK 的子进程桥接器。
// 支持 create_collection、insert、search、delete、drop_collection；Python
// 每次操作启动此二进制，无需 pybind11 或 python3-dev。

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "Database.h"
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {

constexpr char kIdField[] = "id";
constexpr char kVectorField[] = "embedding";
constexpr char kUserIdField[] = "user_id";
constexpr char kVersionIdField[] = "version_id";
constexpr char kSceneIdField[] = "scene_id";
constexpr char kMemoryStatusField[] = "memory_status";
constexpr char kObjectTypeField[] = "object_type";
constexpr char kKnowledgeTypeField[] = "knowledge_type";
constexpr char kPrimaryCategoryField[] = "primary_category";
constexpr char kSourceEventIdField[] = "source_event_id";
constexpr char kIsDeletedField[] = "is_deleted";
constexpr std::size_t kMaxDeletePairs = 500;

std::shared_ptr<VectorDB::Database> g_client;

void Out(const json& value) {
    std::cout << value.dump() << std::endl;
}

void Fail(const std::string& msg) {
    Out(json{{"ok", false}, {"code", -1}, {"message", msg}});
    std::exit(1);
}

void EnsureConnected() {
    if (g_client) return;
    g_client = VectorDB::Database::Create();
    if (!g_client) Fail("Database::Create returned null");
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::ConnectParam connect_param;
#else
    VectorDB::ConnectParam connect_param("vector-bridge");
#endif
    connect_param.SetConnectTimeout(5000);
    const VectorDB::Status st = g_client->Connect(connect_param);
    if (!st.IsOk()) {
        Out(json{{"ok", false}, {"code", static_cast<int>(st.Code())}, {"message", st.Message()}});
        std::exit(1);
    }
}

json StatusJson(const VectorDB::Status& st) {
    return json{{"ok", st.IsOk()}, {"code", static_cast<int>(st.Code())}, {"message", st.Message()}};
}

std::string EscapeExpressionString(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size());
    for (const char ch : value) {
        if (ch == '\\' || ch == '"') {
            escaped.push_back('\\');
        }
        escaped.push_back(ch);
    }
    return escaped;
}

std::string QuotedExpressionList(const std::vector<std::string>& values) {
    std::string expression = "[";
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index != 0) {
            expression += ",";
        }
        expression += "\"" + EscapeExpressionString(values[index]) + "\"";
    }
    return expression + "]";
}

void ValidateFilterKeys(const json& filter) {
    if (!filter.is_object()) {
        Fail("filter must be an object");
    }
    for (auto it = filter.begin(); it != filter.end(); ++it) {
        const std::string& key = it.key();
        if (key != "user_id" && key != "allowed_scene_ids" &&
            key != "include_unscoped" && key != "allowed_memory_statuses" &&
            key != "object_types" && key != "knowledge_types" &&
            key != "primary_categories" && key != "source_event_ids" &&
            key != "version_ids" &&
            key != "exclude_deleted") {
            Fail("unknown filter key: " + key);
        }
    }
}

void ValidateDeleteKeys(const json& input) {
    if (!input.is_object()) {
        Fail("删除请求必须是对象");
    }
    for (auto it = input.begin(); it != input.end(); ++it) {
        const std::string& key = it.key();
        if (key != "user_id" && key != "ids" && key != "version_ids") {
            Fail("删除请求含未知字段: " + key);
        }
    }
    if (!input.contains("user_id") || !input.contains("ids") ||
        !input.contains("version_ids")) {
        Fail("删除请求必须包含 user_id、ids 和 version_ids");
    }
}

void CreateCollection(const std::string& name, int dim) {
    VectorDB::CollectionSchema schema(name, "vector-bridge");
    if (!schema.AddField({kIdField, VectorDB::DataType::INT64, "pk", true, false})) {
        Fail("failed to add id field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kVectorField, VectorDB::DataType::FLOAT_VECTOR, "v").WithDimension(dim))) {
        Fail("failed to add vector field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kUserIdField, VectorDB::DataType::VARCHAR, "owner").WithMaxLength(128))) {
        Fail("failed to add user_id field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kVersionIdField, VectorDB::DataType::VARCHAR, "version").WithMaxLength(128))) {
        Fail("failed to add version_id field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kSceneIdField, VectorDB::DataType::VARCHAR, "scene").WithMaxLength(128))) {
        Fail("failed to add scene_id field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kMemoryStatusField, VectorDB::DataType::VARCHAR, "lifecycle status").WithMaxLength(64))) {
        Fail("failed to add memory_status field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kObjectTypeField, VectorDB::DataType::VARCHAR, "memory object type").WithMaxLength(64))) {
        Fail("failed to add object_type field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kKnowledgeTypeField, VectorDB::DataType::VARCHAR, "knowledge type").WithMaxLength(64))) {
        Fail("failed to add knowledge_type field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kPrimaryCategoryField, VectorDB::DataType::VARCHAR, "knowledge category").WithMaxLength(128))) {
        Fail("failed to add primary_category field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kSourceEventIdField, VectorDB::DataType::VARCHAR, "knowledge source event").WithMaxLength(128))) {
        Fail("failed to add source_event_id field");
    }
    if (!schema.AddField({kIsDeletedField, VectorDB::DataType::BOOL, "logical deletion marker"})) {
        Fail("failed to add is_deleted field");
    }
    const std::string index_name = name + "_idx";
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::IndexDesc index(kVectorField, index_name, 0, VectorDB::IndexType::FLAT, VectorDB::MetricType::COSINE);
#else
    VectorDB::IndexDesc index(kVectorField, index_name, VectorDB::IndexType::FLAT, VectorDB::MetricType::COSINE);
#endif
    const VectorDB::Status st = g_client->CreateCollection(schema, index);
    Out(StatusJson(st));
}

void Insert(const std::string& name, const json& ids, const json& vectors,
            const json& user_ids, const json& version_ids, const json& scene_ids,
            const json& memory_statuses, const json& deleted_flags,
            const json& object_types, const json& knowledge_types,
            const json& primary_categories, const json& source_event_ids) {
    std::vector<std::int64_t> id_vec = ids.get<std::vector<std::int64_t>>();
    std::vector<std::vector<float>> vecs;
    for (const auto& v : vectors) {
        vecs.push_back(v.get<std::vector<float>>());
    }
    const std::vector<std::string> users = user_ids.get<std::vector<std::string>>();
    const std::vector<std::string> versions = version_ids.get<std::vector<std::string>>();
    const std::vector<std::string> scenes = scene_ids.get<std::vector<std::string>>();
    const std::vector<std::string> statuses = memory_statuses.get<std::vector<std::string>>();
    const std::vector<bool> deleted = deleted_flags.get<std::vector<bool>>();
    const std::vector<std::string> objects = object_types.get<std::vector<std::string>>();
    const std::vector<std::string> knowledge_kinds = knowledge_types.get<std::vector<std::string>>();
    const std::vector<std::string> categories = primary_categories.get<std::vector<std::string>>();
    const std::vector<std::string> source_events = source_event_ids.get<std::vector<std::string>>();
    if (id_vec.size() != vecs.size() || id_vec.size() != users.size() ||
        id_vec.size() != versions.size() || id_vec.size() != scenes.size() ||
        id_vec.size() != statuses.size() || id_vec.size() != deleted.size() ||
        id_vec.size() != objects.size() || id_vec.size() != knowledge_kinds.size() ||
        id_vec.size() != categories.size() || id_vec.size() != source_events.size()) {
        Fail("ids, vectors and metadata fields must have equal length");
    }
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, id_vec),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, vecs),
        std::make_shared<VectorDB::VarCharFieldData>(kUserIdField, users),
        std::make_shared<VectorDB::VarCharFieldData>(kVersionIdField, versions),
        std::make_shared<VectorDB::VarCharFieldData>(kSceneIdField, scenes),
        std::make_shared<VectorDB::VarCharFieldData>(kMemoryStatusField, statuses),
        std::make_shared<VectorDB::VarCharFieldData>(kObjectTypeField, objects),
        std::make_shared<VectorDB::VarCharFieldData>(kKnowledgeTypeField, knowledge_kinds),
        std::make_shared<VectorDB::VarCharFieldData>(kPrimaryCategoryField, categories),
        std::make_shared<VectorDB::VarCharFieldData>(kSourceEventIdField, source_events),
        std::make_shared<VectorDB::BoolFieldData>(kIsDeletedField, deleted),
    };
    VectorDB::DmlResults results;
    const VectorDB::Status st = g_client->Insert(name, fields, results);
    json out = StatusJson(st);
    if (st.IsOk() && results.IdArray().IsIntegerID()) {
        out["inserted_ids"] = results.IdArray().IntIDArray();
    }
    Out(out);
}

void Search(const std::string& name, const json& query_vector, const json& filter,
            int top_n, int timeout) {
    if (top_n <= 0) {
        Fail("top_n must be greater than 0");
    }
    ValidateFilterKeys(filter);
    const std::string user_id = filter.at("user_id").get<std::string>();
    if (user_id.empty()) {
        Fail("filter.user_id must be non-empty");
    }
    const std::vector<float> query = query_vector.get<std::vector<float>>();
    if (query.empty()) {
        Fail("query vector must be non-empty");
    }
    for (const float value : query) {
        if (!std::isfinite(value)) {
            Fail("query vector values must be finite");
        }
    }
    VectorDB::SearchArguments arguments(name, top_n, VectorDB::MetricType::COSINE);
    arguments.AddOutputField(kIdField);
    arguments.AddOutputField(kUserIdField);
    arguments.AddOutputField(kVersionIdField);
    std::vector<std::string> clauses{
        std::string(kUserIdField) + " == \"" + EscapeExpressionString(user_id) + "\"",
    };
    // 删除态永不参与检索。即使测试协议收到伪造的 exclude_deleted=false，
    // 也不能把逻辑删除记录重新暴露给调用方。
    clauses.push_back(std::string(kIsDeletedField) + " == false");
    const std::vector<std::string> scenes = filter.value(
        "allowed_scene_ids", std::vector<std::string>{});
    const bool include_unscoped = filter.value("include_unscoped", false);
    const std::string unscoped_scene = std::string(kSceneIdField) + " == \"\"";
    if (scenes.empty()) {
        // D/E 冻结：空 allowlist 表示没有任何 scoped scene 获得授权，绝不能退化为通配。
        // is_deleted == false 已是不可绕过的前置门禁；再追加 true 构成确定性零命中。
        clauses.push_back(include_unscoped
            ? unscoped_scene
            : std::string(kIsDeletedField) + " == true");
    } else {
        const std::string scene_match = std::string(kSceneIdField) + " in " + QuotedExpressionList(scenes);
        clauses.push_back(include_unscoped
            ? "(" + scene_match + " || " + unscoped_scene + ")"
            : scene_match);
    }
    const std::vector<std::string> statuses = filter.value(
        "allowed_memory_statuses", std::vector<std::string>{});
    if (!statuses.empty()) {
        clauses.push_back(std::string(kMemoryStatusField) + " in " + QuotedExpressionList(statuses));
    }
    const std::vector<std::string> object_types = filter.value(
        "object_types", std::vector<std::string>{});
    if (!object_types.empty()) {
        clauses.push_back(std::string(kObjectTypeField) + " in " + QuotedExpressionList(object_types));
    }
    const auto add_knowledge_filter = [&clauses, &filter](
        const char* filter_key, const char* field_name) {
        const std::vector<std::string> values = filter.value(
            filter_key, std::vector<std::string>{});
        if (!values.empty()) {
            clauses.push_back(
                "(" + std::string(kObjectTypeField) + " != \"knowledge\" || " +
                std::string(field_name) + " in " + QuotedExpressionList(values) + ")");
        }
    };
    add_knowledge_filter("knowledge_types", kKnowledgeTypeField);
    add_knowledge_filter("primary_categories", kPrimaryCategoryField);
    add_knowledge_filter("source_event_ids", kSourceEventIdField);
    add_knowledge_filter("version_ids", kVersionIdField);
    std::string expression;
    for (std::size_t index = 0; index < clauses.size(); ++index) {
        if (index != 0) {
            expression += " && ";
        }
        expression += clauses[index];
    }
    const VectorDB::Status filter_status = arguments.SetExpression(expression);
    if (!filter_status.IsOk()) {
        Fail("failed to set user_id filter: " + filter_status.Message());
    }
    arguments.AddTargetVector(kVectorField, query);
    VectorDB::SearchResults results;
    const VectorDB::Status st = g_client->Search(arguments, results, timeout);
    json out = StatusJson(st);
    if (st.IsOk() && !results.Results().empty()) {
        const auto& result = results.Results().front();
        const auto& ids = result.Ids().IntIDArray();
        const auto& scores = result.Scores();
        json hits = json::array();
        if (ids.empty()) {
            if (!scores.empty()) {
                Fail("search response has scores without hit ids");
            }
        } else {
            const auto users = std::static_pointer_cast<VectorDB::VarCharFieldData>(
                result.OutputField(kUserIdField));
            const auto versions = std::static_pointer_cast<VectorDB::VarCharFieldData>(
                result.OutputField(kVersionIdField));
            if (!users || !versions || users->Data().size() != ids.size() ||
                versions->Data().size() != ids.size() || scores.size() != ids.size()) {
                Fail("search response has inconsistent hit metadata");
            }
            for (std::size_t i = 0; i < ids.size(); ++i) {
                hits.push_back({
                    {"id", ids[i]},
                    {"score", scores[i]},
                    {"user_id", users->Data()[i]},
                    {"version_id", versions->Data()[i]},
                });
            }
        }
        out["hits"] = hits;
    }
    Out(out);
}

void DropCollection(const std::string& name) {
    const VectorDB::Status st = g_client->DropCollection(name);
    Out(StatusJson(st));
}

void Delete(const std::string& name, const json& input) {
    ValidateDeleteKeys(input);
    const json& user_value = input.at("user_id");
    const json& ids_value = input.at("ids");
    const json& versions_value = input.at("version_ids");
    if (!user_value.is_string() || user_value.get<std::string>().empty()) {
        Fail("删除用户必须非空字符串");
    }
    if (!ids_value.is_array() || ids_value.empty()) {
        Fail("删除 ID 必须是非空数组");
    }
    if (ids_value.size() > kMaxDeletePairs) {
        Fail("单次删除最多 500 对 ID/版本");
    }
    if (!versions_value.is_array() || versions_value.size() != ids_value.size()) {
        Fail("版本 ID 必须与删除 ID 一一对应");
    }

    const std::string user_id = user_value.get<std::string>();
    std::string pair_expression;
    for (std::size_t index = 0; index < ids_value.size(); ++index) {
        const json& id_value = ids_value.at(index);
        const json& version_value = versions_value.at(index);
        if ((!id_value.is_number_integer() && !id_value.is_number_unsigned()) ||
            id_value.get<std::int64_t>() <= 0) {
            Fail("删除 ID 必须是正整数");
        }
        if (!version_value.is_string() || version_value.get<std::string>().empty()) {
            Fail("版本 ID 必须是非空字符串");
        }
        if (index != 0) {
            pair_expression += " || ";
        }
        pair_expression += "(" + std::string(kIdField) + " == " +
            std::to_string(id_value.get<std::int64_t>()) + " && " +
            std::string(kVersionIdField) + " == \"" +
            EscapeExpressionString(version_value.get<std::string>()) + "\")";
    }

    const std::string expression = std::string(kUserIdField) + " == \"" +
        EscapeExpressionString(user_id) + "\" && (" + pair_expression + ")";
    VectorDB::DmlResults results;
    const VectorDB::Status st = g_client->Delete(name, expression, results);
    json output = StatusJson(st);
    if (st.IsOk()) {
        output["requested_count"] = ids_value.size();
    }
    Out(output);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        Fail("用法: vector_cli <create_collection|insert|search|delete|drop_collection> ...");
    }
    const std::string op = argv[1];
    try {
        EnsureConnected();
        if (op == "create_collection") {
            if (argc < 4) Fail("create_collection <name> <dim>");
            CreateCollection(argv[2], std::stoi(argv[3]));
        } else if (op == "insert") {
            if (argc < 3) Fail("insert <name>  (JSON on stdin: {ids:[...],vectors:[[...]],user_ids:[...],version_ids:[...],scene_ids:[...],memory_statuses:[...],deleted_flags:[...],object_types?:[...],knowledge_types?:[...],primary_categories?:[...],source_event_ids?:[...]})");
            json in;
            std::cin >> in;
            const std::size_t record_count = in["ids"].size();
            const auto default_metadata = [record_count](const std::string& value) {
                json values = json::array();
                for (std::size_t index = 0; index < record_count; ++index) {
                    values.push_back(value);
                }
                return values;
            };
            const json object_types = in.value(
                "object_types", default_metadata("knowledge"));
            const json knowledge_types = in.value(
                "knowledge_types", default_metadata(""));
            const json primary_categories = in.value(
                "primary_categories", default_metadata(""));
            const json source_event_ids = in.value(
                "source_event_ids", default_metadata(""));
            Insert(argv[2], in["ids"], in["vectors"], in["user_ids"], in["version_ids"],
                   in["scene_ids"], in["memory_statuses"], in["deleted_flags"],
                   object_types, knowledge_types, primary_categories, source_event_ids);
        } else if (op == "search") {
            if (argc < 4) Fail("search <name> <top_n> [timeout]  (JSON on stdin: {vector:[...],filter:{user_id:...}})");
            json in;
            std::cin >> in;
            int top_n = std::stoi(argv[3]);
            int timeout = argc >= 5 ? std::stoi(argv[4]) : 5000;
            Search(argv[2], in["vector"], in["filter"], top_n, timeout);
        } else if (op == "drop_collection") {
            if (argc < 3) Fail("drop_collection <name>");
            DropCollection(argv[2]);
        } else if (op == "delete") {
            if (argc < 3) Fail("delete <name>（stdin: {user_id,ids,version_ids}）");
            json in;
            std::cin >> in;
            Delete(argv[2], in);
        } else {
            Fail("unknown op: " + op);
        }
    } catch (const std::exception& e) {
        Fail(std::string("exception: ") + e.what());
    }
    if (g_client) {
        g_client->Disconnect();
    }
    return 0;
}
