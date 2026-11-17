import { Select, Space, Spin, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ResultExportMenu } from "@/components/actions/result-export-menu";
import { apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type AuditSummary = {
  metrics: {
    total: number;
    today_count: number;
    failed_count: number;
  };
  by_action: Array<{ action_type: string; action_count: number }>;
};

type AuditLog = {
  id: number;
  user_id: number | null;
  action_type: string;
  resource_type: string | null;
  resource_id: string | null;
  request_data: Record<string, unknown> | null;
  result_status: string;
  ip_address: string | null;
  created_at: string;
};

export default function AuditPage() {
  const [actionType, setActionType] = useState<string | undefined>();

  const { data: summary, isLoading } = useQuery({
    queryKey: ["audit-summary"],
    queryFn: () => apiFetch<AuditSummary>("/audit/summary"),
  });
  const { data: logs = [] } = useQuery({
    queryKey: ["audit-logs", actionType],
    queryFn: () =>
      apiFetch<{ items: AuditLog[] }>(
        `/audit/logs?limit=500${actionType ? `&action_type=${encodeURIComponent(actionType)}` : ""}`,
      ).then((response) => response.items),
  });

  if (isLoading) {
    return <Spin />;
  }

  const metrics = [
    ["日志总数", summary?.metrics.total ?? 0],
    ["今日操作", summary?.metrics.today_count ?? 0],
    ["失败操作", summary?.metrics.failed_count ?? 0],
  ];

  return (
    <div className="audit-page">
      <PageHero
        title="审计日志"
        description="查看登录、数据操作、AI 调用与系统管理记录，让关键动作始终可回溯。"
        actions={
          <ResultExportMenu
            kind="audit"
            title="系统审计日志"
            filename="系统审计日志"
            metrics={summary?.metrics}
            table={{
              columns: ["编号", "用户ID", "操作", "资源类型", "资源编号", "结果", "IP", "时间", "请求数据"],
              rows: logs.map((log) => [
                log.id,
                log.user_id,
                log.action_type,
                log.resource_type,
                log.resource_id,
                log.result_status,
                log.ip_address,
                log.created_at,
                JSON.stringify(log.request_data ?? {}),
              ]),
            }}
            metadata={{ action_type: actionType ?? "all" }}
          />
        }
      />

      <section className="metric-grid">
        {metrics.map(([label, value]) => (
          <article className="metric-card" key={String(label)}>
            <div className="metric-label">{label}</div>
            <div className="metric-value">{value}</div>
          </article>
        ))}
      </section>

      <Space style={{ marginTop: 20, marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="操作类型"
          style={{ width: 180 }}
          value={actionType}
          onChange={setActionType}
          options={(summary?.by_action ?? []).map((item) => ({
            value: item.action_type,
            label: `${item.action_type} (${item.action_count})`,
          }))}
        />
      </Space>

      <Table
        rowKey="id"
        dataSource={logs}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: "编号", dataIndex: "id", width: 80 },
          { title: "用户ID", dataIndex: "user_id", width: 100 },
          {
            title: "操作",
            dataIndex: "action_type",
            render: (value: string) => <Tag color="blue">{value}</Tag>,
          },
          { title: "资源类型", dataIndex: "resource_type" },
          { title: "资源编号", dataIndex: "resource_id" },
          {
            title: "结果",
            dataIndex: "result_status",
            render: (value: string) => (
              <Tag color={value === "SUCCESS" ? "green" : "red"}>{value}</Tag>
            ),
          },
          { title: "IP", dataIndex: "ip_address" },
          {
            title: "请求数据",
            dataIndex: "request_data",
            render: (value: Record<string, unknown> | null) =>
              value ? JSON.stringify(value) : "",
          },
          { title: "时间", dataIndex: "created_at" },
        ]}
      />
    </div>
  );
}

