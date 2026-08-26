// SPDX-License-Identifier: Apache-2.0
//
// V003 probe: verify deadline/timeout semantics of the non-interruptible SDK.
// The SDK has no cancel/abort API. Search/Query accept a timeout (ms);
// Insert/Upsert/Delete do not. This probe records the real timeout behavior.

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "Database.h"

namespace {

constexpr char kIdField[] = "id";
constexpr char kVectorField[] = "embedding";
constexpr char kIndexName[] = "v003_deadline_index";
constexpr std::uint32_t kDimension = 4;
constexpr std::int64_t kRowCount = 2000;

void Log(const std::string& step, const std::string& detail) {
    std::cout << "V003_DEADLINE step=" << step << " detail=\"" << detail << "\"" << std::endl;
}

void Fail(const std::string& step, const std::string& detail) {
    Log(step, "FAIL: " + detail);
    std::exit(1);
}

std::string StatusDetail(const VectorDB::Status& status) {
    return "ok=" + std::string(status.IsOk() ? "true" : "false") +
           "; code=" + std::to_string(static_cast<int>(status.Code())) +
           "; message=" + status.Message();
}

template <typename F>
long long TimeMillis(F&& fn) {
    const auto start = std::chrono::steady_clock::now();
    fn();
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
}

void CreateAndFill(const std::shared_ptr<VectorDB::Database>& client,
                   const std::string& collection) {
    VectorDB::CollectionSchema schema(collection, "V003 deadline");
    if (!schema.AddField({kIdField, VectorDB::DataType::INT64, "primary key", true, false})) {
        Fail("schema_id", "failed to add id field");
    }
    if (!schema.AddField(
            VectorDB::FieldSchema(kVectorField, VectorDB::DataType::FLOAT_VECTOR, "vector")
                .WithDimension(kDimension))) {
        Fail("schema_vector", "failed to add vector field");
    }
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::IndexDesc index(kVectorField, kIndexName, 0, VectorDB::IndexType::FLAT,
                              VectorDB::MetricType::COSINE);
#else
    VectorDB::IndexDesc index(kVectorField, kIndexName, VectorDB::IndexType::FLAT,
                              VectorDB::MetricType::COSINE);
#endif
    const VectorDB::Status create_status = client->CreateCollection(schema, index);
    if (!create_status.IsOk()) {
        Fail("create_collection", StatusDetail(create_status));
    }

    std::vector<std::int64_t> ids;
    std::vector<std::vector<float>> vectors;
    ids.reserve(kRowCount);
    vectors.reserve(kRowCount);
    for (std::int64_t i = 0; i < kRowCount; ++i) {
        ids.push_back(i);
        vectors.push_back({static_cast<float>(i % 7) / 7.0F, 1.0F, 0.0F, 0.0F});
    }
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, ids),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, vectors),
    };
    VectorDB::DmlResults insert_results;
    const VectorDB::Status insert_status = client->Insert(collection, fields, insert_results);
    Log("baseline_insert_2000_rows", StatusDetail(insert_status));
    if (!insert_status.IsOk()) {
        Fail("baseline_insert", "failed to insert rows");
    }
}

void SearchWithTimeout(const std::shared_ptr<VectorDB::Database>& client,
                       const std::string& collection, int timeout_ms) {
    VectorDB::SearchArguments arguments(collection, 10, VectorDB::MetricType::COSINE);
    arguments.AddTargetVector(kVectorField, std::vector<float>{1.0F, 0.0F, 0.0F, 0.0F});
    VectorDB::SearchResults results;
    VectorDB::Status status;
    const long long elapsed = TimeMillis([&]() {
        status = client->Search(arguments, results, timeout_ms);
    });
    Log("search_timeout_" + std::to_string(timeout_ms) + "ms",
        "elapsed_ms=" + std::to_string(elapsed) + "; " + StatusDetail(status));
}

void QueryWithTimeout(const std::shared_ptr<VectorDB::Database>& client,
                      const std::string& collection, int timeout_ms) {
    VectorDB::QueryArguments arguments;
    arguments.SetCollectionName(collection);
    arguments.SetExpression("id >= 0");
    VectorDB::QueryResults results;
    VectorDB::Status status;
    const long long elapsed = TimeMillis([&]() {
        status = client->Query(arguments, results, timeout_ms);
    });
    Log("query_timeout_" + std::to_string(timeout_ms) + "ms",
        "elapsed_ms=" + std::to_string(elapsed) + "; " + StatusDetail(status));
}

}  // namespace

int main() {
    const std::string collection = "v003_deadline";

    const auto client = VectorDB::Database::Create();
    if (client == nullptr) {
        Fail("client_create", "Database::Create returned null");
    }
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::ConnectParam connect_param;
#else
    VectorDB::ConnectParam connect_param("v003-deadline");
#endif
    connect_param.SetConnectTimeout(5000);
    const VectorDB::Status connect_status = client->Connect(connect_param);
    Log("baseline_connect", StatusDetail(connect_status));
    if (!connect_status.IsOk()) {
        Fail("baseline_connect", "connection failed");
    }

    bool exists = false;
    if (client->HasCollection(collection, exists).IsOk() && exists) {
        client->DropCollection(collection);
    }
    CreateAndFill(client, collection);

    SearchWithTimeout(client, collection, 1);
    SearchWithTimeout(client, collection, 1000);
    QueryWithTimeout(client, collection, 1);

    client->DropCollection(collection);
    client->Disconnect();
    Log("probe_complete", "deadline/timeout scenarios recorded");
    return 0;
}
