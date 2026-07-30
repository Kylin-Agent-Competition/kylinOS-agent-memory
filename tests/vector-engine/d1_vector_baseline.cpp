// SPDX-License-Identifier: Apache-2.0
//
// D1 Vector Engine baseline probe.
//
// This probe intentionally excludes HybridSearch/RRF. It verifies the first
// D1-B task only: connection readiness, Collection operations, CRUD, scalar
// filtering, vector search, and persistence across an operator-controlled
// service restart.

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "Database.h"

namespace {

constexpr char kIdField[] = "id";
constexpr char kCategoryField[] = "category";
constexpr char kContentField[] = "content";
constexpr char kVectorField[] = "embedding";
constexpr char kIndexName[] = "d1_vector_baseline_index";
constexpr std::uint32_t kDimension = 4;

enum class Phase {
    kPrepare,
    kVerify,
    kCleanup,
};

struct Options {
    Phase phase = Phase::kPrepare;
    std::string app_id = "d1-vector-baseline";
    std::string collection = "d1_vector_baseline";
    std::string db_file;
    bool encrypted = false;
    bool service_managed_database = false;
    std::string key;
};

struct QueryRows {
    std::vector<std::int64_t> ids;
    std::vector<std::int64_t> categories;
    std::vector<std::string> contents;
};

std::string Sanitize(std::string value) {
    std::replace(value.begin(), value.end(), '\n', ' ');
    std::replace(value.begin(), value.end(), '\r', ' ');
    return value;
}

void Log(const std::string& step, const std::string& result, const std::string& detail) {
    std::cout << "D1_VECTOR_BASELINE"
              << " step=" << step
              << " result=" << result
              << " detail=\"" << Sanitize(detail) << "\"" << std::endl;
}

[[noreturn]] void Fail(const std::string& step, const std::string& detail) {
    Log(step, "FAIL", detail);
    throw std::runtime_error(step + ": " + detail);
}

void Pass(const std::string& step, const std::string& detail) {
    Log(step, "PASS", detail);
}

void RequireStatus(const std::string& step, const VectorDB::Status& status) {
    if (!status.IsOk()) {
        Fail(step, "code=" + std::to_string(static_cast<int>(status.Code())) +
                       ", message=" + status.Message());
    }
}

void Require(bool condition, const std::string& step, const std::string& detail) {
    if (!condition) {
        Fail(step, detail);
    }
}

bool IsValidCollectionName(const std::string& value) {
    if (value.empty()) {
        return false;
    }
    const auto first = static_cast<unsigned char>(value.front());
    if (!(std::isalpha(first) || value.front() == '_')) {
        return false;
    }
    return std::all_of(value.begin() + 1, value.end(), [](char ch) {
        const auto byte = static_cast<unsigned char>(ch);
        return std::isalnum(byte) || ch == '_';
    });
}

Phase ParsePhase(const std::string& value) {
    if (value == "prepare") {
        return Phase::kPrepare;
    }
    if (value == "verify") {
        return Phase::kVerify;
    }
    if (value == "cleanup") {
        return Phase::kCleanup;
    }
    throw std::invalid_argument("unknown phase: " + value);
}

std::string PhaseName(Phase phase) {
    switch (phase) {
        case Phase::kPrepare:
            return "prepare";
        case Phase::kVerify:
            return "verify";
        case Phase::kCleanup:
            return "cleanup";
    }
    return "unknown";
}

void PrintUsage(const char* program) {
    std::cout
        << "Usage: " << program
        << " --phase <prepare|verify|cleanup> --db-file <path>"
           " [--app-id <id>] [--collection <name>]"
           " [--encrypted --key <key>] [--service-managed-database]\n\n"
        << "Persistence workflow:\n"
        << "  1. Run --phase prepare.\n"
        << "  2. Restart the Vector Engine service outside this probe.\n"
        << "  3. Run --phase verify with the same --db-file and --collection.\n"
        << "  4. Run --phase cleanup only after evidence has been collected.\n";
}

Options ParseOptions(int argc, char** argv) {
    Options options;
    bool phase_seen = false;

    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        auto require_value = [&](const std::string& name) -> std::string {
            if (index + 1 >= argc) {
                throw std::invalid_argument("missing value for " + name);
            }
            return argv[++index];
        };

        if (argument == "--phase") {
            options.phase = ParsePhase(require_value(argument));
            phase_seen = true;
        } else if (argument == "--db-file") {
            options.db_file = require_value(argument);
        } else if (argument == "--app-id") {
            options.app_id = require_value(argument);
        } else if (argument == "--collection") {
            options.collection = require_value(argument);
        } else if (argument == "--encrypted") {
            options.encrypted = true;
        } else if (argument == "--service-managed-database") {
            options.service_managed_database = true;
        } else if (argument == "--key") {
            options.key = require_value(argument);
        } else if (argument == "--help" || argument == "-h") {
            PrintUsage(argv[0]);
            std::exit(0);
        } else {
            throw std::invalid_argument("unknown argument: " + argument);
        }
    }

    if (!phase_seen) {
        throw std::invalid_argument("--phase is required");
    }
    if (options.db_file.empty()) {
        throw std::invalid_argument("--db-file is required");
    }
    if (options.app_id.empty()) {
        throw std::invalid_argument("--app-id cannot be empty");
    }
    if (!IsValidCollectionName(options.collection)) {
        throw std::invalid_argument(
            "--collection must start with a letter or underscore and contain only letters, digits, or underscores");
    }
    if (options.encrypted && options.key.empty()) {
        throw std::invalid_argument("--key is required when --encrypted is set");
    }
    if (!options.encrypted && !options.key.empty()) {
        throw std::invalid_argument("--key requires --encrypted");
    }
    if (options.service_managed_database && options.encrypted) {
        throw std::invalid_argument(
            "--service-managed-database cannot be combined with --encrypted");
    }

    return options;
}

void ConnectAndLoad(const std::shared_ptr<VectorDB::Database>& client, const Options& options) {
    VectorDB::ConnectParam connect_param(options.app_id);
    connect_param.SetConnectTimeout(5000);
    RequireStatus("service_connect", client->Connect(connect_param));
    Pass("service_connect", "SDK data-plane connection established");

    if (options.service_managed_database) {
        Pass("database_mode", "using database preloaded by service: " + options.db_file);
    } else {
        RequireStatus("database_load",
                      client->LoadDBFile(options.db_file, options.encrypted, options.key));
        Pass("database_load", "database file loaded: " + options.db_file);
    }

    std::vector<std::string> collections;
    RequireStatus("service_ready", client->ShowCollections(collections));
    Pass("service_ready", "ShowCollections succeeded; collection_count=" +
                              std::to_string(collections.size()));
}

bool HasCollection(const std::shared_ptr<VectorDB::Database>& client,
                   const std::string& collection) {
    bool exists = false;
    RequireStatus("collection_exists", client->HasCollection(collection, exists));
    return exists;
}

void DropCollectionIfPresent(const std::shared_ptr<VectorDB::Database>& client,
                             const std::string& collection) {
    if (!HasCollection(client, collection)) {
        Pass("collection_drop_preexisting", "no pre-existing collection");
        return;
    }
    RequireStatus("collection_drop_preexisting", client->DropCollection(collection));
    Pass("collection_drop_preexisting", "pre-existing collection removed");
}

void CreateCollection(const std::shared_ptr<VectorDB::Database>& client,
                      const std::string& collection) {
    VectorDB::CollectionSchema schema(collection, "D1 Vector Engine baseline");
    Require(schema.AddField({kIdField, VectorDB::DataType::INT64, "stable primary key", true, false}),
            "schema_id", "failed to add id field");
    Require(schema.AddField({kCategoryField, VectorDB::DataType::INT64, "filter field"}),
            "schema_category", "failed to add category field");
    Require(schema.AddField(
                VectorDB::FieldSchema(kContentField, VectorDB::DataType::VARCHAR, "payload").WithMaxLength(256)),
            "schema_content", "failed to add content field");
    Require(schema.AddField(
                VectorDB::FieldSchema(kVectorField, VectorDB::DataType::FLOAT_VECTOR, "test vector")
                    .WithDimension(kDimension)),
            "schema_vector", "failed to add vector field");

    VectorDB::IndexDesc index(kVectorField, kIndexName, VectorDB::IndexType::FLAT,
                              VectorDB::MetricType::COSINE);
    RequireStatus("collection_create", client->CreateCollection(schema, index));

    Require(HasCollection(client, collection), "collection_create",
            "HasCollection returned false after creation");
    Pass("collection_create", "collection and FLAT/COSINE index created");
}

QueryRows Query(const std::shared_ptr<VectorDB::Database>& client,
                const std::string& collection,
                const std::string& expression,
                const std::string& step) {
    VectorDB::QueryArguments arguments;
    RequireStatus(step + "_set_collection", arguments.SetCollectionName(collection));
    RequireStatus(step + "_set_expression", arguments.SetExpression(expression));
    RequireStatus(step + "_output_id", arguments.AddOutputField(kIdField));
    RequireStatus(step + "_output_category", arguments.AddOutputField(kCategoryField));
    RequireStatus(step + "_output_content", arguments.AddOutputField(kContentField));
    RequireStatus(step + "_strong_consistency",
                  arguments.SetGuaranteeTimestamp(VectorDB::GuaranteeStrongTs()));

    VectorDB::QueryResults results;
    RequireStatus(step, client->Query(arguments, results, 5000));

    const auto id_field = results.GetFieldByName(kIdField);
    const auto category_field = results.GetFieldByName(kCategoryField);
    const auto content_field = results.GetFieldByName(kContentField);
    Require(id_field != nullptr && category_field != nullptr && content_field != nullptr,
            step, "query response is missing required output fields");

    const auto ids = std::static_pointer_cast<VectorDB::Int64FieldData>(id_field);
    const auto categories = std::static_pointer_cast<VectorDB::Int64FieldData>(category_field);
    const auto contents = std::static_pointer_cast<VectorDB::VarCharFieldData>(content_field);
    Require(ids->Count() == categories->Count() && ids->Count() == contents->Count(),
            step, "query output field lengths differ");

    return {ids->Data(), categories->Data(), contents->Data()};
}

void InsertBaselineRows(const std::shared_ptr<VectorDB::Database>& client,
                        const std::string& collection) {
    const std::vector<std::int64_t> ids{1, 2, 3};
    const std::vector<std::int64_t> categories{10, 20, 30};
    const std::vector<std::string> contents{"alpha", "beta", "gamma"};
    const std::vector<std::vector<float>> vectors{
        {1.0F, 0.0F, 0.0F, 0.0F},
        {0.0F, 1.0F, 0.0F, 0.0F},
        {0.0F, 0.0F, 1.0F, 0.0F},
    };

    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, ids),
        std::make_shared<VectorDB::Int64FieldData>(kCategoryField, categories),
        std::make_shared<VectorDB::VarCharFieldData>(kContentField, contents),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, vectors),
    };

    VectorDB::DmlResults results;
    RequireStatus("crud_insert", client->Insert(collection, fields, results));
    Require(results.IdArray().IsIntegerID(), "crud_insert", "insert returned non-integer IDs");
    Require(results.IdArray().IntIDArray().size() == ids.size(), "crud_insert",
            "inserted ID count differs from input row count");
    Pass("crud_insert", "inserted 3 deterministic rows");
}

void VerifyScalarFilter(const std::shared_ptr<VectorDB::Database>& client,
                        const std::string& collection) {
    const QueryRows rows = Query(client, collection, "category >= 20", "filter_query");
    const std::set<std::int64_t> actual(rows.ids.begin(), rows.ids.end());
    Require(actual == std::set<std::int64_t>({2, 3}), "filter_query",
            "expected ids {2,3} for category >= 20");
    Pass("filter_query", "scalar filter returned ids {2,3}");
}

void VerifyVectorSearch(const std::shared_ptr<VectorDB::Database>& client,
                        const std::string& collection,
                        const std::string& step) {
    VectorDB::SearchArguments arguments(collection, 3, VectorDB::MetricType::COSINE);
    RequireStatus(step + "_output_id", arguments.AddOutputField(kIdField));
    RequireStatus(step + "_output_category", arguments.AddOutputField(kCategoryField));
    RequireStatus(step + "_filter", arguments.SetExpression("id in [1,2]"));
    RequireStatus(step + "_strong_consistency",
                  arguments.SetGuaranteeTimestamp(VectorDB::GuaranteeStrongTs()));
    RequireStatus(step + "_target",
                  arguments.AddTargetVector(kVectorField, std::vector<float>{1.0F, 0.0F, 0.0F, 0.0F}));

    VectorDB::SearchResults results;
    RequireStatus(step, client->Search(arguments, results, 5000));
    Require(results.Results().size() == 1, step, "expected one result set for one query vector");

    const auto& ids = results.Results().front().Ids().IntIDArray();
    Require(!ids.empty(), step, "vector search returned no rows");
    Require(ids.front() == 1, step, "expected id 1 as the nearest COSINE match");
    Pass(step, "vector search returned id 1 as the nearest filtered match");
}

void UpsertBaselineRow(const std::shared_ptr<VectorDB::Database>& client,
                       const std::string& collection) {
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, std::vector<std::int64_t>{2}),
        std::make_shared<VectorDB::Int64FieldData>(kCategoryField, std::vector<std::int64_t>{25}),
        std::make_shared<VectorDB::VarCharFieldData>(kContentField,
                                                     std::vector<std::string>{"beta-updated"}),
        std::make_shared<VectorDB::FloatVecFieldData>(
            kVectorField, std::vector<std::vector<float>>{{0.1F, 0.9F, 0.0F, 0.0F}}),
    };

    VectorDB::DmlResults results;
    RequireStatus("crud_upsert", client->Upsert(collection, fields, results));
    Require(results.IdArray().IntIDArray().size() == 1, "crud_upsert",
            "upsert did not return exactly one ID");

    const QueryRows rows = Query(client, collection, "id in [2]", "crud_upsert_verify");
    Require(rows.ids.size() == 1 && rows.ids.front() == 2 &&
                rows.categories.front() == 25 && rows.contents.front() == "beta-updated",
            "crud_upsert_verify", "id 2 does not contain the upserted values");
    Pass("crud_upsert", "id 2 updated to category=25, content=beta-updated");
}

void DeleteBaselineRow(const std::shared_ptr<VectorDB::Database>& client,
                       const std::string& collection) {
    VectorDB::DmlResults results;
    RequireStatus("crud_delete", client->Delete(collection, "id in [3]", results));

    const QueryRows rows = Query(client, collection, "id in [1,2,3]", "crud_delete_verify");
    const std::set<std::int64_t> actual(rows.ids.begin(), rows.ids.end());
    Require(actual == std::set<std::int64_t>({1, 2}), "crud_delete_verify",
            "expected only ids {1,2} after deleting id 3");
    Pass("crud_delete", "id 3 deleted; ids {1,2} remain");
}

void VerifyPersistedState(const std::shared_ptr<VectorDB::Database>& client,
                          const std::string& collection) {
    Require(HasCollection(client, collection), "persistence_collection",
            "collection is missing after service restart/reload");
    Pass("persistence_collection", "collection exists after service restart/reload");

    const QueryRows rows = Query(client, collection, "id in [1,2,3]", "persistence_rows");
    const std::set<std::int64_t> actual(rows.ids.begin(), rows.ids.end());
    Require(actual == std::set<std::int64_t>({1, 2}), "persistence_rows",
            "persisted IDs differ from expected {1,2}");

    const auto id2 = std::find(rows.ids.begin(), rows.ids.end(), 2);
    Require(id2 != rows.ids.end(), "persistence_rows", "persisted id 2 is missing");
    const auto index = static_cast<std::size_t>(std::distance(rows.ids.begin(), id2));
    Require(rows.categories[index] == 25 && rows.contents[index] == "beta-updated",
            "persistence_rows", "upserted values for id 2 were not persisted");
    Pass("persistence_rows", "CRUD end state persisted with ids {1,2}");

    VerifyVectorSearch(client, collection, "persistence_search");
}

void RunPrepare(const std::shared_ptr<VectorDB::Database>& client, const Options& options) {
    DropCollectionIfPresent(client, options.collection);
    CreateCollection(client, options.collection);
    InsertBaselineRows(client, options.collection);
    VerifyScalarFilter(client, options.collection);
    VerifyVectorSearch(client, options.collection, "vector_search");
    UpsertBaselineRow(client, options.collection);
    DeleteBaselineRow(client, options.collection);
    Pass("prepare_complete",
         "state retained; restart Vector Engine, then run --phase verify with identical options");
}

void RunVerify(const std::shared_ptr<VectorDB::Database>& client, const Options& options) {
    VerifyPersistedState(client, options.collection);
    Pass("verify_complete", "post-restart persistence verification passed");
}

void RunCleanup(const std::shared_ptr<VectorDB::Database>& client, const Options& options) {
    if (!HasCollection(client, options.collection)) {
        Pass("cleanup", "collection already absent");
        return;
    }
    RequireStatus("cleanup", client->DropCollection(options.collection));
    Require(!HasCollection(client, options.collection), "cleanup",
            "collection still exists after DropCollection");
    Pass("cleanup", "test collection removed");
}

void Run(const Options& options) {
    const auto client = VectorDB::Database::Create();
    Require(client != nullptr, "client_create", "Database::Create returned null");
    Pass("client_create", "official Vector Engine client created");

    bool connected = false;
    try {
        ConnectAndLoad(client, options);
        connected = true;

        switch (options.phase) {
            case Phase::kPrepare:
                RunPrepare(client, options);
                break;
            case Phase::kVerify:
                RunVerify(client, options);
                break;
            case Phase::kCleanup:
                RunCleanup(client, options);
                break;
        }

        RequireStatus("disconnect", client->Disconnect());
        connected = false;
        Pass("disconnect", "client disconnected cleanly");
    } catch (...) {
        if (connected) {
            const auto status = client->Disconnect();
            if (!status.IsOk()) {
                Log("disconnect_after_failure", "FAIL",
                    "code=" + std::to_string(static_cast<int>(status.Code())) +
                        ", message=" + status.Message());
            }
        }
        throw;
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Options options = ParseOptions(argc, argv);
        Log("probe_start", "INFO",
            "phase=" + PhaseName(options.phase) + ", collection=" + options.collection);
        Run(options);
        Log("probe_complete", "PASS", "all checks for phase " + PhaseName(options.phase) + " passed");
        return 0;
    } catch (const std::exception& error) {
        Log("probe_complete", "FAIL", error.what());
        return 1;
    }
}
