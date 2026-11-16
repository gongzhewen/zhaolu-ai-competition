import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
} from "antd";
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api/client";

type NamedOption = { id: number; name: string };
type PlanOptions = {
  years: Array<{ id: number; year_no: number }>;
  provinces: Array<{ id: number; province_code: string; province_name: string }>;
  batches: Array<{ id: number; batch_code: string; batch_name: string; year_no: number | null }>;
  subjects: Array<{ id: number; subject_code: string; subject_name: string }>;
  majors: Array<{ id: number; major_code: string; major_name: string }>;
  plan_types: Array<{ id: number; type_code: string; type_name: string }>;
};

type PlanItem = {
  id: number;
  year_no: number;
  school_name: string;
  province_id: number;
  province_name: string;
  batch_id: number;
  batch_name: string;
  subject_id: number;
  subject_name: string;
  major_id: number;
  major_name: string;
  plan_type_id: number | null;
  plan_type_name: string | null;
  plan_count: number;
  tuition: number | string | null;
  data_version: string;
  created_at: string;
  is_editable: boolean;
};

type PlanListResponse = {
  items: PlanItem[];
  total: number;
  page: number;
  page_size: number;
  summary: {
    total_plan_count: number;
    province_count: number;
    major_count: number;
    manual_count: number;
  };
};

type PlanFormValues = {
  year_no: number;
  province_id: number;
  batch_id: number;
  subject_id: number;
  major_id: number;
  plan_type_id?: number;
  plan_count: number;
  tuition?: number;
};

export default function PlanManagementPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<PlanFormValues>();
  const [copyForm] = Form.useForm<{ source_year: number; target_year: number }>();
  const [yearForm] = Form.useForm<{ year_no: number }>();
  const [year, setYear] = useState<number>();
  const [provinceId, setProvinceId] = useState<number>();
  const [batchId, setBatchId] = useState<number>();
  const [subjectId, setSubjectId] = useState<number>();
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [editing, setEditing] = useState<PlanItem | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [yearOpen, setYearOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const selectedYear = Form.useWatch("year_no", form);

  const { data: options, isLoading: optionsLoading } = useQuery({
    queryKey: ["plan-options"],
    queryFn: () => apiFetch<PlanOptions>("/plans/options"),
  });

  useEffect(() => {
    if (year === undefined && options?.years.length) {
      setYear(options.years[0].year_no);
    }
  }, [options, year]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (year) params.set("year", String(year));
    if (provinceId) params.set("province_id", String(provinceId));
    if (batchId) params.set("batch_id", String(batchId));
    if (subjectId) params.set("subject_id", String(subjectId));
    if (keyword) params.set("keyword", keyword);
    return params.toString();
  }, [batchId, keyword, page, pageSize, provinceId, subjectId, year]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["plans", queryString],
    queryFn: () => apiFetch<PlanListResponse>(`/plans?${queryString}`),
    enabled: Boolean(year),
  });

  const batchOptions = (options?.batches ?? []).filter(
    (item) => item.year_no === null || item.year_no === (selectedYear ?? year),
  );

  function resetFilters(): void {
    setProvinceId(undefined);
    setBatchId(undefined);
    setSubjectId(undefined);
    setKeyword("");
    setPage(1);
  }

  function openCreate(): void {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      year_no: year ?? options?.years[0]?.year_no,
      plan_count: 0,
    });
    setEditorOpen(true);
  }

  function openEdit(plan: PlanItem): void {
    setEditing(plan);
    form.setFieldsValue({
      year_no: plan.year_no,
      province_id: plan.province_id,
      batch_id: plan.batch_id,
      subject_id: plan.subject_id,
      major_id: plan.major_id,
      plan_type_id: plan.plan_type_id ?? undefined,
      plan_count: plan.plan_count,
      tuition: plan.tuition ? Number(plan.tuition) : undefined,
    });
    setEditorOpen(true);
  }

  async function submitPlan(): Promise<void> {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await apiFetch(`/plans/${editing.id}`, { method: "PUT", body: JSON.stringify(values) });
        message.success("招生计划已更新");
      } else {
        await apiFetch("/plans", { method: "POST", body: JSON.stringify(values) });
        message.success("招生计划已新增");
      }
      setEditorOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["plans"] });
    } catch (submitError) {
      message.error(submitError instanceof Error ? submitError.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(plan: PlanItem): void {
    modal.confirm({
      title: "删除手工招生计划",
      content: `${plan.year_no} 年 ${plan.province_name} · ${plan.major_name} · ${plan.plan_count} 人`,
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        await apiFetch(`/plans/${plan.id}`, { method: "DELETE" });
        message.success("招生计划已删除");
        await queryClient.invalidateQueries({ queryKey: ["plans"] });
      },
    });
  }

  async function submitYear(): Promise<void> {
    const values = await yearForm.validateFields();
    setSaving(true);
    try {
      await apiFetch("/plans/years", { method: "POST", body: JSON.stringify(values) });
      message.success(`${values.year_no} 年已创建`);
      setYearOpen(false);
      setYear(values.year_no);
      await queryClient.invalidateQueries({ queryKey: ["plan-options"] });
    } catch (yearError) {
      message.error(yearError instanceof Error ? yearError.message : "年度创建失败");
    } finally {
      setSaving(false);
    }
  }

  async function submitCopy(): Promise<void> {
    const values = await copyForm.validateFields();
    setSaving(true);
    try {
      const result = await apiFetch<{ created_count: number; skipped_count: number }>(
        "/plans/copy-from-year",
        { method: "POST", body: JSON.stringify(values) },
      );
      message.success(`已复制 ${result.created_count} 条，跳过 ${result.skipped_count} 条`);
      setCopyOpen(false);
      setYear(values.target_year);
      await queryClient.invalidateQueries({ queryKey: ["plans"] });
    } catch (copyError) {
      message.error(copyError instanceof Error ? copyError.message : "复制失败");
    } finally {
      setSaving(false);
    }
  }

  if (optionsLoading || year === undefined) return <SpinPage />;
  if (error) return <Alert type="error" message="招生计划加载失败" description={error.message} />;

  const latestYear = options?.years[0]?.year_no ?? year;
  const summary = data?.summary;

  return (
    <div className="plan-page">
      <section className="plan-hero">
        <div>
          <h1>招生计划填报与维护</h1>
          <p>按年度、省份、批次、科类和专业维护招生计划，手工填报数据与导入数据自动区分。</p>
        </div>
        <Space wrap>
          <Button
            icon={<PlusOutlined />}
            onClick={() => {
              yearForm.setFieldsValue({ year_no: (latestYear ?? new Date().getFullYear()) + 1 });
              setYearOpen(true);
            }}
          >
            新增年度
          </Button>
          <Button
            icon={<CopyOutlined />}
            onClick={() => {
              copyForm.setFieldsValue({
                source_year: latestYear,
                target_year: latestYear + 1,
              });
              setCopyOpen(true);
            }}
          >
            从上年复制
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增招生计划
          </Button>
        </Space>
      </section>

      <section className="metric-grid plan-metric-grid">
        <article className="metric-card">
          <div className="metric-label">计划总人数</div>
          <div className="metric-value">{summary?.total_plan_count.toLocaleString() ?? 0}</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">计划记录</div>
          <div className="metric-value">{data?.total.toLocaleString() ?? 0}</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">覆盖省份</div>
          <div className="metric-value">{summary?.province_count ?? 0}</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">覆盖专业</div>
          <div className="metric-value">{summary?.major_count ?? 0}</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">手工计划</div>
          <div className="metric-value">{summary?.manual_count ?? 0}</div>
        </article>
      </section>

      <Card className="plan-filter-card" bordered={false}>
        <div className="plan-filter-grid">
          <Select
            value={year}
            onChange={(value) => { setYear(value); setPage(1); setBatchId(undefined); }}
            options={options?.years.map((item) => ({ value: item.year_no, label: `${item.year_no} 年` }))}
            placeholder="招生年度"
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            value={provinceId}
            onChange={(value) => { setProvinceId(value); setPage(1); }}
            placeholder="省份"
            options={options?.provinces.map((item) => ({ value: item.id, label: item.province_name }))}
          />
          <Select
            allowClear
            value={subjectId}
            onChange={(value) => { setSubjectId(value); setPage(1); }}
            placeholder="科类"
            options={options?.subjects.map((item) => ({ value: item.id, label: item.subject_name }))}
          />
          <Select
            allowClear
            value={batchId}
            onChange={(value) => { setBatchId(value); setPage(1); }}
            placeholder="批次"
            options={batchOptions.map((item) => ({ value: item.id, label: item.batch_name }))}
          />
          <Input.Search
            allowClear
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={(value) => { setKeyword(value); setPage(1); }}
            placeholder="专业名称或代码"
          />
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void queryClient.invalidateQueries({ queryKey: ["plans"] })}>
              刷新
            </Button>
            <Button type="text" onClick={resetFilters}>重置</Button>
          </Space>
        </div>
      </Card>

      <Card className="plan-table-card" bordered={false}>
        <div className="plan-table-heading">
          <div>
            <h2>{year} 年招生计划明细</h2>
          </div>
          <Tag color="blue">共 {data?.total ?? 0} 条</Tag>
        </div>
        <Table
          rowKey="id"
          loading={isLoading}
          dataSource={data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total.toLocaleString()} 条计划`,
            onChange: (nextPage, nextPageSize) => { setPage(nextPage); setPageSize(nextPageSize); },
          }}
          scroll={{ x: 1480 }}
          columns={[
            { title: "年度", dataIndex: "year_no", width: 86, render: (value: number) => <Tag color="blue">{value}</Tag> },
            { title: "省份", dataIndex: "province_name", width: 140 },
            { title: "批次", dataIndex: "batch_name", width: 150 },
            { title: "科类", dataIndex: "subject_name", width: 100 },
            {
              title: "专业",
              dataIndex: "major_name",
              width: 220,
              render: (value: string) => <span className="student-major">{value}</span>,
            },
            {
              title: "计划类型",
              dataIndex: "plan_type_name",
              width: 120,
              render: (value: string | null) => value ? <Tag>{value}</Tag> : "-",
            },
            {
              title: "计划人数",
              dataIndex: "plan_count",
              width: 110,
              align: "right",
              render: (value: number) => <span className="plan-count-value">{value.toLocaleString()}</span>,
            },
            {
              title: "学费",
              dataIndex: "tuition",
              width: 110,
              align: "right",
              render: (value: number | string | null) => {
                if (value === null) return "-";
                const numericValue = Number(value);
                return Number.isFinite(numericValue)
                  ? `¥ ${numericValue.toLocaleString()}`
                  : `¥ ${value}`;
              },
            },
            {
              title: "数据来源",
              dataIndex: "data_version",
              width: 150,
              render: (value: string, record: PlanItem) => (
                <Tag color={record.is_editable ? "green" : "default"}>
                  {record.is_editable ? "手工填报" : value}
                </Tag>
              ),
            },
            {
              title: "操作",
              width: 150,
              fixed: "right",
              render: (_, record: PlanItem) => record.is_editable ? (
                <Space>
                  <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
                  <Button type="link" danger icon={<DeleteOutlined />} onClick={() => confirmDelete(record)}>删除</Button>
                </Space>
              ) : (
                <Tag color="default">导入只读</Tag>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editing ? "编辑招生计划" : "新增招生计划"}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={() => void submitPlan()}
        confirmLoading={saving}
        width={820}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" className="plan-editor-form">
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="招生年度" name="year_no" rules={[{ required: true, message: "请选择招生年度" }]}>
                <Select options={options?.years.map((item) => ({ value: item.year_no, label: `${item.year_no} 年` }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="省份" name="province_id" rules={[{ required: true, message: "请选择省份" }]}>
                <Select showSearch optionFilterProp="label" options={options?.provinces.map((item) => ({ value: item.id, label: item.province_name }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="批次" name="batch_id" rules={[{ required: true, message: "请选择批次" }]}>
                <Select options={batchOptions.map((item) => ({ value: item.id, label: item.batch_name }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="科类" name="subject_id" rules={[{ required: true, message: "请选择科类" }]}>
                <Select options={options?.subjects.map((item) => ({ value: item.id, label: item.subject_name }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="专业" name="major_id" rules={[{ required: true, message: "请选择专业" }]}>
                <Select showSearch optionFilterProp="label" options={options?.majors.map((item) => ({ value: item.id, label: `${item.major_name}（${item.major_code}）` }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="计划类型" name="plan_type_id">
                <Select allowClear options={options?.plan_types.map((item) => ({ value: item.id, label: item.type_name }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="计划人数" name="plan_count" rules={[{ required: true, message: "请输入计划人数" }]}>
                <InputNumber min={0} max={100000} style={{ width: "100%" }} addonAfter="人" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="学费" name="tuition">
                <InputNumber min={0} max={1000000} precision={2} style={{ width: "100%" }} addonBefore="¥" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="新增招生年度"
        open={yearOpen}
        onCancel={() => setYearOpen(false)}
        onOk={() => void submitYear()}
        confirmLoading={saving}
        okText="创建年度"
      >
        <Form form={yearForm} layout="vertical">
          <Form.Item label="年度" name="year_no" rules={[{ required: true, message: "请输入年度" }]}>
            <InputNumber min={2000} max={2100} style={{ width: "100%" }} addonAfter="年" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="从往年复制招生计划"
        open={copyOpen}
        onCancel={() => setCopyOpen(false)}
        onOk={() => void submitCopy()}
        confirmLoading={saving}
        okText="开始复制"
      >
        <Alert
          type="info"
          showIcon
          message="快速填报"
          description="系统会复制来源年度的计划规模，已有相同手工计划的记录将自动跳过。"
          style={{ marginBottom: 18 }}
        />
        <Form form={copyForm} layout="vertical">
          <Form.Item label="来源年度" name="source_year" rules={[{ required: true }]}>
            <Select options={options?.years.map((item) => ({ value: item.year_no, label: `${item.year_no} 年` }))} />
          </Form.Item>
          <Form.Item label="目标年度" name="target_year" rules={[{ required: true }]}>
            <Select options={options?.years.map((item) => ({ value: item.year_no, label: `${item.year_no} 年` }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function SpinPage() {
  return (
    <div className="plan-loading">
      <Statistic title="正在加载招生计划" value="..." />
    </div>
  );
}




