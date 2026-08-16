#ifndef TOOL_EXECUTION_OBSERVER_H
#define TOOL_EXECUTION_OBSERVER_H

/*
 * Tool Result Hook (Hook C) 最小观察点
 *
 * 关联: D1 任务卡 §3.3 Hook C / TD-007 / R-ARCH-05
 * 用途: 在真实 kylin-aiassistant 宿主中捕获 Tool 成功/失败结果，
 *       生成符合 02 表31 的 ToolExecutionEvent 结构化 JSON。
 *
 * 本文件为 header-only，无外部依赖，通过 KyInfo()/qInfo() 输出到
 * /home/kylin-agent/.log/kylin-aiassistant.log。
 *
 * 已知源码缺口（真实宿主集成阶段需补齐）:
 *   - tool_call_id / source_trace_id: toolReply 信号未携带
 *   - arguments: 仅出站 sendToolMessage 可见，未透传回程
 *   - started_at: 需在 sendToolMessage 打点
 *   - cancelled 状态: 宿主未显式建模
 */

#include <QJsonObject>
#include <QJsonArray>
#include <QJsonDocument>
#include <QDateTime>
#include <QString>

namespace tool_execution_observer {

// 出站: Tool 触发观察点（记录 started_at + arguments）
inline QString toolStartJson(int toolId, const QString &fileType, const QString &para)
{
    QJsonObject obj;
    obj["event"] = "tool_invocation";
    obj["tool_id"] = toolId;
    obj["file_type"] = fileType;
    obj["arguments"] = para;
    obj["started_at"] = QDateTime::currentDateTime().toString(Qt::ISODate);
    return QString::fromUtf8(QJsonDocument(obj).toJson(QJsonDocument::Compact));
}

// 回程: Tool 结果观察点（生成 ToolExecutionEvent 结构，缺失字段标注空/默认）
inline QString toolResultJson(const QString &toolName,
                              int errorCode,
                              const QString &result,
                              const QString &model,
                              const QString &startedAt)
{
    const QString status = (errorCode == 0) ? QStringLiteral("success")
                                            : QStringLiteral("failure");

    QJsonObject e;
    e["tool_call_id"] = QStringLiteral("");               // 宿主缺口
    e["tool_name"] = toolName;
    e["arguments"] = QJsonArray();                        // 宿主缺口（仅出站可见）
    e["started_at"] = startedAt;
    e["finished_at"] = QDateTime::currentDateTime().toString(Qt::ISODate);
    e["status"] = status;
    e["result"] = (errorCode == 0) ? result : QStringLiteral("");
    e["error"] = (errorCode != 0) ? result : QStringLiteral("");
    e["side_effect"] = QStringLiteral("");
    e["user_confirmed"] = false;
    e["rollback_status"] = QStringLiteral("none");
    e["source_trace_id"] = QStringLiteral("");            // 宿主缺口

    QJsonObject wrapper;
    wrapper["event"] = QStringLiteral("tool_execution_event");
    wrapper["model"] = model;
    wrapper["tool_execution_event"] = e;
    return QString::fromUtf8(QJsonDocument(wrapper).toJson(QJsonDocument::Compact));
}

} // namespace tool_execution_observer

#endif // TOOL_EXECUTION_OBSERVER_H
