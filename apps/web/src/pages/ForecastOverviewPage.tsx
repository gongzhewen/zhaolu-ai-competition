import { Alert, Button, Space, Spin, Tag } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch } from "@/lib/api/client";

type ForecastOverview = {
  status: string;
  message?: string;
  history: Array<{
    year_no: number;
    plan_count: number;
    admitted_count: number;
    completion_rate: string | number;
  }>;
  forecast: {
    year: number;
    plan_count: number;
    plan_lower: number;
    plan_upper: number;
    admitted_count: number;
    admitted_lower: number;
    admitted_upper: number;
    completion_rate: number;
    risk_level: string;
    confidence: string;
    model: string;
    data_points: number;
  } | null;
  alerts: Array<{
    severity: string;
    title: string;
    description: string;
    metric: string;
  }>;
  data_sources?: Array<{ table: string; metric: string }>;
};

export default function ForecastOverviewPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["forecast-overview"],
    queryFn: () => apiFetch<ForecastOverview>("/forecast/overview"),
  });

  const chartOption = useMemo(() => {
    const years = [
      ...(data?.history.map((item) => String(item.year_no)) ?? []),
      ...(data?.forecast ? [String(data.forecast.year)] : []),
    ];
    const planHistory = [
      ...(data?.history.map((item) => item.plan_count) ?? []),
      ...(data?.forecast ? [null] : []),
    ];
    const planForecast = [
      ...(data?.history.map(() => null) ?? []),
      ...(data?.forecast ? [data.forecast.plan_count] : []),
    ];
    const admittedHistory = [
      ...(data?.history.map((item) => item.admitted_count) ?? []),
      ...(data?.forecast ? [null] : []),
    ];
    const admittedForecast = [
      ...(data?.history.map(() => null) ?? []),
      ...(data?.forecast ? [data.forecast.admitted_count] : []),
    ];

    return {
      tooltip: { trigger: "axis" as const },
      legend: { data: ["计划历史", "计划预测", "录取历史", "录取预测"] },
      xAxis: { type: "category" as const, data: years },
      yAxis: { type: "value" as const },
      series: [
        { name: "计划历史", type: "line" as const, data: planHistory, connectNulls: true },
        {
          name: "计划预测",
          type: "line" as const,
          data: planForecast,
          connectNulls: true,
          lineStyle: { type: "dashed" as const },
        },
        { name: "录取历史", type: "line" as const, data: admittedHistory, connectNulls: true },
        {
          name: "录取预测",
          type: "line" as const,
          data: admittedForecast,
          connectNulls: true,
          lineStyle: { type: "dashed" as const },
        },
      ],
    };
  }, [data]);

  if (isLoading) {
    return <Spin />;
  }

  if (error) {
    return <Alert type="error" message="预测模块加载失败" description={error.message} />;
  }

  if (!data?.forecast) {
    return <Alert type="warning" message={data?.message ?? "暂无预测数据"} />;
  }

  const riskColor =
    data.forecast.risk_level === "high"
      ? "red"
      : data.forecast.risk_level === "medium"
        ? "gold"
        : "green";

  const metrics = [
    ["预测年度", data.forecast.year],
    ["预计招生计划", data.forecast.plan_count],
    ["预计录取人数", data.forecast.admitted_count],
    ["预计计划完成率", `${data.forecast.completion_rate}%`],
    ["模型置信度", data.forecast.confidence],
    ["数据点数量", data.forecast.data_points],
  ];

  return (
    <div className="forecast-page">
      <PageHero
        title="预测与预警"
        description="提前观察下一学年计划完成与录取风险，把问题暴露在行动之前。"
        actions={
          <Space wrap>
            <Tag color={riskColor}>风险等级：{data.forecast.risk_level}</Tag>
            <Tag color="blue">模型：{data.forecast.model}</Tag>
            <Button
              onClick={() => queryClient.invalidateQueries({ queryKey: ["forecast-overview"] })}
            >
              重新计算
            </Button>
          </Space>
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
        <h2>招生与录取趋势预测</h2>
        <LazyEChartsContainer option={chartOption} height={360} />
      </section>

      <section style={{ marginTop: 20 }}>
        <h2>风险与预警</h2>
        {data.alerts.map((alert) => (
          <Alert
            key={`${alert.severity}-${alert.title}`}
            type={alert.severity === "high" ? "error" : alert.severity === "medium" ? "warning" : "info"}
            message={alert.title}
            description={alert.description}
            style={{ marginBottom: 10 }}
            showIcon
          />
        ))}
      </section>

      <section style={{ marginTop: 20 }}>
        <h2>数据来源</h2>
        <Space wrap>
          {data.data_sources?.map((source) => (
            <Tag key={`${source.table}-${source.metric}`} color="blue">
              {source.table} · {source.metric}
            </Tag>
          ))}
        </Space>
      </section>
    </div>
  );
}

