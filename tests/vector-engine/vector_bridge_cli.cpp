// SPDX-License-Identifier: Apache-2.0
//
// Vector bridge CLI: JSON-in / JSON-out subprocess bridge to the Vector SDK.
// Supports create_collection, insert, search, drop_collection. Python side
// spawns this binary per operation (no pybind11 / python3-dev required).

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
constexpr char kIsDeletedField[] = "is_deleted";

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
            const json& memory_statuses, const json& deleted_flags) {
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
    if (id_vec.size() != vecs.size() || id_vec.size() != users.size() ||
        id_vec.size() != versions.size() || id_vec.size() != scenes.size() ||
        id_vec.size() != statuses.size() || id_vec.size() != deleted.size()) {
        Fail("ids, vectors and metadata fields must have equal length");
    }
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, id_vec),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, vecs),
        std::make_shared<VectorDB::VarCharFieldData>(kUserIdField, users),
        std::make_shared<VectorDB::VarCharFieldData>(kVersionIdField, versions),
        std::make_shared<VectorDB::VarCharFieldData>(kSceneIdField, scenes),
        std::make_shared<VectorDB::VarCharFieldData>(kMemoryStatusField, statuses),
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
    const std::string user_id = filter.at("user_id").get<std::string>();
    if (user_id.empty()) {
        Fail("filter.user_id must be non-empty");
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
    if (!scenes.empty()) {
        const std::string scene_match = std::string(kSceneIdField) + " in " + QuotedExpressionList(scenes);
        clauses.push_back(include_unscoped
            ? "(" + scene_match + " || " + std::string(kSceneIdField) + " == \"\")"
            : scene_match);
    }
    const std::vector<std::string> statuses = filter.value(
        "allowed_memory_statuses", std::vector<std::string>{});
    if (!statuses.empty()) {
        clauses.push_back(std::string(kMemoryStatusField) + " in " + QuotedExpressionList(statuses));
    }
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
    arguments.AddTargetVector(kVectorField, query_vector.get<std::vector<float>>());
    VectorDB::SearchResults results;
    const VectorDB::Status st = g_client->Search(arguments, results, timeout);
    json out = StatusJson(st);
    if (st.IsOk() && !results.Results().empty()) {
        const auto& result = results.Results().front();
        const auto& ids = result.Ids().IntIDArray();
        const auto& scores = result.Scores();
        const auto users = std::static_pointer_cast<VectorDB::VarCharFieldData>(
            result.OutputField(kUserIdField));
        const auto versions = std::static_pointer_cast<VectorDB::VarCharFieldData>(
            result.OutputField(kVersionIdField));
        if (!users || !versions || users->Data().size() != ids.size() || versions->Data().size() != ids.size()) {
            Fail("search response missing user_id/version_id metadata");
        }
        json hits = json::array();
        for (std::size_t i = 0; i < ids.size(); ++i) {
            hits.push_back({
                {"id", ids[i]},
                {"score", scores[i]},
                {"user_id", users->Data()[i]},
                {"version_id", versions->Data()[i]},
            });
        }
        out["hits"] = hits;
    }
    Out(out);
}

void DropCollection(const std::string& name) {
    const VectorDB::Status st = g_client->DropCollection(name);
    Out(StatusJson(st));
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        Fail("usage: vector_cli <create_collection|insert|search|drop_collection> ...");
    }
    const std::string op = argv[1];
    try {
        EnsureConnected();
        if (op == "create_collection") {
            if (argc < 4) Fail("create_collection <name> <dim>");
            CreateCollection(argv[2], std::stoi(argv[3]));
        } else if (op == "insert") {
            if (argc < 3) Fail("insert <name>  (JSON on stdin: {ids:[...],vectors:[[...]],user_ids:[...],version_ids:[...],scene_ids:[...],memory_statuses:[...],deleted_flags:[...]})");
            json in;
            std::cin >> in;
            Insert(argv[2], in["ids"], in["vectors"], in["user_ids"], in["version_ids"],
                   in["scene_ids"], in["memory_statuses"], in["deleted_flags"]);
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
