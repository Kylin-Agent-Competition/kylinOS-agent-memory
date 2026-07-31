#pragma once

#include "Database.h"

static_assert(sizeof(VectorDB::ConnectParam) == 208,
              "legacy ConnectParam ABI size mismatch");
static_assert(sizeof(VectorDB::CollectionSchema) == 96,
              "legacy CollectionSchema ABI size mismatch");
static_assert(sizeof(VectorDB::FieldSchema) == 120,
              "legacy FieldSchema ABI size mismatch");
static_assert(sizeof(VectorDB::IndexDesc) == 136,
              "legacy IndexDesc ABI size mismatch");
static_assert(sizeof(VectorDB::QueryArguments) == 192,
              "legacy QueryArguments compatibility size mismatch");
static_assert(sizeof(VectorDB::SearchArguments) == 344,
              "legacy SearchArguments ABI size mismatch");
