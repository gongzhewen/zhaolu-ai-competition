import {
  Alert,
  App,
  Avatar,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from "antd";
import {
  ArrowRightOutlined,
  DatabaseOutlined,
  EnvironmentOutlined,
  FilterOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch } from "@/lib/api/client";
type StudentItem = {
  candidate_key: string;
  candidate_no: string;
  year_no: number;
  is_synthetic: boolean;
  student_name: string;
  gender: string;
  subject: string;
  exam_type: string;
  source_school: string;
  region_code: string | null;
  region_name: string | null;
  exam_score: number | string | null;
  filing_score: number | string | null;
  major_name: string | null;
  batch_name: string | null;
  student_status: string;
  follow_up_status: string;
  owner_name: string | null;
  tags: string[];
  updated_at: string | null;
};

type StudentListResponse = {
  items: StudentItem[];
  total: number;
  page: number;
  page_size: number;
  year_no: number | null;
};

type StudentYear = {
  year_no: number;
  total: number;
  is_synthetic: boolean;
};

type StudentSummary = {
  year_no: number | null;
  metrics: {
    total: number;
    new: number;
    contacted: number;
    admitted: number;
    enrolled: number;
    pending: number;
    in_progress: number;
    synthetic: number;
  };
  regions: Array<{ region_code: string; region_name: string; count: number }>;
};

type StudentDetail = {
  candidate_key: string;
  basic: Record<string, string | null>;
  profile: Record<string, string | number | null> | null;
  admission: Record<string, string | number | null> | null;
  management: {
    student_status: string;
    follow_up_status: string;
    owner_name: string | null;
    tags: string[];
    notes: string | null;
    updated_at: string | null;
  };
  subject_scores: Array<Record<string, string | number | null>>;
  major_choices: Array<Record<string, string | number | null>>;
  resumes: Array<Record<string, string | number | null>>;
  medical_summary: Record<string, string | string[] | null> | null;
};

const studentStatusOptions = [
  { value: "NEW", label: "新学生" },
  { value: "CONTACTED", label: "已联系" },
  { value: "INTERESTED", label: "有意向" },
  { value: "APPLIED", label: "已报考" },
  { value: "ADMITTED", label: "已录取" },
  { value: "ENROLLED", label: "已报到" },
  { value: "ABANDONED", label: "已放弃" },
];

const followUpOptions = [
  { value: "PENDING", label: "待跟进" },
  { value: "IN_PROGRESS", label: "跟进中" },
  { value: "DONE", label: "已完成" },
  { value: "DEFERRED", label: "暂缓" },
];

const statusColor: Record<string, string> = {
  NEW: "blue",
  CONTACTED: "cyan",
  INTERESTED: "processing",
  APPLIED: "purple",
  ADMITTED: "gold",
  ENROLLED: "green",
  ABANDONED: "red",
};

const followColor: Record<string, string> = {
  PENDING: "default",
  IN_PROGRESS: "processing",
  DONE: "green",
  DEFERRED: "orange",
};

function formatScore(value: number | string | null): string {
  if (value === null || value === undefined || value === "") return "-";
  const score = Number(value);
  return Number.isFinite(score) ? score.toFixed(1) : String(value);
}

function maskId(value: string | null | undefined): string {
  if (!value) return "";
  return `${value.slice(0, 6)}********${value.slice(-4)}`;
}

function maskPhone(value: string | null | undefined): string {
  if (!value) return "";
  return `${value.slice(0, 3)}****${value.slice(-4)}`;
}

export default function StudentsPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [year, setYear] = useState<number | undefined>();
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<string | undefined>();
  const [regionCode, setRegionCode] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [showSensitive, setShowSensitive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [managementForm] = Form.useForm();

  const { data: years, isLoading: yearsLoading, error: yearsError } = useQuery({
    queryKey: ["student-years"],
    queryFn: () => apiFetch<{ items: StudentYear[] }>("/students/years"),
  });

  useEffect(() => {
    if (year === undefined && years?.items?.length) {
      setYear(years.items[0].year_no);
    }
  }, [year, years]);

  const queryString = new URLSearchParams({
    year: String(year ?? ""),
    page: String(page),
    page_size: String(pageSize),
  });
  if (keyword) queryString.set("keyword", keyword);
  if (status) queryString.set("status", status);
  if (regionCode) queryString.set("region_code", regionCode);

  const { data, isLoading, error } = useQuery({
    queryKey: ["students", year, page, pageSize, keyword, status, regionCode],
    queryFn: () => apiFetch<StudentListResponse>(`/students?${queryString.toString()}`),
    enabled: Boolean(year),
  });

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["student-summary", year],
    queryFn: () => apiFetch<StudentSummary>(`/students/summary?year=${year}`),
    enabled: Boolean(year),
  });
  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["student-detail", selectedKey],
    queryFn: () => apiFetch<StudentDetail>(`/students/${selectedKey}`),
    enabled: Boolean(selectedKey),
  });

  const currentYear = years?.items.find((item) => item.year_no === year);
  const trendItems = useMemo(
    () => [...(years?.items ?? [])].sort((a, b) => a.year_no - b.year_no),
    [years],
  );
  const trendOption = useMemo(
    () => ({
      grid: { left: 20, right: 18, top: 28, bottom: 12, containLabel: true },
      tooltip: {
        trigger: "axis" as const,
        formatter: (params: Array<{ name: string; value: number }>) =>
          `${params[0].name} 年<br/>学生规模：<b>${params[0].value}</b> 人`,
      },
      xAxis: {
        type: "category" as const,
        data: trendItems.map((item) => String(item.year_no)),
        axisLine: { lineStyle: { color: "#d9e2ef" } },
        axisTick: { show: false },
        axisLabel: { color: "#64748b" },
      },
      yAxis: {
        type: "value" as const,
        splitLine: { lineStyle: { color: "#edf2f7", type: "dashed" as const } },
        axisLabel: { color: "#94a3b8" },
      },
      series: [
        {
          type: "bar" as const,
          barWidth: 34,
          data: trendItems.map((item) => ({
            value: item.total,
            itemStyle: {
              color: item.is_synthetic ? "#f59e0b" : "#155eef",
              borderRadius: [8, 8, 2, 2],
            },
          })),
          label: { show: true, position: "top" as const, color: "#334155", fontWeight: 700 },
        },
      ],
    }),
    [trendItems],
  );

  async function openDetail(candidateKey: string): Promise<void> {
    setSelectedKey(candidateKey);
    setShowSensitive(false);
    const student = data?.items.find((item) => item.candidate_key === candidateKey);
    managementForm.setFieldsValue({
      student_status: student?.student_status ?? "NEW",
      follow_up_status: student?.follow_up_status ?? "PENDING",
      owner_name: student?.owner_name ?? "",
      tags: student?.tags ?? [],
      notes: "",
    });
  }

  async function saveManagement(): Promise<void> {
    if (!selectedKey) return;
    const values = await managementForm.validateFields();
    setSaving(true);
    try {
      await apiFetch(`/students/${selectedKey}`, {
        method: "PATCH",
        body: JSON.stringify(values),
      });
      message.success("学生跟进信息已保存");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["students"] }),
        queryClient.invalidateQueries({ queryKey: ["student-detail", selectedKey] }),
      ]);
    } catch (saveError) {
      message.error(saveError instanceof Error ? saveError.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  function confirmSensitiveToggle(checked: boolean): void {
    if (!checked) {
      setShowSensitive(false);
      return;
    }
    modal.confirm({
      title: "显示敏感个人信息",
      content: "身份证号、手机号和详细地址仅用于管理员学生管理，查看行为会写入审计日志。",
      okText: "显示",
      cancelText: "取消",
      onOk: () => setShowSensitive(true),
    });
  }

  if (yearsLoading || (year === undefined && !yearsError)) return <Spin />;
  if (yearsError) {
    return (
      <Alert
        type="error"
        showIcon
        message="学生年度目录加载失败"
        description={yearsError.message}
        action={<Button onClick={() => void queryClient.invalidateQueries({ queryKey: ["student-years"] })}>重试</Button>}
      />
    );
  }
  if (!years?.items?.length) {
    return <Alert type="warning" showIcon message="暂无可管理的学生年度数据" />;
  }
  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="学生信息加载失败"
        description={error.message}
        action={<Button onClick={() => void queryClient.invalidateQueries({ queryKey: ["students"] })}>重试</Button>}
      />
    );
  }
  if (isLoading) return <Spin />;

  function handleYearChange(nextYear: number): void {
    setYear(nextYear);
    setKeywordInput("");
    setKeyword("");
    setStatus(undefined);
    setRegionCode(undefined);
    setPage(1);
  }

  function resetFilters(): void {
    setKeywordInput("");
    setKeyword("");
    setStatus(undefined);
    setRegionCode(undefined);
    setPage(1);
  }

  const progressTotal = summary?.metrics.total;
  const progressEnrolled = summary?.metrics.enrolled;
  const progressPercent =
    typeof progressTotal === "number" &&
    typeof progressEnrolled === "number" &&
    progressTotal > 0
      ? Math.round((progressEnrolled / progressTotal) * 100)
      : 0;

  const kpis = [
    { label: "学生总数", value: summary?.metrics.total ?? 0 },
    { label: "新学生", value: summary?.metrics.new ?? 0 },
    { label: "已联系", value: summary?.metrics.contacted ?? 0 },
    { label: "已录取", value: summary?.metrics.admitted ?? 0 },
    { label: "已报到", value: summary?.metrics.enrolled ?? 0 },
    { label: "待跟进", value: summary?.metrics.pending ?? 0 },
  ];

  return (
    <div className="student-page">
      <PageHero
        title="学生信息管理"
        description="按年度查询学生档案、录取信息和跟进状态。敏感信息的查看和修改会记录审计。"
        actions={
          <Space wrap size={8}>
            <Segmented
              size="small"
              value={year}
              onChange={(value) => handleYearChange(Number(value))}
              options={years.items.map((item) => ({
                value: item.year_no,
                label: String(item.year_no),
              }))}
            />
            {currentYear?.is_synthetic ? <Tag color="gold">模拟数据</Tag> : null}
          </Space>
        }
      />

      {currentYear?.is_synthetic ? (
        <Alert
          className="student-data-alert"
          type="warning"
          showIcon
          message={`${year} 年为模拟学生数据`}
          description="该年度仅用于训练、分年度管理和系统功能验证，不代表真实学生名册。模拟考生身份已匿名处理。"
        />
      ) : null}

      <section className="student-kpi-grid">
        {kpis.map((item) => (
          <article className="student-kpi-card" key={item.label}>
            <div className="student-kpi-copy">
              <span>{item.label}</span>
              <strong>{summaryLoading ? "-" : item.value.toLocaleString()}</strong>
            </div>
          </article>
        ))}
      </section>

      <section className="student-insight-grid">
        <Card className="student-progress-card" bordered={false}>
          <div className="student-panel-heading">
            <h2>年度管理进度</h2>
          </div>
          <div className="student-progress-layout">
            <Progress
              percent={progressPercent}
              strokeColor="#245bdb"
              trailColor="#e9eff7"
              showInfo={false}
            />
            <div className="student-progress-facts">
              <div><span>已报到</span><strong>{(summary?.metrics.enrolled ?? 0).toLocaleString()}</strong></div>
              <div><span>跟进中</span><strong>{(summary?.metrics.in_progress ?? 0).toLocaleString()}</strong></div>
              <div><span>待处理</span><strong>{(summary?.metrics.pending ?? 0).toLocaleString()}</strong></div>
              <div><span>数据性质</span><strong>{currentYear?.is_synthetic ? "模拟" : "真实"}</strong></div>
            </div>
          </div>
        </Card>

        <Card className="student-trend-card" bordered={false}>
          <div className="student-panel-heading">
            <h2>年度招生规模</h2>
          </div>
          {trendItems.length ? (
            <LazyEChartsContainer option={trendOption} height={230} />
          ) : (
            <Empty description="暂无年度规模数据" />
          )}
        </Card>
      </section>
      <Card className="student-filter-card" bordered={false}>
        <div className="student-panel-heading student-filter-heading">
          <h2>学生名册筛选</h2>
          <Space>
            <Badge count={data?.total ?? 0} overflowCount={99999} color="#155eef" showZero />
            <span className="student-result-label">条结果</span>
          </Space>
        </div>
        <div className="student-filter-grid">
          <Input.Search
            allowClear
            prefix={<SearchOutlined />}
            placeholder="姓名、考生号、学校、地区或专业"
            value={keywordInput}
            onChange={(event) => {
              const nextValue = event.target.value;
              setKeywordInput(nextValue);
              if (nextValue === "") {
                setKeyword("");
                setPage(1);
              }
            }}
            onSearch={(value) => {
              const nextKeyword = value.trim();
              setKeywordInput(nextKeyword);
              setKeyword(nextKeyword);
              setPage(1);
            }}
          />
          <Select
            allowClear
            suffixIcon={<FilterOutlined />}
            placeholder="学生状态"
            value={status}
            onChange={(value) => { setStatus(value); setPage(1); }}
            options={studentStatusOptions}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="生源地区"
            value={regionCode}
            onChange={(value) => { setRegionCode(value); setPage(1); }}
            options={(summary?.regions ?? []).map((region) => ({
              value: region.region_code,
              label: `${region.region_name}（${region.count}人）`,
            }))}
          />
          <Space className="student-filter-actions">
            <Button icon={<ReloadOutlined />} onClick={() => void queryClient.invalidateQueries({ queryKey: ["students"] })}>
              刷新
            </Button>
            <Button type="text" onClick={resetFilters}>重置筛选</Button>
          </Space>
        </div>
      </Card>

      <Card className="student-table-card" bordered={false}>
        <div className="student-table-header">
          <h2>{year} 年学生名册</h2>
          <Space wrap>
            <Tag>{data?.total ?? 0} 人</Tag>
          </Space>
          </div>
        <Table
          rowKey="candidate_key"
          loading={isLoading}
          dataSource={data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total.toLocaleString()} 名学生`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
          }}
          size="middle"
          sticky
          scroll={{ x: 1540 }}
          columns={[
            {
              title: "学生",
              dataIndex: "student_name",
              fixed: "left",
              width: 210,
              render: (value: string, record: StudentItem) => (
                <div className="student-name-cell">
                  <Avatar className="student-table-avatar">{value?.slice(-1)}</Avatar>
                  <div>
                    <strong>{value}</strong>
                    <span>{record.candidate_no}</span>
                  </div>
                </div>
              ),
            },
            {
              title: "年度",
              dataIndex: "year_no",
              width: 96,
              render: (value: number, record: StudentItem) => (
                <Tag color={record.is_synthetic ? "gold" : "blue"}>{value}</Tag>
              ),
            },
            { title: "性别", dataIndex: "gender", width: 72 },
            {
              title: "科类",
              dataIndex: "subject",
              width: 110,
              render: (value: string) => <Tag bordered={false}>{value}</Tag>,
            },
            {
              title: "毕业学校",
              dataIndex: "source_school",
              width: 220,
              render: (value: string) => (
                <Tooltip title={value}>
                  <span className="student-ellipsis">{value || "-"}</span>
                </Tooltip>
              ),
            },
            {
              title: "地区",
              dataIndex: "region_name",
              width: 160,
              render: (value: string) => (
                <Space size={6}>
                  <EnvironmentOutlined className="student-muted-icon" />
                  <span>{value || "-"}</span>
                </Space>
              ),
            },
            {
              title: "高考成绩",
              dataIndex: "exam_score",
              width: 108,
              align: "right",
              render: (value: number | string | null) => (
                <span className="student-score">{formatScore(value)}</span>
              ),
            },
            {
              title: "投档成绩",
              dataIndex: "filing_score",
              width: 108,
              align: "right",
              render: (value: number | string | null) => (
                <span className="student-score">{formatScore(value)}</span>
              ),
            },
            {
              title: "录取专业",
              dataIndex: "major_name",
              width: 220,
              render: (value: string | null) => (
                <Tooltip title={value}>
                  <span className="student-major">{value || "-"}</span>
                </Tooltip>
              ),
            },
            {
              title: "学生状态",
              dataIndex: "student_status",
              width: 112,
              render: (value: string) => (
                <Tag color={statusColor[value] ?? "default"}>
                  {studentStatusOptions.find((item) => item.value === value)?.label ?? value}
                </Tag>
              ),
            },
            {
              title: "跟进状态",
              dataIndex: "follow_up_status",
              width: 112,
              render: (value: string) => (
                <Tag color={followColor[value] ?? "default"}>
                  {followUpOptions.find((item) => item.value === value)?.label ?? value}
                </Tag>
              ),
            },
            {
              title: "",
              fixed: "right",
              width: 120,
              render: (_, student) => (
                <Button
                  type="link"
                  className="student-detail-button"
                  onClick={() => void openDetail(student.candidate_key)}
                >
                  查看档案 <ArrowRightOutlined />
                </Button>
              ),
            },
          ]}
        />      </Card>

      <Drawer
        className="student-drawer"
        title={
          detail?.basic.student_name ? (
            <div className="student-drawer-title">
              <Avatar size={42} className="student-drawer-avatar">
                {String(detail.basic.student_name).slice(-1)}
              </Avatar>
              <div>
                <strong>{detail.basic.student_name}</strong>
                <span>{detail.basic.year_no} 年 · 学生管理档案</span>
              </div>
            </div>
          ) : (
            "学生详情"
          )
        }
        width={1100}
        open={Boolean(selectedKey)}
        onClose={() => setSelectedKey(null)}
        destroyOnHidden
      >
        {detailLoading || !detail ? (
          <Spin />
        ) : (
          <>
            <section className="student-detail-hero">
              <div className="student-detail-identity">
                <Avatar size={64} className="student-detail-avatar">
                  {String(detail.basic.student_name ?? "").slice(-1)}
                </Avatar>
                <div>
                  <Space wrap>
                    <h2>{detail.basic.student_name}</h2>
                    <Tag color={detail.basic.is_synthetic ? "gold" : "blue"}>
                      {detail.basic.is_synthetic ? "模拟学生" : "真实学生"}
                    </Tag>
                  </Space>
                  <p>{detail.basic.ksh}</p>
                  <Space wrap>
                    <Tag bordered={false}>{detail.profile?.subject_category_code ?? "科类未定"}</Tag>
                    <Tag bordered={false}>{detail.profile?.exam_type_name ?? "考试类型未定"}</Tag>
                    <Tag bordered={false}>{detail.profile?.region_name ?? "地区未定"}</Tag>
                  </Space>
                </div>
              </div>
              <div className="student-detail-stats">
                <Statistic title="考生成绩" value={Number(detail.admission?.exam_score ?? 0)} precision={1} />
                <Divider type="vertical" />
                <Statistic title="投档成绩" value={Number(detail.admission?.filing_score ?? 0)} precision={1} />
                <Divider type="vertical" />
                <Statistic title="志愿数量" value={detail.major_choices.length} suffix="项" />
                <Divider type="vertical" />
                <Statistic title="成绩记录" value={detail.subject_scores.length} suffix="科" />
              </div>
            </section>

            <div className="student-sensitive-bar">
              <Space>
                <Switch checked={showSensitive} onChange={confirmSensitiveToggle} />
                <span>显示敏感个人信息</span>
              </Space>
              <Tag color="blue">所有查看和修改均记录审计</Tag>
            </div>

            <Tabs
              items={[
                {
                  key: "basic",
                  label: "基础信息",
                  children: (
                    <Descriptions className="student-descriptions" bordered column={2} size="small">
                      <Descriptions.Item label="招生年度">{detail.basic.year_no}</Descriptions.Item>
                      <Descriptions.Item label="数据版本">
                        {detail.basic.is_synthetic ? <Tag color="gold">模拟数据</Tag> : <Tag color="blue">真实数据</Tag>}
                      </Descriptions.Item>
                      <Descriptions.Item label="姓名">{detail.basic.student_name}</Descriptions.Item>
                      <Descriptions.Item label="考生号">{detail.basic.ksh}</Descriptions.Item>
                      <Descriptions.Item label="准考证号">{detail.basic.zkzh}</Descriptions.Item>
                      <Descriptions.Item label="性别">{detail.profile?.gender_name ?? ""}</Descriptions.Item>
                      <Descriptions.Item label="民族">{detail.profile?.ethnicity_name ?? ""}</Descriptions.Item>
                      <Descriptions.Item label="考试类型">{detail.profile?.exam_type_name ?? ""}</Descriptions.Item>
                      <Descriptions.Item label="毕业学校">{detail.profile?.source_school_name ?? detail.basic.source_school}</Descriptions.Item>
                      <Descriptions.Item label="地区">{detail.profile?.region_name ?? detail.basic.region_code}</Descriptions.Item>
                      <Descriptions.Item label="身份证号">
                        {showSensitive ? detail.basic.id_card : maskId(detail.basic.id_card)}
                      </Descriptions.Item>
                      <Descriptions.Item label="联系电话">
                        {showSensitive ? detail.basic.phone : maskPhone(detail.basic.phone)}
                      </Descriptions.Item>
                      <Descriptions.Item label="通讯地址" span={2}>
                        {showSensitive ? detail.basic.address : "********"}
                      </Descriptions.Item>
                    </Descriptions>
                  ),
                },
                {
                  key: "admission",
                  label: "录取信息",
                  children: (
                    <Descriptions className="student-descriptions" bordered column={2} size="small">
                      <Descriptions.Item label="批次">{detail.admission?.batch_name ?? ""}</Descriptions.Item>
                      <Descriptions.Item label="科类">{detail.admission?.subject_name ?? ""}</Descriptions.Item>
                      <Descriptions.Item label="考生成绩">{detail.admission?.exam_score ?? ""}</Descriptions.Item>
                      <Descriptions.Item label="投档成绩">{detail.admission?.filing_score ?? ""}</Descriptions.Item>
                      <Descriptions.Item label="录取专业">{detail.admission?.major_name ?? ""}</Descriptions.Item>
                    </Descriptions>
                  ),
                },
                {
                  key: "scores",
                  label: `学科成绩 · ${detail.subject_scores.length}`,
                  children: (
                    <Table
                      rowKey={(row) => `${row.subject_code}-${row.exam_year_month}`}
                      size="small"
                      pagination={false}
                      dataSource={detail.subject_scores}
                      columns={[
                        { title: "科目", dataIndex: "subject_name" },
                        { title: "成绩", dataIndex: "score" },
                        { title: "考试年月", dataIndex: "exam_year_month" },
                      ]}
                    />
                  ),
                },
                {
                  key: "choices",
                  label: `专业志愿 · ${detail.major_choices.length}`,
                  children: (
                    <Table
                      rowKey={(row) => String(row.choice_order)}
                      size="small"
                      pagination={false}
                      dataSource={detail.major_choices}
                      columns={[
                        { title: "志愿序号", dataIndex: "choice_order" },
                        { title: "专业", dataIndex: "major_name" },
                        { title: "专业代码", dataIndex: "major_code" },
                      ]}
                    />
                  ),
                },
                {
                  key: "resume",
                  label: "学习经历",
                  children: (
                    <Table
                      rowKey={(row) => `${row.start_date}-${row.school_name}`}
                      size="small"
                      pagination={false}
                      dataSource={detail.resumes}
                      columns={[
                        { title: "开始", dataIndex: "start_date" },
                        { title: "结束", dataIndex: "end_date" },
                        { title: "学校/经历", dataIndex: "school_name" },
                        { title: "职务/荣誉", dataIndex: "role_name" },
                      ]}
                    />
                  ),
                },
                {
                  key: "medical",
                  label: "体检摘要",
                  children: detail.medical_summary ? (
                    <Descriptions className="student-descriptions" bordered column={1} size="small">
                      <Descriptions.Item label="体检结论">
                        {detail.medical_summary.medical_result_name ?? detail.medical_summary.medical_result_code}
                      </Descriptions.Item>
                      <Descriptions.Item label="专业限制代码">
                        {Array.isArray(detail.medical_summary.restricted_major_codes)
                          ? detail.medical_summary.restricted_major_codes.join("，")
                          : ""}
                      </Descriptions.Item>
                    </Descriptions>
                  ) : (
                    <Alert type="info" message="暂无体检摘要" />
                  ),
                },
                {
                  key: "management",
                  label: "跟进管理",
                  children: (
                    <div className="student-management-panel">
                      <div className="student-management-note">
                        <DatabaseOutlined />
                        <div>
                          <strong>年度隔离写入</strong>
                          <span>保存后会写入 {detail.basic.year_no} 年学生管理记录，不影响其他年度。</span>
                        </div>
                      </div>
                      <Form form={managementForm} layout="vertical">
                        <Row gutter={18}>
                          <Col xs={24} md={12}>
                            <Form.Item label="学生状态" name="student_status">
                              <Select options={studentStatusOptions} />
                            </Form.Item>
                          </Col>
                          <Col xs={24} md={12}>
                            <Form.Item label="跟进状态" name="follow_up_status">
                              <Select options={followUpOptions} />
                            </Form.Item>
                          </Col>
                          <Col xs={24} md={12}>
                            <Form.Item label="负责人" name="owner_name">
                              <Input maxLength={128} placeholder="请输入负责人姓名" />
                            </Form.Item>
                          </Col>
                          <Col xs={24} md={12}>
                            <Form.Item label="标签" name="tags">
                              <Select mode="tags" tokenSeparators={[","]} placeholder="输入标签后回车" />
                            </Form.Item>
                          </Col>
                          <Col span={24}>
                            <Form.Item label="跟进备注" name="notes">
                              <Input.TextArea rows={5} maxLength={5000} showCount placeholder="记录沟通结果、关注事项和后续动作" />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Button type="primary" size="large" loading={saving} onClick={() => void saveManagement()}>
                          保存跟进信息
                        </Button>
                      </Form>
                    </div>
                  ),
                },
              ]}
            />
          </>
        )}
      </Drawer>
    </div>
  );
}























