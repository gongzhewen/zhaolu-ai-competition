import { App, Button, Space, Spin, Table, Tag } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type QualitySummary = {
  metrics: {
    total: number;
    open_count: number;
    resolved_count: number;
  };
  by_type: Array<{ issue_type: string; issue_count: number }>;
  by_table: Array<{ target_table: string; issue_count: number }>;
};

type QualityIssue = {
  id: number;
  target_table: string;
  record_key: string | null;
  issue_type: string;
  issue_message: string;
  issue_status: string;
  created_at: string;
};

export default function DataQualityPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState(false);

  const { data: summary, isLoading } = useQuery({
    queryKey: ["quality-summary"],
    queryFn: () => apiFetch<QualitySummary>("/data/quality/summary"),
  });
  const { data: issues = [] } = useQuery({
    queryKey: ["quality-issues"],
    queryFn: () =>
      apiFetch<{ items: QualityIssue[] }>("/data/quality/issues?limit=500").then(
        (response) => response.items,
      ),
  });

  async function handleScan(): Promise<void> {
    setLoading(true);
    try {
      const result = await apiFetch<{ message: string; open_issues: number }>(
        "/data/quality/scan",
        { method: "POST" },
      );
      message.success(`${result.message}，当前问题 ${result.open_issues} 条`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["quality-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["quality-issues"] }),
      ]);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "数据质量扫描失败");
    } finally {
      setLoading(false);
    }
  }

  async function updateIssue(issueId: number, issueStatus: string): Promise<void> {
    try {
      await apiFetch(`/data/quality/issues/${issueId}`, {
        method: "PATCH",
        body: JSON.stringify({ issue_status: issueStatus }),
      });
      message.success("问题状态已更新");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["quality-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["quality-issues"] }),
      ]);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "更新失败");
    }
  }

  if (isLoading) {
    return <Spin />;
  }

  const metrics = [
    ["问题总数", summary?.metrics.total ?? 0],
    ["待处理", summary?.metrics.open_count ?? 0],
    ["已解决", summary?.metrics.resolved_count ?? 0],
  ];

  return (
    <div className="data-quality-page">
      <PageHero
        title="数据质量"
        description="持续扫描缺失、重复与异常记录，让进入分析链路的数据保持可信。"
        actions={
          <Button type="primary" onClick={handleScan} loading={loading}>
            运行质量扫描
          </Button>
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

      <section className="chart-panel" style={{ marginTop: 20 }}>
        <h2>问题明细</h2>
        <Table
          rowKey="id"
          dataSource={issues}
          pagination={{ pageSize: 20 }}
          locale={{ emptyText: "暂无数据质量问题" }}
          columns={[
            { title: "编号", dataIndex: "id", width: 80 },
            { title: "目标表", dataIndex: "target_table" },
            { title: "记录", dataIndex: "record_key" },
            {
              title: "类型",
              dataIndex: "issue_type",
              render: (value: string) => <Tag color="gold">{value}</Tag>,
            },
            { title: "问题说明", dataIndex: "issue_message" },
            {
              title: "状态",
              dataIndex: "issue_status",
              render: (value: string) => (
                <Tag color={value === "OPEN" ? "red" : value === "RESOLVED" ? "green" : "default"}>
                  {value}
                </Tag>
              ),
            },
            {
              title: "操作",
              render: (_, issue) => (
                <Space>
                  <Button
                    size="small"
                    onClick={() => updateIssue(issue.id, "RESOLVED")}
                    disabled={issue.issue_status === "RESOLVED"}
                  >
                    标记解决
                  </Button>
                  <Button
                    size="small"
                    onClick={() => updateIssue(issue.id, "IGNORED")}
                    disabled={issue.issue_status === "IGNORED"}
                  >
                    忽略
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </section>
    </div>
  );
}

