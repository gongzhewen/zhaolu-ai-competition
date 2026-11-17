import { Alert, Select, Space, Spin, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { ResultExportMenu } from "@/components/actions/result-export-menu";
import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch } from "@/lib/api/client";

type Overview = {
  metrics: {
    plan_count: number;
    admitted_count: number;
    completion_rate: number;
    min_score: string | number | null;
    max_score: string | number | null;
    min_rank_no: number | null;
    score_scope?: string;
  };
  by_province: Array<{
    province_name: string;
    plan_count: number;
    admitted_count: number;
    completion_rate: string | number;
    min_score: string | number | null;
    max_score: string | number | null;
    min_rank_no: number | null;
  }>;
  by_major: Array<{
    major_name: string;
    plan_count: number;
    admitted_count: number;
    completion_rate: string | number;
    min_score: string | number | null;
    max_score: string | number | null;
    min_rank_no: number | null;
  }>;
  year_trend: Array<{
    year_no: number;
    plan_count: number;
    admitted_count: number;
    completion_rate: string | number;
  }>;
};

type DimensionResponse = {
  items: Array<Record<string, string | number>>;
};

export default function AdmissionsOverviewPage() {
  const [year, setYear] = useState<number | undefined>();
  const [province, setProvince] = useState<string | undefined>();

  const { data: years } = useQuery({
    queryKey: ["years"],
    queryFn: () => apiFetch<DimensionResponse>("/meta/years"),
  });
  const { data: provinces } = useQuery({
    queryKey: ["provinces"],
    queryFn: () => apiFetch<DimensionResponse>("/meta/provinces"),
  });

  useEffect(() => {
    if (year !== undefined) {
      return;
    }
    const latestYear = (years?.items ?? [])
      .map((item) => Number(item.year_no))
      .filter((value) => Number.isFinite(value))
      .sort((left, right) => right - left)[0];
    if (latestYear !== undefined) {
      setYear(latestYear);
    }
  }, [year, years]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (year) params.set("year", String(year));
    if (province) params.set("province", province);
    const value = params.toString();
    return value ? `?${value}` : "";
  }, [year, province]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admissions-overview", year, province],
    queryFn: () => apiFetch<Overview>(`/analytics/admissions/overview${queryString}`),
    enabled: year !== undefined,
  });

  const provinceChart = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      legend: { data: ["计划数", "录取数"] },
      grid: { left: 40, right: 20, top: 40, bottom: 40 },
      xAxis: {
        type: "category" as const,
        data: data?.by_province.map((item) => item.province_name) ?? [],
      },
      yAxis: { type: "value" as const },
      series: [
        {
          name: "计划数",
          type: "bar" as const,
          data: data?.by_province.map((item) => item.plan_count) ?? [],
        },
        {
          name: "录取数",
          type: "bar" as const,
          data: data?.by_province.map((item) => item.admitted_count) ?? [],
        },
      ],
    }),
    [data],
  );

  const trendChart = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      legend: { data: ["招生计划数", "实际录取数", "计划完成率"] },
      grid: { left: 50, right: 50, top: 40, bottom: 40 },
      xAxis: {
        type: "category" as const,
        data: data?.year_trend.map((item) => String(item.year_no)) ?? [],
      },
      yAxis: [
        { type: "value" as const, name: "人数" },
        { type: "value" as const, name: "完成率", max: 100 },
      ],
      series: [
        {
          name: "招生计划数",
          type: "bar" as const,
          data: data?.year_trend.map((item) => item.plan_count) ?? [],
        },
        {
          name: "实际录取数",
          type: "bar" as const,
          data: data?.year_trend.map((item) => item.admitted_count) ?? [],
        },
        {
          name: "计划完成率",
          type: "line" as const,
          yAxisIndex: 1,
          data: data?.year_trend.map((item) => Number(item.completion_rate)) ?? [],
        },
      ],
    }),
    [data],
  );

  if (year === undefined || isLoading) {
    return <Spin />;
  }

  if (error) {
    return <Alert type="error" message="招生驾驶舱加载失败" description={error.message} />;
  }

  const metrics = [
    ["招生计划数", data?.metrics.plan_count ?? 0],
    ["实际录取数", data?.metrics.admitted_count ?? 0],
    ["计划完成率", `${data?.metrics.completion_rate ?? 0}%`],
    ["普通类最低分", data?.metrics.min_score ?? "暂无"],
    ["普通类最高分", data?.metrics.max_score ?? "暂无"],
    ["最低录取位次", data?.metrics.min_rank_no ?? "暂无"],
  ];

  return (
    <div className="admissions-overview-page">
      <PageHero
        title="招生驾驶舱"
        description="把计划、录取、分数、位次、省份和专业趋势放在同一决策视野中。"
        actions={
          <Space wrap>
            <Select
              placeholder="招生年度"
              style={{ width: 160 }}
              value={year}
              onChange={setYear}
              options={(years?.items ?? []).map((item) => ({
                value: Number(item.year_no),
                label: String(item.year_no),
              }))}
            />
            <Select
              allowClear
              placeholder="生源省份"
              style={{ width: 180 }}
              value={province}
              onChange={setProvince}
              options={(provinces?.items ?? []).map((item) => ({
                value: String(item.province_name),
                label: String(item.province_name),
              }))}
            />
            {year ? <Tag color="blue">官方汇总</Tag> : null}
            {data?.metrics.score_scope ? <Tag color="default">普通类文化总分</Tag> : null}
            {data ? (
              <ResultExportMenu
                kind="insights"
                title={`${year ?? "当前"}年招生驾驶舱分析`}
                filename={`招生驾驶舱_${year ?? "当前"}`}
                metrics={data.metrics}
                table={{
                  columns: ["专业", "计划数", "录取数", "完成率", "最低分", "最高分", "最低位次"],
                  rows: data.by_major.map((item) => [
                    item.major_name,
                    item.plan_count,
                    item.admitted_count,
                    item.completion_rate,
                    item.min_score,
                    item.max_score,
                    item.min_rank_no,
                  ]),
                }}
                sections={[
                  {
                    title: "分省招生",
                    text: data.by_province
                      .map(
                        (item) =>
                          `${item.province_name}：计划 ${item.plan_count}，录取 ${item.admitted_count}，完成率 ${item.completion_rate}%，最低分 ${item.min_score ?? "暂无"}`,
                      )
                      .join("\n"),
                  },
                  {
                    title: "年度趋势",
                    text: data.year_trend
                      .map(
                        (item) =>
                          `${item.year_no}：计划 ${item.plan_count}，录取 ${item.admitted_count}，完成率 ${item.completion_rate}%`,
                      )
                      .join("\n"),
                  },
                ]}
                metadata={{ year: year ?? null, province: province ?? "全部" }}
              />
            ) : null}
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

      <section className="chart-grid" style={{ marginTop: 20 }}>
        <article className="chart-panel">
          <h2>省份招生计划与录取</h2>
          <LazyEChartsContainer option={provinceChart} />
        </article>
        <article className="chart-panel">
          <h2>年度招生趋势</h2>
          <LazyEChartsContainer option={trendChart} />
        </article>
      </section>

      <section className="chart-panel" style={{ marginTop: 20 }}>
        <h2>专业录取情况</h2>
        <Table
          rowKey="major_name"
          pagination={false}
          dataSource={data?.by_major ?? []}
          columns={[
            { title: "专业", dataIndex: "major_name" },
            { title: "计划数", dataIndex: "plan_count" },
            { title: "录取数", dataIndex: "admitted_count" },
            {
              title: "计划完成率",
              dataIndex: "completion_rate",
              render: (value: string) => (
                <Tag color={Number(value) >= 100 ? "green" : Number(value) >= 90 ? "gold" : "red"}>
                  {value}%
                </Tag>
              ),
            },
            {
              title: "普通类最低分",
              dataIndex: "min_score",
              render: (value: string | number | null) => value ?? "暂无",
            },
            {
              title: "普通类最高分",
              dataIndex: "max_score",
              render: (value: string | number | null) => value ?? "暂无",
            },
            {
              title: "最低位次",
              dataIndex: "min_rank_no",
              render: (value: number | null) => value || "暂无",
            },
          ]}
        />
      </section>
    </div>
  );
}


