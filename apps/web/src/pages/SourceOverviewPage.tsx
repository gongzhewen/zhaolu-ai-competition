import { Alert, Select, Space, Spin, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ResultExportMenu } from "@/components/actions/result-export-menu";
import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch } from "@/lib/api/client";

type SourceOverview = {
  metrics: {
    official_total_count: number;
    candidate_count: number;
    detail_count: number;
    coverage_rate: number;
    coverage_basis: string;
    detail_complete: boolean;
    enrolled_count: number;
    enrollment_rate: number;
    enrollment_data_available: boolean;
  };
  by_province: Array<{
    province_name: string;
    candidate_count: number;
    enrolled_count: number;
    avg_score: string | number | null;
  }>;
  year_no: number;
  by_channel: Array<{
    channel_name: string;
    candidate_count: number;
    enrolled_count: number;
    avg_score: string | number | null;
  }>;
};

export default function SourceOverviewPage() {
  const [year, setYear] = useState<number | undefined>();
  const { data: years } = useQuery({
    queryKey: ["source-years"],
    queryFn: () => apiFetch<{ items: Array<{ id: number; year_no: number }> }>("/meta/years"),
  });
  const { data, isLoading, error } = useQuery({
    queryKey: ["source-overview", year],
    queryFn: () =>
      apiFetch<SourceOverview>(
        `/analytics/source/overview${year ? `?year=${year}` : ""}`,
      ),
  });

  const channelChart = useMemo(
    () => ({
      tooltip: { trigger: "item" as const },
      legend: { bottom: 0 },
      series: [
        {
          name: "渠道生源",
          type: "pie" as const,
          radius: ["38%", "68%"],
          data: data?.by_channel.map((item) => ({
            name: item.channel_name,
            value: item.candidate_count,
          })) ?? [],
        },
      ],
    }),
    [data],
  );

  if (isLoading) {
    return <Spin />;
  }

  if (error) {
    return <Alert type="error" message="生源分析加载失败" description={error.message} />;
  }

  const metrics = [
    ["录取总人数", data?.metrics.coverage_basis === "official" ? data.metrics.official_total_count : "未提供"],
    ["生源明细", data?.metrics.detail_count ?? data?.metrics.candidate_count ?? 0],
    ["明细覆盖率", data?.metrics.coverage_basis === "official" ? `${data.metrics.coverage_rate}%` : "待核验"],
    ["已报到（明细）", data?.metrics.enrollment_data_available ? data.metrics.enrolled_count : "未导入"],
  ];

  return (
    <div className="source-overview-page">
      <PageHero
        title="生源分析"
        description="从省份、渠道与报到状态三个方向定位生源质量和覆盖缺口。"
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
            {year && year <= 2025 ? <Tag color="orange">历史年度</Tag> : null}
            {data ? (
              <ResultExportMenu
                kind="insights"
                title={`${data.year_no}年生源分析`}
                filename={`生源分析_${data.year_no}`}
                metrics={data.metrics}
                table={{
                  columns: ["渠道", "生源人数", "报到人数", "平均分"],
                  rows: data.by_channel.map((item) => [
                    item.channel_name,
                    item.candidate_count,
                    item.enrolled_count,
                    item.avg_score,
                  ]),
                }}
                sections={[
                  {
                    title: "省份生源分布",
                    text: data.by_province
                      .map(
                        (item) =>
                          `${item.province_name}：生源 ${item.candidate_count}，报到 ${item.enrolled_count}，平均分 ${item.avg_score ?? "暂无"}`,
                      )
                      .join("\n"),
                  },
                ]}
                metadata={{
                  year: data.year_no,
                  coverage_basis: data.metrics.coverage_basis,
                }}
              />
            ) : null}
          </Space>
        }
      />

      {data && data.metrics.coverage_basis !== "official" ? (
        <Alert
          type="info"
          showIcon
          message="官方录取总数待核验"
          description={`${data.year_no} 年已导入考生明细 ${data.metrics.detail_count} 人，但尚未提供官方录取总数，因此不能计算可信覆盖率，也不能把明细人数直接视为完整录取总数。`}
          style={{ marginBottom: 18 }}
        />
      ) : data && !data.metrics.detail_complete ? (
        <Alert
          type="warning"
          showIcon
          message={`生源明细覆盖率为 ${data.metrics.coverage_rate}%`}
          description={`${data.year_no} 年官方录取总数为 ${data.metrics.official_total_count} 人，当前导入的考生明细为 ${data.metrics.detail_count} 人。省份和渠道分布仅统计已导入明细，不代表全部生源。`}
          style={{ marginBottom: 18 }}
        />
      ) : null}

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
          <h2>渠道生源分布（已导入明细）</h2>
          <LazyEChartsContainer option={channelChart} />
        </article>
        <article className="chart-panel">
          <h2>省份生源情况（已导入明细）</h2>
          <Table
            rowKey="province_name"
            pagination={false}
            dataSource={data?.by_province ?? []}
            columns={[
              { title: "省份", dataIndex: "province_name" },
              { title: "生源人数", dataIndex: "candidate_count" },
              { title: "报到人数", dataIndex: "enrolled_count" },
              { title: "平均分", dataIndex: "avg_score" },
            ]}
          />
        </article>
      </section>

      <section className="chart-panel" style={{ marginTop: 20 }}>
        <h2>渠道明细（已导入明细）</h2>
        <Table
          rowKey="channel_name"
          pagination={false}
          dataSource={data?.by_channel ?? []}
          columns={[
            { title: "渠道", dataIndex: "channel_name" },
            { title: "生源人数", dataIndex: "candidate_count" },
            { title: "报到人数", dataIndex: "enrolled_count" },
            { title: "平均分", dataIndex: "avg_score" },
          ]}
        />
      </section>
    </div>
  );
}


