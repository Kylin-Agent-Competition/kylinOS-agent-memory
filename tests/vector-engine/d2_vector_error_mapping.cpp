// SPDX-License-Identifier: Apache-2.0
//
// V002 probe: inject SDK error scenarios for upsert/search/delete and record
// the raw VectorDB::StatusCode for B-layer error mapping. This probe records
// statuses (it does not assert), so each scenario reports the real SDK behavior.

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
constexpr char kIndexName[] = "v002_error_mapping_index";
constexpr std::uint32_t kDimension = 4;

void Log(const std::string& step, const std::string& detail) {
    std::cout << "V002_ERROR_MAPPING step=" << step << " detail=\"" << detail << "\"" << std::endl;
}

std::string StatusDetail(const VectorDB::Status& status) {
    return "ok=" + std::string(status.IsOk() ? "true" : "false") +
           "; code=" + std::to_string(static_cast<int>(status.Code())) +
           "; message=" + status.Message();
}

void Record(const std::string& scenario, const VectorDB::Status& status) {
    Log(scenario, StatusDetail(status));
}

void Fail(const std::string& step, const std::string& detail) {
    Log(step, "FAIL: " + detail);
    std::exit(1);
}

bool HasCollection(const std::shared_ptr<VectorDB::Database>& client,
                   const std::string& collection) {
    bool exists = false;
    const VectorDB::Status status = client->HasCollection(collection, exists);
    if (!status.IsOk()) {
        return false;
    }
    return exists;
}

void CreateCollection(const std::shared_ptr<VectorDB::Database>& client,
                      const std::string& collection) {
    VectorDB::CollectionSchema schema(collection, "V002 error mapping");
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
    const VectorDB::Status status = client->CreateCollection(schema, index);
    Record("baseline_create_collection", status);
    if (!status.IsOk()) {
        Fail("baseline_create_collection", "valid collection creation failed");
    }
}

void ScenarioSearchNonexistent(const std::shared_ptr<VectorDB::Database>& client) {
    VectorDB::SearchArguments arguments("v002_nonexistent_collection", 3, VectorDB::MetricType::COSINE);
    arguments.AddTargetVector(kVectorField, std::vector<float>{1.0F, 0.0F, 0.0F, 0.0F});
    VectorDB::SearchResults results;
    Record("scenario_search_nonexistent_collection", client->Search(arguments, results, 5000));
}

void ScenarioInsertWrongDimension(const std::shared_ptr<VectorDB::Database>& client,
                                  const std::string& collection) {
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, std::vector<std::int64_t>{100}),
        std::make_shared<VectorDB::FloatVecFieldData>(
            kVectorField, std::vector<std::vector<float>>{{1.0F, 0.0F, 0.0F}}),
    };
    VectorDB::DmlResults results;
    Record("scenario_insert_wrong_dimension", client->Insert(collection, fields, results));
}

void ScenarioInsertEmptyVector(const std::shared_ptr<VectorDB::Database>& client,
                               const std::string& collection) {
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, std::vector<std::int64_t>{101}),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, std::vector<std::vector<float>>{{}}),
    };
    VectorDB::DmlResults results;
    Record("scenario_insert_empty_vector", client->Insert(collection, fields, results));
}

void ScenarioDeleteEmptyExpression(const std::shared_ptr<VectorDB::Database>& client,
                                   const std::string& collection) {
    VectorDB::DmlResults results;
    Record("scenario_delete_empty_expression", client->Delete(collection, "", results));
}

void ScenarioQueryInvalidExpression(const std::shared_ptr<VectorDB::Database>& client,
                                    const std::string& collection) {
    VectorDB::QueryArguments arguments;
    arguments.SetCollectionName(collection);
    arguments.SetExpression("this is not a valid expression");
    VectorDB::QueryResults results;
    Record("scenario_query_invalid_expression", client->Query(arguments, results, 5000));
}

void ScenarioSearchWrongDimension(const std::shared_ptr<VectorDB::Database>& client,
                                  const std::string& collection) {
    VectorDB::SearchArguments arguments(collection, 3, VectorDB::MetricType::COSINE);
    arguments.AddTargetVector(kVectorField, std::vector<float>{1.0F, 0.0F, 0.0F});
    VectorDB::SearchResults results;
    Record("scenario_search_wrong_dimension", client->Search(arguments, results, 5000));
}

}  // namespace

int main() {
    const std::string collection = "v002_error_mapping";

    const auto client = VectorDB::Database::Create();
    if (client == nullptr) {
        Fail("client_create", "Database::Create returned null");
    }

#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::ConnectParam connect_param;
#else
    VectorDB::ConnectParam connect_param("v002-error-mapping");
#endif
    connect_param.SetConnectTimeout(5000);
    const VectorDB::Status connect_status = client->Connect(connect_param);
    Record("baseline_connect", connect_status);
    if (!connect_status.IsOk()) {
        Fail("baseline_connect", "connection failed");
    }

    if (HasCollection(client, collection)) {
        client->DropCollection(collection);
    }
    CreateCollection(client, collection);

    ScenarioSearchNonexistent(client);
    ScenarioInsertWrongDimension(client, collection);
    ScenarioInsertEmptyVector(client, collection);
    ScenarioDeleteEmptyExpression(client, collection);
    ScenarioQueryInvalidExpression(client, collection);
    ScenarioSearchWrongDimension(client, collection);

    const VectorDB::Status drop_status = client->DropCollection(collection);
    Record("cleanup_drop_collection", drop_status);

    const VectorDB::Status disconnect_status = client->Disconnect();
    Record("cleanup_disconnect", disconnect_status);

    Log("probe_complete", "all error scenarios recorded");
    return 0;
}
