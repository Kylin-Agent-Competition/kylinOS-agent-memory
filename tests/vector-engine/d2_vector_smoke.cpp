// SPDX-License-Identifier: Apache-2.0
//
// D2 Vector Engine data-plane smoke probe.
//
// This probe verifies real collection CRUD, hard user_id filtering, vector
// search isolation, and persistence across an operator-controlled service
// restart. It targets the Kylin 0k0.7 client/runtime combination documented
// by the companion compatibility patch and intentionally excludes D3
// provider and contract work.

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

#include "d2_cleanup_manifest.h"
#include "Database.h"

namespace {

constexpr char kIdField[] = "id";
constexpr char kUserField[] = "user_id";
constexpr char kCategoryField[] = "category";
constexpr char kContentField[] = "content";
constexpr char kVectorField[] = "embedding";
constexpr char kIndexName[] = "d2_vector_smoke_index";
constexpr char kCollectionPrefix[] = "d2_vector_smoke_";
constexpr char kAlphaUser[] = "user-alpha";
constexpr char kBetaUser[] = "user-beta";
constexpr std::uint32_t kDimension = 4;

enum class Phase {
    kPrepare,
    kVerify,
    kCleanup,
    kVerifyCleanup,
};

struct Options {
    Phase phase = Phase::kPrepare;
    std::string app_id = "d2-vector-smoke";
    std::string run_id;
    std::string collection;
    std::string db_file;
    std::string manifest;
    std::string cleanup_token;
    std::string cleanup_invocation_id;
    bool service_managed_database = false;
};

struct QueryRows {
    std::vector<std::int64_t> ids;
    std::vector<std::string> user_ids;
    std::vector<std::int64_t> categories;
    std::vector<std::string> contents;
};

std::string Sanitize(std::string value) {
    std::replace(value.begin(), value.end(), '\n', ' ');
    std::replace(value.begin(), value.end(), '\r', ' ');
    return value;
}

void Log(const std::string& step, const std::string& result, const std::string& detail) {
    std::cout << "D2_VECTOR_SMOKE"
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

bool IsValidRunId(const std::string& value) {
    if (value.size() < 6 || value.size() > 32) {
        return false;
    }
    return std::all_of(value.begin(), value.end(), [](char ch) {
        return (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9');
    });
}

std::string ExpectedCollectionName(const std::string& run_id) {
    return std::string(kCollectionPrefix) + run_id;
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
    if (value == "verify-cleanup") {
        return Phase::kVerifyCleanup;
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
        case Phase::kVerifyCleanup:
            return "verify-cleanup";
    }
    return "unknown";
}

void PrintUsage(const char* program) {
    std::cout
        << "Usage: " << program
        << " --phase <prepare|verify|cleanup|verify-cleanup> --run-id <lowercase-id>"
           " --db-file <absolute-path> [--app-id <id>] [--collection <name>]"
           " --service-managed-database"
           " [--manifest <absolute-path> --cleanup-token <64-hex>"
           " --cleanup-invocation-id <32-hex>]\n\n"
        << "Persistence workflow:\n"
        << "  1. Run --phase prepare.\n"
        << "  2. Restart the service that preloads the same --db-file.\n"
        << "  3. Run --phase verify with identical database and collection values.\n"
        << "  4. Save evidence before running --phase cleanup.\n";
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
        } else if (argument == "--run-id") {
            options.run_id = require_value(argument);
        } else if (argument == "--app-id") {
            options.app_id = require_value(argument);
        } else if (argument == "--collection") {
            options.collection = require_value(argument);
        } else if (argument == "--manifest") {
            options.manifest = require_value(argument);
        } else if (argument == "--cleanup-token") {
            options.cleanup_token = require_value(argument);
        } else if (argument == "--cleanup-invocation-id") {
            options.cleanup_invocation_id = require_value(argument);
        } else if (argument == "--service-managed-database") {
            options.service_managed_database = true;
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
    if (options.db_file.empty() || options.db_file.front() != '/') {
        throw std::invalid_argument("--db-file must be an absolute path");
    }
    if (options.app_id.empty()) {
        throw std::invalid_argument("--app-id cannot be empty");
    }
    if (!IsValidRunId(options.run_id)) {
        throw std::invalid_argument(
            "--run-id must contain 6-32 lowercase ASCII letters or digits");
    }
    const std::string expected_collection = ExpectedCollectionName(options.run_id);
    if (options.collection.empty()) {
        options.collection = expected_collection;
    }
    if (options.collection != expected_collection) {
        throw std::invalid_argument(
            "--collection must exactly equal d2_vector_smoke_<run-id>");
    }
    if (!options.service_managed_database) {
        throw std::invalid_argument(
            "--service-managed-database is required by the legacy 0k0.7 runtime");
    }
    if (options.phase == Phase::kCleanup) {
        if (options.manifest.empty() || options.manifest.front() != '/') {
            throw std::invalid_argument(
                "cleanup requires --manifest with an absolute path");
        }
        if (!D2Cleanup::IsHex(options.cleanup_token, 64)) {
            throw std::invalid_argument(
                "cleanup requires --cleanup-token with 64 hexadecimal characters");
        }
        if (!D2Cleanup::IsHex(options.cleanup_invocation_id, 32)) {
            throw std::invalid_argument(
                "cleanup requires --cleanup-invocation-id with 32 hexadecimal characters");
        }
    } else if (!options.manifest.empty() || !options.cleanup_token.empty() ||
               !options.cleanup_invocation_id.empty()) {
        throw std::invalid_argument(
            "cleanup authorization arguments are only valid for --phase cleanup");
    }

    return options;
}

void ConnectToService(const std::shared_ptr<VectorDB::Database>& client,
                      const Options& options) {
    VectorDB::ConnectParam connect_param;
    connect_param.SetConnectTimeout(5000);
    RequireStatus("service_connect", client->Connect(connect_param));
    Pass("service_connect", "SDK data-plane connection established");
    Pass("database_mode", "using database preloaded by service: " + options.db_file);
    Pass("service_ready",
         "legacy 0k0.7 data plane is ready after successful Unix-socket connection");
}

bool HasCollection(const std::shared_ptr<VectorDB::Database>& client,
                   const std::string& collection) {
    bool exists = false;
    RequireStatus("collection_exists", client->HasCollection(collection, exists));
    return exists;
}

bool CollectionNameAvailable(const std::shared_ptr<VectorDB::Database>& client,
                             const std::string& collection) {
    return !HasCollection(client, collection);
}

void RequireCollectionAbsent(const std::shared_ptr<VectorDB::Database>& client,
                             const std::string& collection,
                             const std::string& step) {
    Require(CollectionNameAvailable(client, collection), step,
            "refusing to modify pre-existing collection: " + collection);
    Pass(step, "collection name is unused; safe to create: " + collection);
}

void CreateCollection(const std::shared_ptr<VectorDB::Database>& client,
                      const std::string& collection) {
    VectorDB::CollectionSchema schema(collection, "D2 Vector Engine user-isolation smoke");
    Require(schema.AddField({kIdField, VectorDB::DataType::INT64, "stable primary key", true, false}),
            "schema_id", "failed to add id field");
    Require(schema.AddField(
                VectorDB::FieldSchema(kUserField, VectorDB::DataType::VARCHAR, "hard owner boundary")
                    .WithMaxLength(64)),
            "schema_user", "failed to add user_id field");
    Require(schema.AddField({kCategoryField, VectorDB::DataType::INT64, "filter field"}),
            "schema_category", "failed to add category field");
    Require(schema.AddField(
                VectorDB::FieldSchema(kContentField, VectorDB::DataType::VARCHAR, "payload")
                    .WithMaxLength(256)),
            "schema_content", "failed to add content field");
    Require(schema.AddField(
                VectorDB::FieldSchema(kVectorField, VectorDB::DataType::FLOAT_VECTOR, "test vector")
                    .WithDimension(kDimension)),
            "schema_vector", "failed to add vector field");

    VectorDB::IndexDesc index(kVectorField, kIndexName, 0, VectorDB::IndexType::FLAT,
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
    RequireStatus(step + "_output_user", arguments.AddOutputField(kUserField));
    RequireStatus(step + "_output_category", arguments.AddOutputField(kCategoryField));
    RequireStatus(step + "_output_content", arguments.AddOutputField(kContentField));
    RequireStatus(step + "_strong_consistency",
                  arguments.SetGuaranteeTimestamp(VectorDB::GuaranteeStrongTs()));

    VectorDB::QueryResults results;
    RequireStatus(step, client->Query(arguments, results, 5000));

    const auto id_field = results.GetFieldByName(kIdField);
    const auto user_field = results.GetFieldByName(kUserField);
    const auto category_field = results.GetFieldByName(kCategoryField);
    const auto content_field = results.GetFieldByName(kContentField);
    Require(id_field != nullptr && user_field != nullptr &&
                category_field != nullptr && content_field != nullptr,
            step, "query response is missing required output fields");

    const auto ids = std::static_pointer_cast<VectorDB::Int64FieldData>(id_field);
    const auto users = std::static_pointer_cast<VectorDB::VarCharFieldData>(user_field);
    const auto categories = std::static_pointer_cast<VectorDB::Int64FieldData>(category_field);
    const auto contents = std::static_pointer_cast<VectorDB::VarCharFieldData>(content_field);
    Require(ids->Count() == users->Count() &&
                ids->Count() == categories->Count() &&
                ids->Count() == contents->Count(),
            step, "query output field lengths differ");

    return {ids->Data(), users->Data(), categories->Data(), contents->Data()};
}

void InsertRows(const std::shared_ptr<VectorDB::Database>& client,
                const std::string& collection) {
    const std::vector<std::int64_t> ids{101, 102, 201, 202};
    const std::vector<std::string> users{kAlphaUser, kAlphaUser, kBetaUser, kBetaUser};
    const std::vector<std::int64_t> categories{10, 20, 10, 30};
    const std::vector<std::string> contents{
        "alpha-nearest", "alpha-second", "beta-cross-user-decoy", "beta-delete"};
    const std::vector<std::vector<float>> vectors{
        {0.98F, 0.02F, 0.0F, 0.0F},
        {0.70F, 0.30F, 0.0F, 0.0F},
        {1.00F, 0.00F, 0.0F, 0.0F},
        {0.00F, 0.00F, 1.0F, 0.0F},
    };

    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(kIdField, ids),
        std::make_shared<VectorDB::VarCharFieldData>(kUserField, users),
        std::make_shared<VectorDB::Int64FieldData>(kCategoryField, categories),
        std::make_shared<VectorDB::VarCharFieldData>(kContentField, contents),
        std::make_shared<VectorDB::FloatVecFieldData>(kVectorField, vectors),
    };

    VectorDB::DmlResults results;
    RequireStatus("crud_insert", client->Insert(collection, fields, results));
    Require(results.IdArray().IsIntegerID(), "crud_insert",
            "insert returned non-integer IDs");
    Require(results.IdArray().IntIDArray().size() == ids.size(), "crud_insert",
            "inserted ID count differs from input row count");
    Pass("crud_insert", "inserted 4 deterministic rows across 2 users");
}

void VerifyUserFilters(const std::shared_ptr<VectorDB::Database>& client,
                       const std::string& collection,
                       const std::string& prefix) {
    const QueryRows alpha = Query(
        client, collection, "user_id == \"user-alpha\"", prefix + "_alpha_query");
    const std::set<std::int64_t> alpha_ids(alpha.ids.begin(), alpha.ids.end());
    Require(alpha_ids == std::set<std::int64_t>({101, 102}), prefix + "_alpha_query",
            "target user query did not return exactly ids {101,102}");
    Require(std::all_of(alpha.user_ids.begin(), alpha.user_ids.end(),
                        [](const std::string& value) { return value == kAlphaUser; }),
            prefix + "_alpha_query", "target user query leaked another user");

    const QueryRows constrained = Query(
        client, collection,
        "user_id == \"user-alpha\" && category >= 20",
        prefix + "_combined_filter");
    Require(constrained.ids == std::vector<std::int64_t>({102}),
            prefix + "_combined_filter",
            "combined user/category filter did not return exactly id 102");
    Require(constrained.user_ids.front() == kAlphaUser,
            prefix + "_combined_filter", "combined filter leaked another user");
    Pass(prefix + "_user_filter",
         "hard user_id filters returned only target-user rows");
}

void VerifyVectorSearch(const std::shared_ptr<VectorDB::Database>& client,
                        const std::string& collection,
                        const std::string& step) {
    VectorDB::SearchArguments arguments(collection, 4, VectorDB::MetricType::COSINE);
    RequireStatus(step + "_output_id", arguments.AddOutputField(kIdField));
    RequireStatus(step + "_output_user", arguments.AddOutputField(kUserField));
    RequireStatus(step + "_filter",
                  arguments.SetExpression("user_id == \"user-alpha\""));
    RequireStatus(step + "_strong_consistency",
                  arguments.SetGuaranteeTimestamp(VectorDB::GuaranteeStrongTs()));
    RequireStatus(step + "_target",
                  arguments.AddTargetVector(
                      kVectorField, std::vector<float>{1.0F, 0.0F, 0.0F, 0.0F}));

    VectorDB::SearchResults results;
    RequireStatus(step, client->Search(arguments, results, 5000));
    Require(results.Results().size() == 1, step,
            "expected one result set for one query vector");

    const auto& result = results.Results().front();
    const auto& ids = result.Ids().IntIDArray();
    const auto user_field = result.OutputField(kUserField);
    Require(user_field != nullptr, step,
            "vector search response is missing required user_id output field");
    const auto users = std::static_pointer_cast<VectorDB::VarCharFieldData>(user_field);
    Require(ids.size() == users->Count(), step,
            "vector search ID and user_id output lengths differ");
    Require(ids.size() == 2 &&
                std::set<std::int64_t>(ids.begin(), ids.end()) ==
                std::set<std::int64_t>({101, 102}),
            step, "vector search did not return exactly target-user ids {101,102}");
    Require(std::all_of(users->Data().begin(), users->Data().end(),
                        [](const std::string& user_id) {
                            return user_id == kAlphaUser;
                        }),
            step, "vector search returned a row owned by another user");
    Require(ids.front() == 101, step,
            "expected target-user id 101 as the nearest allowed match");
    Require(std::find(ids.begin(), ids.end(), 201) == ids.end(), step,
            "exact-vector cross-user decoy id 201 bypassed user_id filter");
    Pass(step,
         "vector search returned exactly ids {101,102}, all owned by user-alpha; id 101 ranked first");
}

void UpsertRow(const std::shared_ptr<VectorDB::Database>& client,
               const std::string& collection) {
    std::vector<VectorDB::FieldDataPtr> fields{
        std::make_shared<VectorDB::Int64FieldData>(
            kIdField, std::vector<std::int64_t>{102}),
        std::make_shared<VectorDB::VarCharFieldData>(
            kUserField, std::vector<std::string>{kAlphaUser}),
        std::make_shared<VectorDB::Int64FieldData>(
            kCategoryField, std::vector<std::int64_t>{25}),
        std::make_shared<VectorDB::VarCharFieldData>(
            kContentField, std::vector<std::string>{"alpha-second-updated"}),
        std::make_shared<VectorDB::FloatVecFieldData>(
            kVectorField,
            std::vector<std::vector<float>>{{0.80F, 0.20F, 0.0F, 0.0F}}),
    };

    VectorDB::DmlResults results;
    RequireStatus("crud_upsert", client->Upsert(collection, fields, results));
    Require(results.IdArray().IntIDArray().size() == 1, "crud_upsert",
            "upsert did not return exactly one ID");

    const QueryRows rows = Query(
        client, collection, "id in [102]", "crud_upsert_verify");
    Require(rows.ids.size() == 1 && rows.ids.front() == 102 &&
                rows.user_ids.front() == kAlphaUser &&
                rows.categories.front() == 25 &&
                rows.contents.front() == "alpha-second-updated",
            "crud_upsert_verify", "id 102 does not contain the expected values");
    Pass("crud_upsert",
         "id 102 updated while preserving user_id=user-alpha");
}

void DeleteRow(const std::shared_ptr<VectorDB::Database>& client,
               const std::string& collection) {
    VectorDB::DmlResults results;
    RequireStatus("crud_delete",
                  client->Delete(collection,
                                 "user_id == \"user-beta\" && id in [202]", results));

    const QueryRows rows = Query(
        client, collection, "id in [101,102,201,202]", "crud_delete_verify");
    const std::set<std::int64_t> actual(rows.ids.begin(), rows.ids.end());
    Require(actual == std::set<std::int64_t>({101, 102, 201}),
            "crud_delete_verify", "expected ids {101,102,201} after deleting id 202");
    Pass("crud_delete",
         "user-scoped delete removed beta id 202; ids {101,102,201} remain");
}

void VerifyCollisionGuard(const std::shared_ptr<VectorDB::Database>& client,
                          const std::string& collection) {
    RequireCollectionAbsent(client, collection, "collision_guard_precondition");
    CreateCollection(client, collection);
    InsertRows(client, collection);

    Require(!CollectionNameAvailable(client, collection), "collision_guard_refusal",
            "same-name collection was incorrectly considered safe to create");
    Pass("collision_guard_refusal",
         "same-name creation is refused without dropping the existing collection");

    const QueryRows rows = Query(
        client, collection, "id in [101,102,201,202]", "collision_guard_preserved");
    Require(std::set<std::int64_t>(rows.ids.begin(), rows.ids.end()) ==
                std::set<std::int64_t>({101, 102, 201, 202}),
            "collision_guard_preserved",
            "collision fixture changed while creation was refused");
    Pass("collision_guard_preserved",
         "pre-existing same-name collection retained all four sentinel rows");

    RequireStatus("collision_guard_owned_cleanup", client->DropCollection(collection));
    Require(!HasCollection(client, collection), "collision_guard_owned_cleanup",
            "owned collision fixture still exists after explicit cleanup");
    Pass("collision_guard_owned_cleanup",
         "only the collection created by this regression run was removed");
}

void VerifyPersistedState(const std::shared_ptr<VectorDB::Database>& client,
                          const std::string& collection) {
    Require(HasCollection(client, collection), "persistence_collection",
            "collection is missing after service restart/reload");
    Pass("persistence_collection", "collection exists after service restart/reload");

    const QueryRows rows = Query(
        client, collection, "id in [101,102,201,202]", "persistence_rows");
    const std::set<std::int64_t> actual(rows.ids.begin(), rows.ids.end());
    Require(actual == std::set<std::int64_t>({101, 102, 201}),
            "persistence_rows", "persisted IDs differ from {101,102,201}");

    const auto id102 = std::find(rows.ids.begin(), rows.ids.end(), 102);
    Require(id102 != rows.ids.end(), "persistence_rows", "persisted id 102 is missing");
    const auto index = static_cast<std::size_t>(std::distance(rows.ids.begin(), id102));
    Require(rows.user_ids[index] == kAlphaUser &&
                rows.categories[index] == 25 &&
                rows.contents[index] == "alpha-second-updated",
            "persistence_rows", "upserted values for id 102 were not persisted");
    Pass("persistence_rows",
         "CRUD end state persisted with ids {101,102,201}");

    VerifyUserFilters(client, collection, "persistence");
    VerifyVectorSearch(client, collection, "persistence_vector_search");
}

void RunPrepare(const std::shared_ptr<VectorDB::Database>& client,
                const Options& options) {
    VerifyCollisionGuard(client, options.collection);
    RequireCollectionAbsent(client, options.collection, "collection_precondition");
    CreateCollection(client, options.collection);
    InsertRows(client, options.collection);
    VerifyUserFilters(client, options.collection, "prepare");
    VerifyVectorSearch(client, options.collection, "vector_search");
    UpsertRow(client, options.collection);
    DeleteRow(client, options.collection);
    Pass("prepare_complete",
         "state retained; restart Vector Engine, then run --phase verify");
}

void RunVerify(const std::shared_ptr<VectorDB::Database>& client,
               const Options& options) {
    VerifyPersistedState(client, options.collection);
    Pass("verify_complete", "post-restart persistence and user isolation passed");
}

void RunCleanup(const std::shared_ptr<VectorDB::Database>& client,
                const Options& options) {
    if (!HasCollection(client, options.collection)) {
        Pass("cleanup", "collection already absent");
        return;
    }
    RequireStatus("cleanup", client->DropCollection(options.collection));
    Require(!HasCollection(client, options.collection), "cleanup",
            "collection still exists after DropCollection");
    Pass("cleanup", "test collection removed");
}

void RunVerifyCleanup(const std::shared_ptr<VectorDB::Database>& client,
                      const Options& options) {
    Require(!HasCollection(client, options.collection), "verify_cleanup",
            "collection exists after cleanup completion");
    Pass("verify_cleanup",
         "collection remains absent; no destructive operation was requested");
}

void Run(const Options& options) {
    if (options.phase == Phase::kCleanup) {
        D2Cleanup::Validate({options.manifest,
                             options.cleanup_token,
                             options.cleanup_invocation_id,
                             options.run_id,
                             options.collection,
                             options.app_id,
                             options.db_file});
        Pass("cleanup_authorization",
             "manifest, one-time token, database identity, and invocation match");
    }

    const auto client = VectorDB::Database::Create();
    Require(client != nullptr, "client_create", "Database::Create returned null");
    Pass("client_create", "official Vector Engine client created");

    bool connected = false;
    try {
        ConnectToService(client, options);
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
            case Phase::kVerifyCleanup:
                RunVerifyCleanup(client, options);
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
            "phase=" + PhaseName(options.phase) +
                ", collection=" + options.collection +
                ", app_id=" + options.app_id);
        Run(options);
        Log("probe_complete", "PASS",
            "all checks for phase " + PhaseName(options.phase) + " passed");
        return 0;
    } catch (const std::exception& error) {
        Log("probe_complete", "FAIL", error.what());
        return 1;
    }
}
