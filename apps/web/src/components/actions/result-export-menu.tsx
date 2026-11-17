import { DownloadOutlined } from "@ant-design/icons";
import { App, Button, Dropdown } from "antd";
import { useState } from "react";

import { apiDownload } from "@/lib/api/client";

export type ExportFormat = "xlsx" | "csv" | "docx" | "pdf" | "md" | "json";
export type ExportKind =
  | "query"
  | "insights"
  | "anomaly"
  | "forecast"
  | "simulation"
  | "quality"
  | "audit";

export type ExportTable = {
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
};

type ResultExportMenuProps = {
  kind: ExportKind;
  title: string;
  filename?: string;
  question?: string;
  answer?: string;
  sections?: Array<{ title: string; text: string }>;
  metrics?: Record<string, unknown>;
  table?: ExportTable | null;
  metadata?: Record<string, unknown>;
  disabled?: boolean;
};

const formatLabels: Record<ExportFormat, string> = {
  xlsx: "Excel 工作簿",
  csv: "CSV 明细",
  docx: "Word 文档",
  pdf: "PDF 文档",
  md: "Markdown",
  json: "JSON 原始结果",
};

function safeBaseName(value: string): string {
  return value.replace(/[\\/:*?"<>|]+/g, "_").trim() || "分析结果";
}

export function ResultExportMenu({
  kind,
  title,
  filename,
  question,
  answer,
  sections = [],
  metrics = {},
  table = null,
  metadata = {},
  disabled = false,
}: ResultExportMenuProps) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);

  async function handleDownload(format: ExportFormat): Promise<void> {
    setLoading(true);
    try {
      const blob = await apiDownload("/exports/result", {
        method: "POST",
        body: JSON.stringify({
          kind,
          format,
          title,
          filename: safeBaseName(filename ?? title),
          question,
          answer,
          sections,
          metrics,
          table,
          metadata,
        }),
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${safeBaseName(filename ?? title)}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      message.success(`已导出${formatLabels[format]}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "导出失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dropdown
      disabled={disabled || loading}
      trigger={["click"]}
      menu={{
        items: (Object.keys(formatLabels) as ExportFormat[]).map((format) => ({
          key: format,
          label: formatLabels[format],
        })),
        onClick: ({ key }) => void handleDownload(key as ExportFormat),
      }}
    >
      <Button size="small" icon={<DownloadOutlined />} loading={loading} disabled={disabled}>
        导出
      </Button>
    </Dropdown>
  );
}
