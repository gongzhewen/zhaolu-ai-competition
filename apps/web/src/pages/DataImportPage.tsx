import { DownloadOutlined, InboxOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Upload,
} from "antd";
import type { UploadFile } from "antd";
import { useEffect, useMemo, useState } from "react";

import { apiDownload, apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type ImportForm = {
  source_type: string;
  data_type: string;
  year?: number;
  data_version?: string;
  file: UploadFile[];
};

type JobStatus = {
  job_id: number;
  status: string;
  data_type: string | null;
  file_name: string | null;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  mapping_confirmed: boolean;
  error_message: string | null;
};

type PreviewResponse = {
  job_id: number;
  headers: string[];
  mapping: Record<string, string | null>;
  preview: Array<Record<string, string | number | null>>;
};

type Issue = {
  row_no: number;
  error_message: string;
};

const dataTypeLabels: Record<string, string> = {
  plan: "招生计划",
  admission: "录取数据",
  enrollment: "报到情况",
  score_line: "分数线",
  consultation: "咨询数据",
};

const dataTypeOptions = [
  { value: "plan", label: "招生计划" },
  { value: "admission", label: "录取数据" },
  { value: "enrollment", label: "报到情况" },
  { value: "score_line", label: "分数线" },
  { value: "consultation", label: "咨询数据" },
];

const targetOptions = [
  { value: "", label: "忽略" },
  { value: "year", label: "招生年度" },
  { value: "province", label: "省份/生源地" },
  { value: "batch", label: "批次" },
  { value: "subject", label: "科类" },
  { value: "major_code", label: "专业代码" },
  { value: "major_name", label: "专业名称" },
  { value: "plan_type", label: "计划类型" },
  { value: "plan_count", label: "计划数" },
  { value: "admitted_count", label: "录取数" },
  { value: "min_score", label: "最低分" },
  { value: "avg_score", label: "平均分" },
  { value: "max_score", label: "最高分" },
  { value: "min_rank_no", label: "最低位次" },
  { value: "candidate_key", label: "考生编号/考生号" },
  { value: "student_name", label: "考生姓名" },
  { value: "score", label: "成绩/投档分" },
  { value: "rank_no", label: "位次" },
  { value: "volunteer_order", label: "志愿顺序" },
  { value: "channel", label: "渠道" },
  { value: "consultation_type", label: "咨询类型" },
  { value: "status", label: "状态" },
  { value: "contacted_at", label: "联系时间" },
  { value: "converted", label: "是否转化" },
  { value: "admit_type", label: "录取类型" },
  { value: "is_enrolled", label: "是否报到" },
  { value: "enrolled_at", label: "报到日期" },
  { value: "remark", label: "备注" },
  { value: "tuition", label: "学费" },
  { value: "source_type", label: "来源类型" },
  { value: "data_version", label: "数据版本" },
];

const requiredFieldsByType: Record<string, string[]> = {
  plan: ["year", "province", "major_name", "plan_count"],
  admission: ["year", "province", "major_name"],
  score_line: ["year", "province"],
  consultation: ["year", "province"],
  enrollment: ["year"],
};

const requiredFieldLabels: Record<string, string> = {
  year: "招生年度（year）",
  province: "省份（province）",
  major_name: "专业名称（major_name）",
  plan_count: "计划数（plan_count）",
};

function normalizeTargetField(value: string | null | undefined): string | null {
  return value ? value.trim().replaceAll("-", "_").toLowerCase() : null;
}

const statusStep: Record<string, number> = {
  AWAITING_MAPPING: 1,
  READY_TO_IMPORT: 2,
  QUEUED_FOR_IMPORT: 3,
  IMPORTING: 3,
  IMPORTED: 4,
  VALIDATION_FAILED: 1,
  IMPORT_FAILED: 2,
};

export default function DataImportPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<ImportForm>();
  const selectedDataType = Form.useWatch("data_type", form);
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [issues, setIssues] = useState<Issue[]>([]);

  const currentStep = useMemo(
    () => (job ? statusStep[job.status] ?? 1 : 0),
    [job],
  );

  useEffect(() => {
    if (!job?.job_id || !["QUEUED_FOR_IMPORT", "IMPORTING"].includes(job.status)) {
      return;
    }

    const timer = window.setInterval(async () => {
      try {
        const latest = await apiFetch<JobStatus>(`/data/imports/${job.job_id}`);
        setJob(latest);
        if (latest.status === "IMPORTED") {
          message.success("数据导入完成");
        }
        if (latest.status === "IMPORT_FAILED") {
          message.error(latest.error_message ?? "数据导入失败");
        }
      } catch (error) {
        message.error(error instanceof Error ? error.message : "任务状态查询失败");
      }
    }, 2000);

    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  async function handleDownloadTemplate(): Promise<void> {
    try {
      const dataType = selectedDataType || "plan";
      const blob = await apiDownload(`/data/template?data_type=${dataType}`);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${dataType}_template.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      message.success("标准模板下载已开始");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "模板下载失败");
    }
  }

  async function handleDownloadEnrollmentTemplate(): Promise<void> {
    try {
      const blob = await apiDownload("/data/enrollment/template");
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "报到情况导入模板.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      message.success("报到情况模板已下载");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "模板下载失败");
    }
  }

  async function handleUpload(values: ImportForm): Promise<void> {
    const file = values.file?.[0]?.originFileObj;
    if (!file) {
      message.error("请先选择文件");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("source_type", values.source_type);
    formData.append("data_type", values.data_type);
    if (values.year) {
      formData.append("year", String(values.year));
    }
    if (values.data_version) {
      formData.append("data_version", values.data_version);
    }

    setSubmitting(true);
    try {
      const response = await apiFetch<JobStatus>("/data/imports", {
        method: "POST",
        body: formData,
      });
      setJob(response);
      const previewData = await apiFetch<PreviewResponse>(
        `/data/imports/${response.job_id}/preview`,
      );
      setPreview(previewData);
      setMapping(previewData.mapping);
      setIssues([]);
      message.success("文件解析完成，请确认字段映射");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "文件上传失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirmMapping(): Promise<void> {
    if (!job) {
      return;
    }
    try {
      const normalizedMapping = Object.fromEntries(
        Object.entries(mapping).map(([source, target]) => [source, target || null]),
      );
      const response = await apiFetch<JobStatus>(`/data/imports/${job.job_id}/mapping`, {
        method: "PUT",
        body: JSON.stringify({ mapping: normalizedMapping }),
      });
      setJob(response);
      if (response.data_type && job.data_type && response.data_type !== job.data_type) {
        message.info(`系统已根据字段自动识别为：${dataTypeLabels[response.data_type] ?? response.data_type}`);
      }
      if (response.invalid_rows > 0) {
        const issueData = await apiFetch<{ items: Issue[] }>(
          `/data/imports/${job.job_id}/issues`,
        );
        setIssues(issueData.items);
        message.warning(`校验完成，有 ${response.invalid_rows} 行存在问题`);
      } else {
        setIssues([]);
        message.success("字段映射和质量校验完成");
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "映射校验失败");
    }
  }

  async function handleCommit(): Promise<void> {
    if (!job) {
      return;
    }
    try {
      const response = await apiFetch<JobStatus>(`/data/imports/${job.job_id}/commit`, {
        method: "POST",
      });
      setJob(response);
      message.success("已提交导入任务");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "提交导入失败");
    }
  }

  const previewColumns = (preview?.headers ?? []).map((header) => ({
    title: header,
    dataIndex: header,
    key: header,
    ellipsis: true,
  }));

  const mappingRows = preview?.headers.map((header) => ({
    source_field: header,
    target_field: mapping[header] ?? "",
  })) ?? [];
  const normalizedTargets = new Set(
    Object.values(mapping)
      .map((value) => normalizeTargetField(value))
      .filter((value): value is string => Boolean(value)),
  );
  const missingRequiredFields = (requiredFieldsByType[selectedDataType] ?? []).filter(
    (field) => !normalizedTargets.has(field),
  );

  return (
    <div className="data-import-page">
      <PageHero
        title="数据导入"
        description="从上传、字段映射到质量校验，确保进入决策链路的每一条数据都可追溯。"
      />

      <Steps
        current={currentStep}
        items={[
          { title: "上传文件" },
          { title: "确认映射" },
          { title: "质量校验" },
          { title: "正式导入" },
        ]}
        style={{ marginBottom: 24 }}
      />

      <Form<ImportForm>
        form={form}
        layout="vertical"
        initialValues={{ source_type: "file_upload", data_type: "admission" }}
        onFinish={handleUpload}
        style={{ maxWidth: 760 }}
      >
        <Form.Item label="数据来源" name="source_type" rules={[{ required: true }]}>
          <Select
            options={[
              { value: "file_upload", label: "文件上传" },
              { value: "legacy_system", label: "原招录系统" },
            ]}
          />
        </Form.Item>
        <Form.Item label="数据类型" name="data_type" rules={[{ required: true }]}>
          <Select options={dataTypeOptions} />
        </Form.Item>
        <Alert
          type="info"
          showIcon
          message={`${dataTypeLabels[selectedDataType] ?? "数据"}导入标准模板`}
          description="请下载标准模板后，按示例列填写并保留表头；上传时系统会识别已有字段，缺少的字段不会阻断导入，但会进入质量校验提示。"
          action={
            <Button icon={<DownloadOutlined />} onClick={() => void handleDownloadTemplate()}>
              下载标准模板
            </Button>
          }
          style={{ marginBottom: 18 }}
        />
        <Space style={{ display: "flex" }} align="start">
          <Form.Item label="招生年度" name="year">
            <Input type="number" placeholder="例如 2025" />
          </Form.Item>
          <Form.Item label="数据版本" name="data_version">
            <Input placeholder="例如 2025_v1" />
          </Form.Item>
        </Space>
        <Form.Item
          label="数据文件"
          name="file"
          valuePropName="fileList"
          getValueFromEvent={(event) => event?.fileList}
          rules={[{ required: true, message: "请选择文件" }]}
        >
          <Upload.Dragger beforeUpload={() => false} maxCount={1} accept=".xlsx,.xls,.csv">
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到这里</p>
            <p className="ant-upload-hint">支持 xlsx、xls、csv，单文件不超过 50MB</p>
          </Upload.Dragger>
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting}>
          上传并解析
        </Button>
      </Form>

      {job ? (
        <section style={{ marginTop: 32 }}>
          <Alert
            type={job.status === "VALIDATION_FAILED" || job.status === "IMPORT_FAILED" ? "error" : "info"}
            showIcon
            message={`任务状态：${job.status}`}
            description={
              job.error_message ??
              `总行数：${job.total_rows}，有效：${job.valid_rows}，问题：${job.invalid_rows}`
            }
          />
        </section>
      ) : null}

      {preview ? (
        <>
          <section style={{ marginTop: 28 }}>
            <h2>字段映射</h2>
            {missingRequiredFields.length > 0 ? (
              <Alert
                type="warning"
                showIcon
                message={`部分标准字段未映射：${missingRequiredFields
                  .map((field) => requiredFieldLabels[field] ?? field)
                  .join("、")}`}
                description="系统仍会识别并导入文件中已有的字段；缺少关键字段的记录会在质量校验时跳过并显示具体原因。"
                style={{ marginBottom: 16 }}
              />
            ) : null}
            <Table
              rowKey="source_field"
              pagination={false}
              dataSource={mappingRows}
              columns={[
                { title: "原始字段", dataIndex: "source_field", width: 240 },
                {
                  title: "标准字段",
                  dataIndex: "target_field",
                  render: (value: string, row: { source_field: string }) => (
                    <Select
                      value={value}
                      style={{ minWidth: 220 }}
                      options={targetOptions}
                      onChange={(nextValue) =>
                        setMapping((current) => ({ ...current, [row.source_field]: nextValue || null }))
                      }
                    />
                  ),
                },
              ]}
            />
            <Space style={{ marginTop: 16 }}>
              <Button type="primary" onClick={handleConfirmMapping}>
                确认映射并校验
              </Button>
              <Button
                disabled={
                  !job ||
                  job.valid_rows <= 0 ||
                  ["QUEUED_FOR_IMPORT", "IMPORTING", "IMPORTED"].includes(job.status)
                }
                onClick={handleCommit}
              >
                {job?.status === "IMPORT_FAILED" ? "重试导入" : "正式导入"}
              </Button>
            </Space>
          </section>

          <section style={{ marginTop: 28 }}>
            <h2>数据预览</h2>
            <Table
              rowKey={(_, index) => String(index)}
              dataSource={preview.preview.slice(0, 10)}
              columns={previewColumns}
              scroll={{ x: "max-content" }}
              pagination={false}
            />
          </section>
        </>
      ) : null}

      {issues.length > 0 ? (
        <section style={{ marginTop: 28 }}>
          <h2>质量问题</h2>
          <Table
            rowKey="row_no"
            dataSource={issues}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: "行号", dataIndex: "row_no", width: 100 },
              { title: "问题", dataIndex: "error_message" },
            ]}
          />
        </section>
      ) : null}

      {job?.status === "IMPORTED" ? (
        <Tag color="green" style={{ marginTop: 20 }}>
          已正式导入
        </Tag>
      ) : null}
    </div>
  );
}

