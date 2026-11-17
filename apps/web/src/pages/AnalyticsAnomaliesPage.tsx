import { Alert, Button, Empty, Progress, Select, Space, Spin, Table, Tag } from "antd";
import type { TableColumnsType } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ResultExportMenu } from "@/components/actions/result-export-menu";
import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch } from "@/lib/api/client";

type Severity = "high" | "medium";

type AnomalyItem = {
  major_name: string;
  severity: Severity;
  message: string;
  suggestion: string;
  plan_count: number;
  admitted_count: number;
  completion_rate: number;
  demand_ratio: number;
  plan_change_pct: number;
  admitted_change_pct: number;
};

type AnomalyResponse = {
  year_no: number | null;
  previous_year: number | null;
  contains_synthetic: boolean;
  summary: {
    total_anomalies: number;
    high: number;
    medium: number;
  };
  items: AnomalyItem[];
  message?: string;
  data_sources?: Array<{ table: string; metric: string }>;
};

const severityLabel: Record<Severity, string> = {
  high: "高风险",
  medium: "中风险",
};

export default function AnomaliesPage() {
  const queryClient = useQueryClient();
  const [severity, setSeverity] = useState<"all" | Severity>("all");
  const { data, isLoading, error } = useQuery({
    queryKey: ["analytics-anomalies"],
    queryFn: () => apiFetch<AnomalyResponse>("/analytics/anomalies"),
  });

  const items = useMemo(
    () => (data?.items ?? []).filter((item) => severity === "all" || item.severity === severity),
    [data?.items, severity],
  );

  const chartOption = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      xAxis: {
        type: "category" as const,
        data: items.slice(0, 20).map((item) => item.major_name),
        axisLabel: { rotate: 28 },
      },
      yAxis: { type: "value" as const, name: "志愿热度 / 计划" },
      series: [
        {
          name: "志愿热度比",
          type: "bar" as const,
          data: items.slice(0, 20).map((item) => item.demand_ratio),
          itemStyle: {
            color: (params: { dataIndex: number }) =>
              items[params.dataIndex]?.severity === "high" ? "#d92d20" : "#f79009",
          },
        },
      ],
    }),
    [items],
  );

  const columns: TableColumnsType<AnomalyItem> = [
    {
      title: "专业",
      dataIndex: "major_name",
      width: 160,
      fixed: "left",
    },
    {
      title: "风险",
      dataIndex: "severity",
      width: 90,
      render: (value: Severity) => (
        <Tag color={value === "high" ? "red" : "gold"}>{severityLabel[value]}</Tag>
      ),
    },
    {
      title: "异常原因",
      dataIndex: "message",
      width: 260,
    },
    {
      title: "计划 / 录取",
      key: "counts",
      width: 140,
      render: (_, record) => `${record.plan_count} / ${record.admitted_count}`,
    },
    {
      title: "完成率",
      dataIndex: "completion_rate",
      width: 180,
      render: (value: number) =>
        typeof value === "number" ? (
          <Progress
            percent={Math.min(value, 100)}
            size="small"
            status={value < 90 ? "exception" : value < 95 ? "active" : "success"}
            format={() => `${value}%`}
          />
        ) : (
          <span>{value}%</span>
        ),
    },
    {
      title: "志愿热度比",
      dataIndex: "demand_ratio",
      width: 110,
      render: (value: number) => `${value} 倍`,
    },
    {
      title: "计划同比",
      dataIndex: "plan_change_pct",
      width: 110,
      render: (value: number) => `${value > 0 ? "+" : ""}${value}%`,
    },
    {
      title: "AI 建议",
      dataIndex: "suggestion",
      width: 320,
    },
  ];

  if (isLoading) {
    return <Spin />;
  }

  if (error) {
    return <Alert type="error" message="异常检测加载失败" description={error.message} />;
  }

  if (!data?.year_no) {
    return <Alert type="warning" message={data?.message ?? "暂无异常检测数据"} />;
  }

  return (
    <div className="anomaly-page">
      <PageHero
        title="AI 异常检测"
        description="先定位偏离计划和志愿热度的专业，再用可追溯的 AI 解释支持处置。"
        actions={
          <Space wrap>
            <Tag color="blue">检测年度：{data.year_no}</Tag>
            <Tag color="default">同比基线：{data.previous_year} 年</Tag>
            <Select
              value={severity}
              onChange={setSeverity}
              style={{ width: 140 }}
              options={[
                { value: "all", label: "全部风险" },
                { value: "high", label: "仅高风险" },
                { value: "medium", label: "仅中风险" },
              ]}
            />
            <Button
              onClick={() => queryClient.invalidateQueries({ queryKey: ["analytics-anomalies"] })}
            >
              重新检测
            </Button>
            <ResultExportMenu
              kind="anomaly"
              title={`${data.year_no}年招生异常检测`}
              filename={`招生异常检测_${data.year_no}`}
              metrics={{
                total_anomalies: data.summary.total_anomalies,
                high: data.summary.high,
                medium: data.summary.medium,
                filtered_count: items.length,
              }}
              table={{
                columns: [
                  "专业",
                  "风险等级",
                  "异常原因",
                  "计划数",
                  "录取数",
                  "完成率",
                  "志愿热度比",
                  "计划同比",
                  "录取同比",
                  "建议",
                ],
                rows: items.map((item) => [
                  item.major_name,
                  item.severity,
                  item.message,
                  item.plan_count,
                  item.admitted_count,
                  item.completion_rate,
                  item.demand_ratio,
                  item.plan_change_pct,
                  item.admitted_change_pct,
                  item.suggestion,
                ]),
              }}
              sections={[
                {
                  title: "检测口径",
                  text: `检测年度 ${data.year_no}，同比基线 ${data.previous_year}，当前筛选 ${severity}。`,
                },
              ]}
              metadata={{
                year: data.year_no,
                previous_year: data.previous_year,
                severity,
                contains_synthetic: data.contains_synthetic,
                sources: data.data_sources,
              }}
            />
          </Space>
        }
      />

      {data.contains_synthetic ? (
        <Alert
          type="warning"
          showIcon
          message="同比基线包含模拟数据"
          description="2026 年真实数据与 2025 年模拟数据对比，异常结果仅用于功能验证，不能替代真实招生审计。"
          style={{ marginBottom: 16 }}
        />
      ) : null}

      <section className="metric-grid">
        <article className="metric-card">
          <div className="metric-label">异常总数</div>
          <div className="metric-value">{data.summary.total_anomalies}</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">高风险</div>
          <div className="metric-value" style={{ color: "#d92d20" }}>{data.summary.high}</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">中风险</div>
          <div className="metric-value" style={{ color: "#dc6803" }}>{data.summary.medium}</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">当前筛选</div>
          <div className="metric-value">{items.length}</div>
        </article>
      </section>

      <section className="chart-panel" style={{ marginTop: 20 }}>
        <h2>专业志愿热度与计划偏离</h2>
        {items.length ? (
          <LazyEChartsContainer option={chartOption} height={330} />
        ) : (
          <Empty description="当前筛选条件下没有异常专业" />
        )}
      </section>

      <section style={{ marginTop: 20 }}>
        <h2>异常专业清单</h2>
        <Table
          rowKey={(record) => record.major_name}
          columns={columns}
          dataSource={items}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 1400 }}
          locale={{ emptyText: <Empty description="没有符合条件的异常" /> }}
        />
      </section>
    </div>
  );
}


