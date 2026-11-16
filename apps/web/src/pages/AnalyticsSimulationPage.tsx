import { Alert, App, Button, Card, Col, Empty, InputNumber, Row, Select, Space, Spin, Statistic, Table, Tag } from "antd";
import type { TableColumnsType } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch } from "@/lib/api/client";

type TrendItem = {
  year_no: number;
  plan_count: number;
  admitted_count: number;
  completion_rate: string | number;
};

type MajorItem = {
  major_name: string;
  plan_count: number;
  admitted_count: number;
  completion_rate: string | number;
};

type AdmissionsOverview = {
  by_major: MajorItem[];
};

type AdjustmentRow = {
  key: number;
  major_name?: string;
  plan_delta: number;
};

type SimulationResult = {
  major_name: string;
  plan_delta: number;
  baseline_plan: number;
  baseline_admitted: number;
  baseline_completion_rate: number;
  projected_plan: number;
  projected_admitted: number;
  projected_completion_rate: number;
  projected_score_change: number;
  risk_level: "high" | "medium" | "low";
  choice_count: number;
};

type SimulationResponse = {
  year_no: number | null;
  contains_synthetic: boolean;
  baseline: {
    plan_count: number;
    admitted_count: number;
    completion_rate: number;
  };
  projected: {
    plan_count: number;
    admitted_count: number;
    completion_rate: number;
  };
  results: SimulationResult[];
  unmatched_adjustments: string[];
  message?: string;
  disclaimer: string;
};

const riskLabel = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

export default function PlanSimulationPage() {
  const { message } = App.useApp();
  const [year, setYear] = useState<number | undefined>();
  const [rows, setRows] = useState<AdjustmentRow[]>([{ key: 1, plan_delta: 0 }]);
  const [result, setResult] = useState<SimulationResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const trendQuery = useQuery({
    queryKey: ["analytics-trends", "simulation"],
    queryFn: () => apiFetch<{ items: TrendItem[] }>("/analytics/trends"),
  });

  const latestYear = trendQuery.data?.items?.length
    ? Math.max(...trendQuery.data.items.map((item) => item.year_no))
    : undefined;
  const selectedYear = year ?? latestYear;

  const overviewQuery = useQuery({
    queryKey: ["analytics-overview", "simulation", selectedYear],
    queryFn: () => apiFetch<AdmissionsOverview>(`/analytics/admissions/overview?year=${selectedYear}`),
    enabled: Boolean(selectedYear),
  });

  const majorOptions = useMemo(
    () =>
      (overviewQuery.data?.by_major ?? [])
        .filter((item) => item.plan_count > 0)
        .map((item) => ({
          value: item.major_name,
          label: `${item.major_name}（计划 ${item.plan_count}，完成率 ${item.completion_rate}%）`,
        })),
    [overviewQuery.data],
  );

  function updateRow(key: number, patch: Partial<AdjustmentRow>): void {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addRow(): void {
    setRows((current) => [
      ...current,
      { key: current.length ? Math.max(...current.map((row) => row.key)) + 1 : 1, plan_delta: 0 },
    ]);
  }

  async function handleSimulate(): Promise<void> {
    const adjustments = rows
      .filter((row) => row.major_name && row.plan_delta !== 0)
      .map((row) => ({ major_name: row.major_name as string, plan_delta: row.plan_delta }));
    if (!adjustments.length) {
      message.warning("请至少选择一个专业，并填写非零的计划增减人数");
      return;
    }
    setLoading(true);
    try {
      const response = await apiFetch<SimulationResponse>("/analytics/simulate", {
        method: "POST",
        body: JSON.stringify({ year: selectedYear, adjustments }),
      });
      setResult(response);
      message.success("计划沙盘模拟完成");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "沙盘模拟失败");
    } finally {
      setLoading(false);
    }
  }

  const chartOption = useMemo(() => {
    const results = result?.results ?? [];
    return {
      tooltip: { trigger: "axis" as const },
      legend: { data: ["基准计划", "模拟计划"] },
      xAxis: { type: "category" as const, data: results.map((item) => item.major_name) },
      yAxis: { type: "value" as const },
      series: [
        { name: "基准计划", type: "bar" as const, data: results.map((item) => item.baseline_plan) },
        { name: "模拟计划", type: "bar" as const, data: results.map((item) => item.projected_plan) },
      ],
    };
  }, [result]);

  const columns: TableColumnsType<SimulationResult> = [
    { title: "专业", dataIndex: "major_name", width: 150, fixed: "left" },
    {
      title: "计划变化",
      dataIndex: "plan_delta",
      width: 110,
      render: (value: number) => (
        <Tag color={value > 0 ? "green" : "red"}>{value > 0 ? `+${value}` : value}</Tag>
      ),
    },
    { title: "基准计划", dataIndex: "baseline_plan", width: 100 },
    { title: "模拟计划", dataIndex: "projected_plan", width: 100 },
    { title: "模拟录取", dataIndex: "projected_admitted", width: 100 },
    {
      title: "模拟完成率",
      dataIndex: "projected_completion_rate",
      width: 130,
      render: (value: number) => `${value}%`,
    },
    {
      title: "估计分数变化",
      dataIndex: "projected_score_change",
      width: 130,
      render: (value: number) => `${value > 0 ? "+" : ""}${value}`,
    },
    {
      title: "风险",
      dataIndex: "risk_level",
      width: 100,
      render: (value: SimulationResult["risk_level"]) => (
        <Tag color={value === "high" ? "red" : value === "medium" ? "gold" : "green"}>
          {riskLabel[value]}
        </Tag>
      ),
    },
  ];

  if (trendQuery.isLoading) {
    return <Spin />;
  }

  return (
    <div className="simulation-page">
      <PageHero
        title="招生计划策略沙盘"
        description="在不修改真实计划的前提下，提前观察专业计划调整对录取、完成率和风险的影响。"
      />

      <Card className="report-form" title="设置模拟场景" extra={<Tag color="blue">What-if 分析</Tag>}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Space wrap>
            <span>模拟年度</span>
            <Select
              value={selectedYear}
              onChange={setYear}
              style={{ width: 160 }}
              placeholder="选择年度"
              options={(trendQuery.data?.items ?? []).map((item) => ({
                value: item.year_no,
                label: `${item.year_no} 年`,
              }))}
            />
            <Button onClick={addRow}>添加专业调整</Button>
          </Space>

          {overviewQuery.isLoading ? <Spin /> : null}
          {!overviewQuery.isLoading && !majorOptions.length ? (
            <Empty description="当前年度没有可用于模拟的招生专业" />
          ) : null}

          <Space direction="vertical" style={{ width: "100%" }}>
            {rows.map((row) => (
              <Row gutter={12} key={row.key} align="middle">
                <Col flex="auto">
                  <Select
                    showSearch
                    value={row.major_name}
                    onChange={(value) => updateRow(row.key, { major_name: value })}
                    options={majorOptions}
                    placeholder="选择专业"
                    style={{ width: "100%" }}
                  />
                </Col>
                <Col flex="180px">
                  <InputNumber
                    value={row.plan_delta}
                    onChange={(value) => updateRow(row.key, { plan_delta: Number(value ?? 0) })}
                    addonBefore="计划增减"
                    style={{ width: "100%" }}
                  />
                </Col>
                <Col flex="80px">
                  <Button
                    danger
                    disabled={rows.length === 1}
                    onClick={() => setRows((current) => current.filter((item) => item.key !== row.key))}
                  >
                    删除
                  </Button>
                </Col>
              </Row>
            ))}
          </Space>

          <Button type="primary" loading={loading} onClick={handleSimulate}>
            运行 AI 计划沙盘
          </Button>
        </Space>
      </Card>

      {result ? (
        <>
          {result.contains_synthetic ? (
            <Alert
              type="warning"
              showIcon
              message="当前模拟年度使用模拟数据"
              description="模拟结果仅用于训练和系统功能验证，不代表真实招生结果。"
              style={{ marginBottom: 16 }}
            />
          ) : null}
          {result.unmatched_adjustments.length ? (
            <Alert
              type="warning"
              showIcon
              message="部分专业未匹配"
              description={`未找到：${result.unmatched_adjustments.join("、")}`}
              style={{ marginBottom: 16 }}
            />
          ) : null}

          <Row gutter={16} style={{ marginBottom: 20 }}>
            <Col xs={24} md={8}>
              <Card><Statistic title="模拟年度" value={result.year_no ?? "-"} /></Card>
            </Col>
            <Col xs={24} md={8}>
              <Card><Statistic title="基准招生计划" value={result.baseline.plan_count} suffix="人" /></Card>
            </Col>
            <Col xs={24} md={8}>
              <Card><Statistic title="模拟招生计划" value={result.projected.plan_count} suffix="人" /></Card>
            </Col>
            <Col xs={24} md={8} style={{ marginTop: 16 }}>
              <Card><Statistic title="基准录取" value={result.baseline.admitted_count} suffix="人" /></Card>
            </Col>
            <Col xs={24} md={8} style={{ marginTop: 16 }}>
              <Card><Statistic title="模拟录取" value={result.projected.admitted_count} suffix="人" /></Card>
            </Col>
            <Col xs={24} md={8} style={{ marginTop: 16 }}>
              <Card><Statistic title="模拟完成率" value={result.projected.completion_rate} suffix="%" /></Card>
            </Col>
          </Row>

          <section className="chart-panel" style={{ marginBottom: 20 }}>
            <h2>计划调整前后对比</h2>
            {result.results.length ? (
              <LazyEChartsContainer option={chartOption} height={330} />
            ) : (
              <Empty description="没有可对比的模拟结果" />
            )}
          </section>

          <section>
            <h2>专业模拟明细</h2>
            <Table
              rowKey={(record) => record.major_name}
              columns={columns}
              dataSource={result.results}
              pagination={false}
              scroll={{ x: 1100 }}
              locale={{ emptyText: <Empty description="没有模拟结果" /> }}
            />
          </section>

          <Alert
            type="info"
            showIcon
            message="模型说明"
            description={result.disclaimer}
            style={{ marginTop: 18 }}
          />
        </>
      ) : null}
    </div>
  );
}

