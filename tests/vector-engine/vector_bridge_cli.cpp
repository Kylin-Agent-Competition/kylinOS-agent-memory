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

void CreateCollection(const std::string& name, int dim) {
    VectorDB::CollectionSchema schema(name, "vector-bridge");
    if (!schema.AddField({kIdField, VectorDB::DataType::INT64, "pk", true, false})) {
        Fail("failed to add id field");
    }
    if (!schema.AddField(VectorDB::FieldSchema(kVectorField, VectorDB::DataType::FLOAT_VECTOR, "v").WithDimension(dim))) {
        Fail("failed to add vector field");
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

void Insert(const std::string& name, const json& ids, const json& vectors) {
    std::vector<std::int64_t> id_vec = ids.get<std::vector<std::int64_t>>();
    std::vector<std::vector<float>> vecs;
    for (const auto& v : vectors) {
        vecs.push_back(v.get<std::vector<float>>());
    }
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, id_vec),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, vecs),
    };
    VectorDB::DmlResults results;
    const VectorDB::Status st = g_client->Insert(name, fields, results);
    json out = StatusJson(st);
    if (st.IsOk() && results.IdArray().IsIntegerID()) {
        out["inserted_ids"] = results.IdArray().IntIDArray();
    }
    Out(out);
}

void Search(const std::string& name, const json& query_vector, int top_n, int timeout) {
    VectorDB::SearchArguments arguments(name, top_n, VectorDB::MetricType::COSINE);
    arguments.AddOutputField(kIdField);
    arguments.AddTargetVector(kVectorField, query_vector.get<std::vector<float>>());
    VectorDB::SearchResults results;
    const VectorDB::Status st = g_client->Search(arguments, results, timeout);
    json out = StatusJson(st);
    if (st.IsOk() && !results.Results().empty()) {
        const auto& result = results.Results().front();
        const auto& ids = result.Ids().IntIDArray();
        const auto& scores = result.Scores();
        json hits = json::array();
        for (std::size_t i = 0; i < ids.size(); ++i) {
            hits.push_back({{"id", ids[i]}, {"score", scores[i]}});
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
            if (argc < 3) Fail("insert <name>  (JSON on stdin: {ids:[...],vectors:[[...]]})");
            json in;
            std::cin >> in;
            Insert(argv[2], in["ids"], in["vectors"]);
        } else if (op == "search") {
            if (argc < 4) Fail("search <name> <top_n> [timeout]  (JSON on stdin: {vector:[...]})");
            json in;
            std::cin >> in;
            int top_n = std::stoi(argv[3]);
            int timeout = argc >= 5 ? std::stoi(argv[4]) : 5000;
            Search(argv[2], in["vector"], top_n, timeout);
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
