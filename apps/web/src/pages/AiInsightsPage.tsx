import { Alert, App, Button, Card, Col, Row, Select, Space, Spin, Statistic, Table, Tabs, Tag } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch } from "@/lib/api/client";

type Insight = {
  year_no?: number;
  title: string;
  finding: string;
  analysis?: string;
  suggestion: string;
  risk_level?: string;
  evidence: string[] | string;
};

type YearSummary = {
  year_no: number;
  metrics: {
    plan_count: number;
    admitted_count: number;
    official_admitted_count: number;
    plan_gap_count: number | null;
    completion_rate: number | null;
    candidate_count: number;
    candidate_profile_count: number;
    source_detail_count: number;
    detail_gap_count: number;
    source_coverage_rate: number;
    coverage_basis: string;
    detail_complete: boolean;
    enrolled_count: number;
    enrollment_rate: number;
    enrollment_data_available: boolean;
    enrollment_record_count: number;
    data_quality_status: string;
    top_major_name?: string | null;
    top_major_choices?: number;
    top_major_share?: number;
    plan_yoy_rate?: number | null;
    admitted_yoy_rate?: number | null;
    candidate_yoy_rate?: number | null;
  };
  insights: Insight[];
  detail?: {
    candidate?: {
      metrics: { candidate_count: number };
      by_gender?: Array<{ name: string; count: number }>;
      by_region?: Array<{ name: string; count: number }>;
      by_exam_type?: Array<{ name: string; count: number }>;
      by_subject?: Array<{ name: string; count: number }>;
    } | null;
    subjects?: {
      subjects?: Array<{
        subject_name: string;
        record_count: number;
        candidate_count: number;
        avg_score: number | null;
        min_score: number | null;
        max_score: number | null;
        score_stddev: number | null;
      }>;
    } | null;
    choices?: {
      metrics: { choice_count: number; candidate_count: number };
      majors?: Array<{ major_name: string; choice_count: number; candidate_count: number }>;
    } | null;
    medical?: {
      medical_results?: Array<{ result_name: string; count: number }>;
    } | null;
    major_detail?: Array<{
      major_name: string;
      choice_count: number;
      candidate_count: number;
      plan_count: number;
      completion_rate?: number | null;
      choice_per_plan?: number | null;
    }>;
  };
};

type TrendItem = {
  year_no: number;
  plan_count: number;
  admitted_count: number;
  completion_rate: number | null;
  candidate_count: number;
  source_detail_count: number;
  source_coverage_rate: number;
  coverage_basis: string;
  enrolled_count: number;
  enrollment_rate: number;
  enrollment_data_available: boolean;
  plan_yoy_rate?: number | null;
  admitted_yoy_rate?: number | null;
  candidate_yoy_rate?: number | null;
};

type InsightsResponse = {
  scope: string;
  provider: string;
  generated_at: string;
  years: number[];
  selected_year: number | null;
  trend: TrendItem[];
  year_summaries: YearSummary[];
  cross_year_insights: Insight[];
  insights: Insight[];
  detail?: {
    candidate?: {
      metrics: { candidate_count: number };
      by_gender?: Array<{ name: string; count: number }>;
      by_region?: Array<{ name: string; count: number }>;
      by_exam_type?: Array<{ name: string; count: number }>;
      by_subject?: Array<{ name: string; count: number }>;
    } | null;
    subjects?: {
      subjects?: Array<{
        subject_name: string;
        record_count: number;
        candidate_count: number;
        avg_score: number | null;
        min_score: number | null;
        max_score: number | null;
        score_stddev: number | null;
      }>;
    } | null;
    choices?: {
      metrics: { choice_count: number; candidate_count: number };
      majors?: Array<{ major_name: string; choice_count: number; candidate_count: number }>;
    } | null;
    medical?: {
      medical_results?: Array<{ result_name: string; count: number }>;
    } | null;
    major_detail?: Array<{
      major_name: string;
      choice_count: number;
      candidate_count: number;
      plan_count: number;
      completion_rate?: number | null;
      choice_per_plan?: number | null;
    }>;
  };
};

const scopeOptions = [
  { value: "all", label: "综合洞察" },
  { value: "admissions", label: "招生计划" },
  { value: "candidate", label: "考生画像" },
  { value: "subject", label: "学科成绩" },
  { value: "major", label: "专业志愿" },
  { value: "medical", label: "体检摘要" },
];

const riskColors: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "green",
  unknown: "default",
};

const riskLabels: Record<string, string> = {
  high: "高风险",
  medium: "关注",
  low: "正常",
  unknown: "待补数",
};

const qualityLabels: Record<string, { label: string; color: string }> = {
  complete: { label: "明细完整", color: "green" },
  partial: { label: "部分覆盖", color: "orange" },
  missing: { label: "明细缺失", color: "red" },
  unverified: { label: "基数待核验", color: "default" },
};

function signedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "不适用";
  }
  const target = value;
  return `${target > 0 ? "+" : ""}${target.toFixed(2)}%`;
}

function InsightCards({ items }: { items: Insight[] }) {
  return (
    <div className="insight-grid">
      {items.map((insight) => (
        <Card
          key={`${insight.year_no ?? "cross"}-${insight.title}`}
          title={insight.title}
          className="insight-card"
          extra={insight.risk_level ? <Tag color={riskColors[insight.risk_level] ?? "default"}>{riskLabels[insight.risk_level] ?? insight.risk_level}</Tag> : null}
        >
          <p><strong>发现：</strong>{insight.finding}</p>
          {insight.analysis ? <p><strong>分析：</strong>{insight.analysis}</p> : null}
          <p><strong>建议：</strong>{insight.suggestion}</p>
          <Space wrap>
            {(Array.isArray(insight.evidence) ? insight.evidence : [insight.evidence]).map((source) => (
              <Tag key={source} color="blue">{source}</Tag>
            ))}
          </Space>
        </Card>
      ))}
    </div>
  );
}

function Share({ part, total }: { part: number; total: number }) {
  return total > 0 ? `${(part / total * 100).toFixed(2)}%` : "不适用";
}

function CandidateDetail({ detail }: { detail: NonNullable<YearSummary["detail"]> }) {
  const candidate = detail.candidate;
  if (!candidate) return null;
  const total = candidate.metrics?.candidate_count ?? 0;
  const columns = [
    { title: "维度", dataIndex: "name", key: "name" },
    { title: "人数", dataIndex: "count", key: "count" },
    { title: "占比", dataIndex: "share", key: "share" },
  ];
  function rows(items: Array<{ name: string; count: number }> = []) {
    return items.map((item) => ({ key: item.name, name: item.name, count: item.count, share: <Share part={item.count} total={total} /> }));
  }
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} md={12}><Card title="性别结构" size="small"><Table size="small" pagination={false} columns={columns} dataSource={rows(candidate.by_gender)} /></Card></Col>
      <Col xs={24} md={12}><Card title="科类结构" size="small"><Table size="small" pagination={false} columns={columns} dataSource={rows(candidate.by_subject)} /></Card></Col>
      <Col xs={24} md={12}><Card title="考试类型结构" size="small"><Table size="small" pagination={false} columns={columns} dataSource={rows(candidate.by_exam_type)} /></Card></Col>
      <Col xs={24} md={12}><Card title="地区结构" size="small"><Table size="small" pagination={false} columns={columns} dataSource={rows(candidate.by_region)} /></Card></Col>
    </Row>
  );
}

function SubjectDetail({ detail }: { detail: NonNullable<YearSummary["detail"]> }) {
  const rows = detail.subjects?.subjects ?? [];
  if (!rows.length) return null;
  return (
    <Card title="逐科成绩分析" size="small">
      <Table
        size="small"
        pagination={false}
        rowKey={(row) => String(row.subject_name)}
        columns={[
          { title: "科目", dataIndex: "subject_name", key: "subject_name" },
          { title: "参考人数", dataIndex: "candidate_count", key: "candidate_count" },
          { title: "平均分", dataIndex: "avg_score", key: "avg_score" },
          { title: "最低分", dataIndex: "min_score", key: "min_score" },
          { title: "最高分", dataIndex: "max_score", key: "max_score" },
          { title: "标准差", dataIndex: "score_stddev", key: "score_stddev" },
        ]}
        dataSource={rows}
      />
    </Card>
  );
}

function MajorDetail({ detail }: { detail: NonNullable<YearSummary["detail"]> }) {
  const rows = detail.major_detail ?? [];
  if (!rows.length) return null;
  return (
    <Card title="专业志愿热度与志愿率" size="small">
      <Table
        size="small"
        pagination={{ pageSize: 10 }}
        rowKey={(row) => String(row.major_name)}
        columns={[
          { title: "专业", dataIndex: "major_name", key: "major_name" },
          { title: "招生计划", dataIndex: "plan_count", key: "plan_count" },
          { title: "志愿次数", dataIndex: "choice_count", key: "choice_count" },
          { title: "志愿人数", dataIndex: "candidate_count", key: "candidate_count" },
          { title: "志愿/计划", dataIndex: "choice_per_plan", key: "choice_per_plan" },
          { title: "完成率", dataIndex: "completion_rate", key: "completion_rate" },
        ]}
        dataSource={rows}
      />
    </Card>
  );
}

function MedicalDetail({ detail }: { detail: NonNullable<YearSummary["detail"]> }) {
  const rows = detail.medical?.medical_results ?? [];
  if (!rows.length) return null;
  return (
    <Card title="体检结论分布" size="small">
      <Table
        size="small"
        pagination={false}
        rowKey={(row) => String(row.result_name)}
        columns={[
          { title: "体检结论", dataIndex: "result_name", key: "result_name" },
          { title: "人数", dataIndex: "count", key: "count" },
        ]}
        dataSource={rows}
      />
    </Card>
  );
}

export default function AiInsightsPage() {
  const { message } = App.useApp();
  const [scope, setScope] = useState("all");
  const [selectedYear, setSelectedYear] = useState<number | undefined>();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<InsightsResponse | null>(null);

  const loadInsights = useCallback(async (targetScope: string, notify = false): Promise<void> => {
    setLoading(true);
    try {
      const response = await apiFetch<InsightsResponse>(`/ai/insights?scope=${targetScope}`);
      setData(response);
      setSelectedYear(response.selected_year ?? response.years.at(-1));
      if (notify) {
        message.success("深度洞察已生成");
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "AI 洞察生成失败");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void loadInsights(scope);
  }, [loadInsights, scope]);

  function handleGenerate(): void {
    void loadInsights(scope, true);
  }

  const selectedSummary = useMemo(
    () => data?.year_summaries.find((item) => item.year_no === selectedYear),
    [data, selectedYear],
  );

  const volumeTrendOption = useMemo(() => ({
    tooltip: { trigger: "axis" as const },
    legend: { data: ["招生计划", "实际录取", "生源明细", "已报到"] },
    grid: { left: 58, right: 28, top: 45, bottom: 40 },
    xAxis: { type: "category" as const, data: data?.trend.map((item) => String(item.year_no)) ?? [] },
    yAxis: { type: "value" as const, name: "人数" },
    series: [
      { name: "招生计划", type: "line" as const, smooth: true, data: data?.trend.map((item) => item.plan_count) ?? [] },
      { name: "实际录取", type: "line" as const, smooth: true, data: data?.trend.map((item) => item.admitted_count) ?? [] },
      { name: "生源明细", type: "line" as const, smooth: true, data: data?.trend.map((item) => item.source_detail_count) ?? [] },
      { name: "已报到", type: "line" as const, smooth: true, data: data?.trend.map((item) => item.enrolled_count) ?? [] },
    ],
  }), [data]);

  const rateTrendOption = useMemo(() => ({
    tooltip: { trigger: "axis" as const, valueFormatter: (value: number) => `${value}%` },
    legend: { data: ["计划完成率", "明细覆盖率"] },
    grid: { left: 58, right: 28, top: 45, bottom: 40 },
    xAxis: { type: "category" as const, data: data?.trend.map((item) => String(item.year_no)) ?? [] },
    yAxis: { type: "value" as const, min: 0, max: 100, name: "百分比", axisLabel: { formatter: "{value}%" } },
    series: [
      { name: "计划完成率", type: "line" as const, smooth: true, data: data?.trend.map((item) => item.completion_rate) ?? [] },
      {
        name: "明细覆盖率",
        type: "line" as const,
        smooth: true,
        data: data?.trend.map((item) => item.coverage_basis === "official" ? item.source_coverage_rate : null) ?? [],
      },
    ],
  }), [data]);

  return (
    <div className="ai-insights-page">
      <PageHero
        title="AI 数据洞察"
        description="沿着年度、考生、成绩、志愿和体检维度逐层追问，把数据变化转化为可执行判断。"
        actions={
          <Space>
            <Select value={scope} onChange={setScope} options={scopeOptions} style={{ width: 180 }} />
            <Button type="primary" onClick={handleGenerate} loading={loading}>生成深度洞察</Button>
          </Space>
        }
      />

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="统计口径"
        description="所有年度按录取年度独立统计，同比仅与上一年度比较；生源明细与官方录取总数分开核算。报到名单未导入时显示“未导入”，不代表真实零报到。"
      />

      {loading && !data ? <Spin /> : null}

      {data ? (
        <>
          <Space style={{ marginBottom: 16 }}>
            <Tag color="blue">范围：{data.scope}</Tag>
            <Tag color="default">生成方式：本地规则与知识库</Tag>
            <Tag>年度：{data.years.join("、")}</Tag>
            <Tag>生成时间：{data.generated_at}</Tag>
          </Space>

          <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
            <Col xs={24} xl={14}>
              <Card title="跨年度规模趋势" bordered={false} loading={loading}>
                <LazyEChartsContainer option={volumeTrendOption} height={340} />
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card title="执行率与数据覆盖率" bordered={false} loading={loading}>
                <LazyEChartsContainer option={rateTrendOption} height={340} />
              </Card>
            </Col>
          </Row>

          {selectedSummary ? (
            <Card size="small" style={{ marginBottom: 16 }}>
              <Space wrap>
                <strong>{selectedSummary.year_no} 年口径</strong>
                <Tag color={qualityLabels[selectedSummary.metrics.data_quality_status]?.color ?? "default"}>
                  {qualityLabels[selectedSummary.metrics.data_quality_status]?.label ?? selectedSummary.metrics.data_quality_status}
                </Tag>
                <span>
                  官方录取 {selectedSummary.metrics.coverage_basis === "official" ? `${selectedSummary.metrics.official_admitted_count} 人` : "未提供"}
                </span>
                <span>
                  明细缺口 {selectedSummary.metrics.coverage_basis === "official" ? `${selectedSummary.metrics.detail_gap_count} 人` : "待核验"}
                </span>
                <span>考生画像匹配 {selectedSummary.metrics.candidate_profile_count || "未启用"} 人</span>
              </Space>
            </Card>
          ) : null}

          <Tabs
            activeKey={selectedYear ? String(selectedYear) : undefined}
            onChange={(value) => setSelectedYear(Number(value))}
            items={(data.year_summaries ?? []).map((summary) => ({
              key: String(summary.year_no),
              label: `${summary.year_no} 年`,
              children: (
                <>
                  <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
                    <Col xs={12} md={6}><Card><Statistic title="招生计划" value={summary.metrics.plan_count} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="实际录取" value={summary.metrics.admitted_count} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="官方录取总数" value={summary.metrics.coverage_basis === "official" ? summary.metrics.official_admitted_count : "未提供"} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="录取较计划" value={summary.metrics.plan_gap_count ?? "不适用"} prefix={summary.metrics.plan_gap_count !== null && summary.metrics.plan_gap_count > 0 ? "+" : ""} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="计划完成率" value={summary.metrics.completion_rate ?? "数据缺失"} suffix={summary.metrics.completion_rate !== null ? "%" : undefined} precision={summary.metrics.completion_rate !== null ? 2 : undefined} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="生源明细" value={summary.metrics.source_detail_count} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="明细缺口" value={summary.metrics.coverage_basis === "official" ? summary.metrics.detail_gap_count : "待核验"} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="明细覆盖率" value={summary.metrics.coverage_basis === "official" ? summary.metrics.source_coverage_rate : "待核验"} suffix={summary.metrics.coverage_basis === "official" ? "%" : undefined} precision={summary.metrics.coverage_basis === "official" ? 2 : undefined} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="已报到" value={summary.metrics.enrollment_data_available ? summary.metrics.enrolled_count : "未导入"} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="报到率" value={summary.metrics.enrollment_data_available ? summary.metrics.enrollment_rate : "未导入"} suffix={summary.metrics.enrollment_data_available ? "%" : undefined} precision={summary.metrics.enrollment_data_available ? 2 : undefined} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="录取同比" value={signedPercent(summary.metrics.admitted_yoy_rate)} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="生源同比" value={signedPercent(summary.metrics.candidate_yoy_rate)} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="最高志愿专业" value={summary.metrics.top_major_name ?? "暂无"} /></Card></Col>
                    <Col xs={12} md={6}><Card><Statistic title="最高专业志愿占比" value={summary.metrics.top_major_share ?? 0} suffix="%" precision={2} /></Card></Col>
                  </Row>
                  <h2>{summary.year_no} 年深度洞察</h2>
                  <InsightCards items={summary.insights} />

                  {summary.detail ? (
                    <div style={{ marginTop: 20, display: "grid", gap: 16 }}>
                      {scope === "candidate" ? <CandidateDetail detail={summary.detail} /> : null}
                      {scope === "subject" ? <SubjectDetail detail={summary.detail} /> : null}
                      {scope === "major" ? <MajorDetail detail={summary.detail} /> : null}
                      {scope === "medical" ? <MedicalDetail detail={summary.detail} /> : null}
                    </div>
                  ) : null}
                </>
              ),
            }))}
          />

          <section style={{ marginTop: 28 }}>
            <h2>跨年度分析</h2>
            <InsightCards items={data.cross_year_insights} />
          </section>
        </>
      ) : null}
    </div>
  );
}

