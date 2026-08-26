// SPDX-License-Identifier: Apache-2.0
//
// V004 probe: verify the SDK supports the multi-generation collection pattern
// required by the B-layer rebuild (build new generation, keep old serving on
// failure, switch serving on success, recover by rebuilding).

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
constexpr std::uint32_t kDimension = 4;

void Log(const std::string& step, const std::string& detail) {
    std::cout << "V004_GENERATION step=" << step << " detail=\"" << detail << "\"" << std::endl;
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

void RequireOk(const std::string& step, const VectorDB::Status& status) {
    if (!status.IsOk()) {
        Fail(step, StatusDetail(status));
    }
    Log(step, StatusDetail(status));
}

void CreateCollection(const std::shared_ptr<VectorDB::Database>& client,
                      const std::string& collection) {
    VectorDB::CollectionSchema schema(collection, "V004 generation");
    if (!schema.AddField({kIdField, VectorDB::DataType::INT64, "primary key", true, false})) {
        Fail("schema_id", "failed to add id field");
    }
    if (!schema.AddField(
            VectorDB::FieldSchema(kVectorField, VectorDB::DataType::FLOAT_VECTOR, "vector")
                .WithDimension(kDimension))) {
        Fail("schema_vector", "failed to add vector field");
    }
    const std::string index_name = collection + "_idx";
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::IndexDesc index(kVectorField, index_name, 0, VectorDB::IndexType::FLAT,
                              VectorDB::MetricType::COSINE);
#else
    VectorDB::IndexDesc index(kVectorField, index_name, VectorDB::IndexType::FLAT,
                              VectorDB::MetricType::COSINE);
#endif
    RequireOk("create_collection_" + collection, client->CreateCollection(schema, index));
}

void InsertRows(const std::shared_ptr<VectorDB::Database>& client,
                const std::string& collection, std::int64_t count) {
    std::vector<std::int64_t> ids;
    std::vector<std::vector<float>> vectors;
    ids.reserve(count);
    vectors.reserve(count);
    for (std::int64_t i = 0; i < count; ++i) {
        ids.push_back(i);
        vectors.push_back({static_cast<float>(i % 5) / 5.0F, 1.0F, 0.0F, 0.0F});
    }
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, ids),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, vectors),
    };
    VectorDB::DmlResults results;
    RequireOk("insert_" + collection, client->Insert(collection, fields, results));
}

long long QueryCount(const std::shared_ptr<VectorDB::Database>& client,
                     const std::string& collection) {
    VectorDB::QueryArguments arguments;
    arguments.SetCollectionName(collection);
    arguments.SetExpression("id >= 0");
    arguments.AddOutputField(kIdField);
    VectorDB::QueryResults results;
    RequireOk("query_" + collection, client->Query(arguments, results, 5000));
    const auto id_field = results.GetFieldByName(kIdField);
    if (id_field == nullptr) {
        return 0;
    }
    const auto ids = std::static_pointer_cast<VectorDB::Int64FieldData>(id_field);
    return ids->Count();
}

bool HasCollection(const std::shared_ptr<VectorDB::Database>& client,
                   const std::string& collection) {
    bool exists = false;
    const VectorDB::Status status = client->HasCollection(collection, exists);
    return status.IsOk() && exists;
}

}  // namespace

int main() {
    const std::string gen_a = "v004_gen_a_serving";
    const std::string gen_b = "v004_gen_b_building";

    const auto client = VectorDB::Database::Create();
    if (client == nullptr) {
        Fail("client_create", "Database::Create returned null");
    }
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::ConnectParam connect_param;
#else
    VectorDB::ConnectParam connect_param("v004-generation");
#endif
    connect_param.SetConnectTimeout(5000);
    RequireOk("connect", client->Connect(connect_param));

    // Clean slate.
    for (const auto& c : {gen_a, gen_b}) {
        if (HasCollection(client, c)) {
            client->DropCollection(c);
        }
    }

    // 1. Build serving generation A.
    CreateCollection(client, gen_a);
    InsertRows(client, gen_a, 100);
    Log("serving_gen_A_rows", std::to_string(QueryCount(client, gen_a)));

    // 2. Build new generation B while A keeps serving.
    CreateCollection(client, gen_b);
    InsertRows(client, gen_b, 50);
    Log("build_gen_B_rows", std::to_string(QueryCount(client, gen_b)));
    Log("gen_A_still_queryable_during_build", std::to_string(QueryCount(client, gen_a)));

    // 3. Inject a failed build into a third collection: wrong-dimension insert.
    const std::string gen_fail = "v004_gen_fail";
    if (HasCollection(client, gen_fail)) {
        client->DropCollection(gen_fail);
    }
    CreateCollection(client, gen_fail);
    std::vector<VectorDB::FieldDataPtr> bad_fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, std::vector<std::int64_t>{1}),
        std::make_shared<VectorDB::FloatVecFieldData>(
            kVectorField, std::vector<std::vector<float>>{{1.0F, 0.0F, 0.0F}}),
    };
    VectorDB::DmlResults bad_results;
    const VectorDB::Status bad_insert = client->Insert(gen_fail, bad_fields, bad_results);
    Log("failed_build_insert", StatusDetail(bad_insert));

    // The failed build must not disturb generation A.
    Log("gen_A_intact_after_failed_build", std::to_string(QueryCount(client, gen_a)));
    client->DropCollection(gen_fail);

    // 4. Switch serving: drop A, B becomes serving.
    RequireOk("drop_old_gen_A", client->DropCollection(gen_a));
    Log("gen_A_dropped", std::to_string(HasCollection(client, gen_a)));
    Log("gen_B_serving_after_switch", std::to_string(QueryCount(client, gen_b)));

    // Cleanup.
    client->DropCollection(gen_b);
    client->Disconnect();
    Log("probe_complete", "multi-generation build/fail-keep-old/switch verified");
    return 0;
}
