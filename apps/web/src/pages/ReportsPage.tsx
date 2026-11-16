import { DownloadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Radio, Select, Space, Spin, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiDownload, apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type ReportFormat = "docx" | "pdf";
type ReportType = "admissions" | "source" | "comprehensive";

type PreviewResponse = {
  title: string;
  generated_at: string;
  filters: Record<string, string | number | null>;
  summary: string[];
  ai_commentary: string | null;
  insights?: Array<{
    title: string;
    finding: string;
    analysis?: string;
    suggestion?: string;
  }>;
  admissions: {
    metrics: {
      plan_count: number;
      admitted_count: number;
      completion_rate: number;
      min_score: string | number | null;
      min_rank_no: number | null;
    };
  } | null;
  source: {
    metrics: {
      candidate_count: number;
      enrolled_count: number;
      enrollment_rate: number;
    };
  } | null;
};

type DimensionResponse = {
  items: Array<Record<string, string | number>>;
};

export default function ReportsPage() {
  const { message } = App.useApp();
  const [reportType, setReportType] = useState<ReportType>("admissions");
  const [fileFormat, setFileFormat] = useState<ReportFormat>("docx");
  const [year, setYear] = useState<number | undefined>(2025);
  const [province, setProvince] = useState<string | undefined>();
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const { data: years } = useQuery({
    queryKey: ["report-years"],
    queryFn: () => apiFetch<DimensionResponse>("/meta/years"),
  });
  const { data: provinces } = useQuery({
    queryKey: ["report-provinces"],
    queryFn: () => apiFetch<DimensionResponse>("/meta/provinces"),
  });

  function requestPayload() {
    return {
      report_type: reportType,
      file_format: fileFormat,
      year,
      province: province ?? null,
      major: null,
    };
  }

  async function handlePreview(): Promise<void> {
    setLoading(true);
    try {
      const response = await apiFetch<PreviewResponse>("/reports/preview", {
        method: "POST",
        body: JSON.stringify(requestPayload()),
      });
      setPreview(response);
      message.success("报告预览已生成");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "报告预览失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleDownload(): Promise<void> {
    setLoading(true);
    try {
      const blob = await apiDownload("/reports/generate", {
        method: "POST",
        body: JSON.stringify(requestPayload()),
      });
      const extension = fileFormat === "docx" ? "docx" : "pdf";
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${reportType === "source" ? "生源分析报告" : "招生分析报告"}.${extension}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      message.success("报告下载已开始");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "报告生成失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="reports-page">
      <PageHero
        title="报告中心"
        description="把当前数据、核心结论和管理建议收束为可交付的正式报告。"
      />

      <section className="report-form">
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <div>
            <div className="metric-label">报告类型</div>
            <Radio.Group
              value={reportType}
              onChange={(event) => setReportType(event.target.value)}
              options={[
                { label: "招生分析", value: "admissions" },
                { label: "生源分析", value: "source" },
                { label: "综合分析", value: "comprehensive" },
              ]}
            />
          </div>
          <Space wrap>
            <Select
              allowClear
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
            <Select
              value={fileFormat}
              style={{ width: 140 }}
              onChange={setFileFormat}
              options={[
                { value: "docx", label: "Word" },
                { value: "pdf", label: "PDF" },
              ]}
            />
          </Space>
          <Space>
            <Button onClick={handlePreview} loading={loading}>
              生成预览
            </Button>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              onClick={handleDownload}
              loading={loading}
            >
              生成并下载
            </Button>
          </Space>
        </Space>
      </section>

      {loading ? <Spin style={{ marginTop: 20 }} /> : null}

      {preview ? (
        <section className="report-preview">
          <h2>{preview.title}</h2>
          <p>生成时间：{preview.generated_at}</p>
          <p>
            筛选条件：
            {preview.filters.year ? ` 年度 ${preview.filters.year}` : " 全部年度"}
            {preview.filters.province ? ` / 省份 ${preview.filters.province}` : ""}
          </p>

          {preview.admissions ? (
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag color="blue">计划 {preview.admissions.metrics.plan_count}</Tag>
              <Tag color="green">录取 {preview.admissions.metrics.admitted_count}</Tag>
              <Tag color="gold">完成率 {preview.admissions.metrics.completion_rate}%</Tag>
            </Space>
          ) : null}

          {preview.source ? (
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag color="blue">生源 {preview.source.metrics.candidate_count}</Tag>
              <Tag color="green">报到 {preview.source.metrics.enrolled_count}</Tag>
              <Tag color="gold">报到率 {preview.source.metrics.enrollment_rate}%</Tag>
            </Space>
          ) : null}

          <h3>核心结论</h3>
          {preview.summary.map((item) => (
            <Alert key={item} type="info" message={item} style={{ marginBottom: 8 }} />
          ))}

          {preview.insights && preview.insights.length > 0 ? (
            <>
              <h3>深层分析</h3>
              {preview.insights.map((item) => (
                <Alert
                  key={`${item.title}-${item.finding}`}
                  type="info"
                  message={item.title}
                  description={
                    <div>
                      <div>{item.finding}</div>
                      {item.analysis ? <div style={{ marginTop: 4 }}>{item.analysis}</div> : null}
                      {item.suggestion ? <div style={{ marginTop: 4 }}>建议：{item.suggestion}</div> : null}
                    </div>
                  }
                  style={{ marginBottom: 8 }}
                />
              ))}
            </>
          ) : null}

          {preview.ai_commentary ? (
            <>
              <h3>AI 管理建议</h3>
              <Alert
                type="success"
                message="由本地规则与知识库生成，数字仍来自数据库"
                description={<div style={{ whiteSpace: "pre-wrap" }}>{preview.ai_commentary}</div>}
              />
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}




