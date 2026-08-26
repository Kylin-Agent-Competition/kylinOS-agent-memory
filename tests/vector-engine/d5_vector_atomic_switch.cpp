// SPDX-License-Identifier: Apache-2.0
//
// V005 probe: establish whether the SDK exposes an atomic generation/Collection
// switch. The SDK API surface (Database.h) has no rename/swap/replace operation,
// so the only switch primitive is drop-old + keep-new (routing switch). This
// probe records the collection list and a non-atomic switch to confirm it.

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "Database.h"

namespace {

void Log(const std::string& step, const std::string& detail) {
    std::cout << "V005_ATOMIC step=" << step << " detail=\"" << detail << "\"" << std::endl;
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

std::string CollectionsState(const std::shared_ptr<VectorDB::Database>& client,
                              const std::string& a, const std::string& b) {
    bool ha = false, hb = false;
    client->HasCollection(a, ha);
    client->HasCollection(b, hb);
    return "gen1_exists=" + std::string(ha ? "true" : "false") +
           "; gen2_exists=" + std::string(hb ? "true" : "false");
}

void CreateCollection(const std::shared_ptr<VectorDB::Database>& client,
                      const std::string& collection) {
    VectorDB::CollectionSchema schema(collection, "V005 atomic");
    schema.AddField({std::string("id"), VectorDB::DataType::INT64, "pk", true, false});
    schema.AddField(VectorDB::FieldSchema(std::string("embedding"), VectorDB::DataType::FLOAT_VECTOR, "v").WithDimension(4));
    const std::string index_name = collection + "_idx";
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::IndexDesc index("embedding", index_name, 0, VectorDB::IndexType::FLAT,
                              VectorDB::MetricType::COSINE);
#else
    VectorDB::IndexDesc index("embedding", index_name, VectorDB::IndexType::FLAT,
                              VectorDB::MetricType::COSINE);
#endif
    const VectorDB::Status status = client->CreateCollection(schema, index);
    if (!status.IsOk()) {
        Fail("create_" + collection, StatusDetail(status));
    }
}

}  // namespace

int main() {
    const std::string gen1 = "v005_gen_1";
    const std::string gen2 = "v005_gen_2";

    const auto client = VectorDB::Database::Create();
    if (client == nullptr) Fail("client_create", "null");
#if defined(KYLIN_VECTOR_LEGACY_0K0_7)
    VectorDB::ConnectParam connect_param;
#else
    VectorDB::ConnectParam connect_param("v005-atomic");
#endif
    connect_param.SetConnectTimeout(5000);
    const VectorDB::Status connect_status = client->Connect(connect_param);
    Log("connect", StatusDetail(connect_status));
    if (!connect_status.IsOk()) Fail("connect", "failed");

    for (const auto& c : {gen1, gen2}) {
        bool exists = false;
        if (client->HasCollection(c, exists).IsOk() && exists) client->DropCollection(c);
    }

    CreateCollection(client, gen1);
    CreateCollection(client, gen2);
    Log("collections_after_build_both_generations", CollectionsState(client, gen1, gen2));

    // Non-atomic switch: drop gen1; gen2 becomes serving. No single swap op exists.
    client->DropCollection(gen1);
    Log("collections_after_drop_old_generation", CollectionsState(client, gen1, gen2));

    // The only atomic-capable primitive in the B layer is a routing pointer,
    // because the SDK offers no rename/swap/replace. Record this observation.
    Log("atomic_switch_capability", "absent; only drop-old + keep-new routing switch available");

    client->DropCollection(gen2);
    client->Disconnect();
    Log("probe_complete", "no atomic switch API; routing switch is the equivalent scheme");
    return 0;
}
