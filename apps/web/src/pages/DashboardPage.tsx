import { Alert, Select, Space, Spin, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type DashboardOverview = {
  year_no: number;
  plan_count: number;
  admitted_count: number;
  completion_rate: number;
  min_rank_no: number | null;
  source_quality_index: number | null;
  pending_alerts: number;
  empty_reason?: string | null;
};

type DimensionResponse = {
  items: Array<{ id: number; year_no: number }>;
};

export default function DashboardPage() {
  const [year, setYear] = useState<number | undefined>();

  const { data: years } = useQuery({
    queryKey: ["dashboard-years"],
    queryFn: () => apiFetch<DimensionResponse>("/meta/years"),
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard-overview", year],
    queryFn: () =>
      apiFetch<DashboardOverview>(
        `/analytics/dashboard/overview${year ? `?year=${year}` : ""}`,
      ),
  });

  if (isLoading) {
    return <Spin />;
  }

  if (error) {
    return <Alert type="error" message="工作台加载失败" description={error.message} />;
  }

  const metrics = [
    ["招生计划数", data?.plan_count ?? 0],
    ["实际录取数", data?.admitted_count ?? 0],
    [
      "计划完成率",
      `${Math.round((data?.completion_rate ?? 0) * 10000) / 100}%`,
    ],
    ["最低录取位次", data?.min_rank_no ?? "暂无"],
    ["生源质量指数", data?.source_quality_index ?? "待计算"],
    ["待处理预警", data?.pending_alerts ?? 0],
  ];

  return (
    <div className="dashboard-page">
      <PageHero
        title="招生工作台"
        description={data?.empty_reason ?? "查看年度招生计划、录取执行和风险概况。"}
        actions={
          <Space wrap>
            <Select
              allowClear
              placeholder="招生年度"
              style={{ width: 160 }}
              value={year}
              onChange={setYear}
              options={(years?.items ?? []).map((item) => ({
                value: item.year_no,
                label: String(item.year_no),
              }))}
            />
            <Tag color="blue">当前年度：{data?.year_no ?? "最新"}</Tag>
          </Space>
        }
      />

      <div className="dashboard-workspace">
        <section className="metric-grid">
          {metrics.map(([label, value]) => (
            <article className="metric-card" key={String(label)}>
              <div className="metric-label">{label}</div>
              <div className="metric-value">{value}</div>
            </article>
          ))}
        </section>
        <aside className="dashboard-shortcuts">
          <h2>常用操作</h2>
          <Link to="/admissions/plans">招生计划填报</Link>
          <Link to="/data/import">导入数据</Link>
          <Link to="/ai/assistant">AI 招录问数</Link>
          <Link to="/analytics/anomalies">查看异常</Link>
        </aside>
      </div>
    </div>
  );
}


