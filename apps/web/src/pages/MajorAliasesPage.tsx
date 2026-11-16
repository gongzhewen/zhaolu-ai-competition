import { Alert, App, Button, Card, Form, Input, Modal, Select, Space, Statistic, Switch, Table, Tag } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";

type AliasItem = {
  id: number;
  source_name: string;
  province_id: number | null;
  province_name: string | null;
  canonical_major_id: number;
  canonical_major_name: string;
  note: string | null;
  is_active: boolean;
  source_major_count: number;
  affected_plan_count: number;
  affected_record_count: number;
};

type AliasOptions = {
  provinces: Array<{ id: number; province_code: string; province_name: string }>;
  majors: Array<{ id: number; major_code: string; major_name: string; plan_record_count: number; plan_count: number }>;
};

type AliasForm = {
  source_name: string;
  province_id?: number;
  canonical_major_id: number;
  note?: string;
  is_active: boolean;
};

export default function MajorAliasesPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<AliasForm>();
  const [renameForm] = Form.useForm<{ major_name: string }>();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<AliasItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [renameTarget, setRenameTarget] = useState<AliasOptions["majors"][number] | null>(null);
  const [renameOpen, setRenameOpen] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["major-aliases"],
    queryFn: () => apiFetch<{ items: AliasItem[] }>("/major-aliases"),
  });
  const { data: options, isLoading: optionsLoading } = useQuery({
    queryKey: ["major-alias-options"],
    queryFn: () => apiFetch<AliasOptions>("/major-aliases/options"),
  });

  const items = data?.items ?? [];

  function openCreate(): void {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true });
    setOpen(true);
  }

  function openEdit(item: AliasItem): void {
    setEditing(item);
    form.setFieldsValue({
      source_name: item.source_name,
      province_id: item.province_id ?? undefined,
      canonical_major_id: item.canonical_major_id,
      note: item.note ?? undefined,
      is_active: item.is_active,
    });
    setOpen(true);
  }

  function openRename(item: AliasOptions["majors"][number]): void {
    setRenameTarget(item);
    renameForm.setFieldsValue({ major_name: item.major_name });
    setRenameOpen(true);
  }

  async function submitRename(): Promise<void> {
    if (!renameTarget) return;
    const values = await renameForm.validateFields();
    setSaving(true);
    try {
      await apiFetch(`/major-aliases/majors/${renameTarget.id}`, {
        method: "PUT",
        body: JSON.stringify(values),
      });
      message.success("标准专业名称已修改");
      setRenameOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["major-alias-options"] }),
        queryClient.invalidateQueries({ queryKey: ["major-aliases"] }),
        queryClient.invalidateQueries({ queryKey: ["admissions-overview"] }),
      ]);
    } catch (renameError) {
      message.error(renameError instanceof Error ? renameError.message : "专业名称修改失败");
    } finally {
      setSaving(false);
    }
  }

  async function submit(): Promise<void> {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await apiFetch(`/major-aliases/${editing.id}`, { method: "PUT", body: JSON.stringify(values) });
        message.success("专业别名已更新");
      } else {
        await apiFetch("/major-aliases", { method: "POST", body: JSON.stringify(values) });
        message.success("专业别名已新增");
      }
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["major-aliases"] });
    } catch (submitError) {
      message.error(submitError instanceof Error ? submitError.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(item: AliasItem): void {
    modal.confirm({
      title: "删除专业别名",
      content: `${item.source_name} → ${item.canonical_major_name}`,
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        await apiFetch(`/major-aliases/${item.id}`, { method: "DELETE" });
        message.success("专业别名已删除");
        await queryClient.invalidateQueries({ queryKey: ["major-aliases"] });
      },
    });
  }

  if (error) return <Alert type="error" message="专业别名加载失败" description={error.message} />;

  const activeCount = items.filter((item) => item.is_active).length;
  const affectedPlans = items.reduce((sum, item) => sum + Number(item.affected_plan_count), 0);
  const affectedRecords = items.reduce((sum, item) => sum + Number(item.affected_record_count), 0);

  return (
    <div className="alias-page">
      <section className="plan-hero alias-hero">
        <div>
          <h1>专业名称修正与标准化</h1>
          <p>
            同一专业在不同省份可能出现别名、简称或不同专业代码。通过别名映射统一统计口径，不覆盖原始来源名称。
          </p>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新增名称映射
        </Button>
      </section>

      <section className="metric-grid alias-metric-grid">
        <article className="metric-card"><div className="metric-label">映射规则</div><div className="metric-value">{items.length}</div></article>
        <article className="metric-card"><div className="metric-label">启用规则</div><div className="metric-value">{activeCount}</div></article>
        <article className="metric-card"><div className="metric-label">影响计划人数</div><div className="metric-value">{affectedPlans.toLocaleString()}</div></article>
        <article className="metric-card"><div className="metric-label">影响录取记录</div><div className="metric-value">{affectedRecords.toLocaleString()}</div></article>
      </section>

      <Card className="plan-table-card" bordered={false}>
        <div className="plan-table-heading">
          <div>
            <h2>专业别名映射规则</h2>
          </div>
          <Button icon={<ReloadOutlined />} onClick={() => void queryClient.invalidateQueries({ queryKey: ["major-aliases"] })}>
            刷新
          </Button>
        </div>
        <Table
          rowKey="id"
          loading={isLoading}
          dataSource={items}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: 1180 }}
          columns={[
            { title: "来源专业名称", dataIndex: "source_name", width: 240, render: (value: string) => <strong>{value}</strong> },
            {
              title: "生效范围",
              dataIndex: "province_name",
              width: 130,
              render: (value: string | null) => value ? <Tag color="blue">{value}</Tag> : <Tag>全局</Tag>,
            },
            {
              title: "标准专业",
              dataIndex: "canonical_major_name",
              width: 230,
              render: (value: string) => <Tag color="green">{value}</Tag>,
            },
            {
              title: "来源专业数",
              dataIndex: "source_major_count",
              width: 110,
              align: "right",
              render: (value: number) => value || <span style={{ color: "#dc2626" }}>未匹配</span>,
            },
            { title: "影响计划人数", dataIndex: "affected_plan_count", width: 130, align: "right" },
            { title: "影响录取记录", dataIndex: "affected_record_count", width: 130, align: "right" },
            {
              title: "状态",
              dataIndex: "is_active",
              width: 90,
              render: (value: boolean) => <Tag color={value ? "green" : "default"}>{value ? "启用" : "停用"}</Tag>,
            },
            { title: "备注", dataIndex: "note", width: 220, ellipsis: true },
            {
              title: "操作",
              width: 150,
              fixed: "right",
              render: (_, item: AliasItem) => (
                <Space>
                  <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(item)}>编辑</Button>
                  <Button type="link" danger icon={<DeleteOutlined />} onClick={() => confirmDelete(item)}>删除</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Card className="plan-table-card alias-major-card" bordered={false}>
        <div className="plan-table-heading">
          <div>
            <h2>标准专业名称字典</h2>
          </div>
          <Tag color="blue">{options?.majors.length ?? 0} 个专业记录</Tag>
        </div>
        <Alert
          type="warning"
          showIcon
          message="名称修改影响全部年度"
          description="标准专业名称会直接用于计划、录取和跨年度统计。若是不同名称需要合并统计，请优先使用上方专业别名映射。"
          style={{ margin: "16px 22px" }}
        />
        <Table
          rowKey="id"
          loading={optionsLoading}
          dataSource={options?.majors ?? []}
          pagination={{ pageSize: 12, showSizeChanger: true }}
          scroll={{ x: 980 }}
          columns={[
            { title: "专业代码", dataIndex: "major_code", width: 180 },
            { title: "标准专业名称", dataIndex: "major_name", width: 280, render: (value: string) => <strong>{value}</strong> },
            { title: "关联计划记录", dataIndex: "plan_record_count", width: 130, align: "right" },
            { title: "累计计划人数", dataIndex: "plan_count", width: 130, align: "right" },
            {
              title: "操作",
              width: 140,
              fixed: "right",
              render: (_, item: AliasOptions["majors"][number]) => (
                <Button type="link" icon={<EditOutlined />} onClick={() => openRename(item)}>
                  修改名称
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editing ? "编辑专业别名" : "新增专业别名"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void submit()}
        confirmLoading={saving}
        width={680}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          message="统计归并规则"
          description="系统在统计时使用标准专业名称，原始名称仍保留在数据源中。省份级规则优先于全局规则。"
          style={{ marginBottom: 18 }}
        />
        <Form form={form} layout="vertical">
          <Form.Item label="来源专业名称" name="source_name" rules={[{ required: true, message: "请输入来源专业名称" }]}>
            <Input placeholder="例如：计算机科学与技术（师范）" maxLength={255} />
          </Form.Item>
          <Form.Item label="生效省份" name="province_id" extra="不选择表示对所有省份生效">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              loading={optionsLoading}
              options={options?.provinces.map((item) => ({ value: item.id, label: item.province_name }))}
            />
          </Form.Item>
          <Form.Item label="标准专业" name="canonical_major_id" rules={[{ required: true, message: "请选择标准专业" }]}>
            <Select
              showSearch
              optionFilterProp="label"
              loading={optionsLoading}
              options={options?.majors.map((item) => ({
                value: item.id,
                label: `${item.major_name}（${item.major_code}） · 计划 ${item.plan_count}`,
              }))}
            />
          </Form.Item>
          <Form.Item label="备注" name="note">
            <Input.TextArea rows={3} maxLength={1000} showCount placeholder="记录省级名称差异或修正依据" />
          </Form.Item>
          <Form.Item label="启用状态" name="is_active" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="手动修改标准专业名称"
        open={renameOpen}
        onCancel={() => setRenameOpen(false)}
        onOk={() => void submitRename()}
        confirmLoading={saving}
        okText="确认修改"
        destroyOnHidden
      >
        <Alert
          type="warning"
          showIcon
          message="请确认名称口径"
          description="修改后会立即影响所有年度和专业统计。关联计划、录取记录不会丢失；如需保留原名称并合并统计，请使用专业别名映射。"
          style={{ marginBottom: 18 }}
        />
        <Form form={renameForm} layout="vertical">
          <Form.Item label="原专业名称">
            <Input value={renameTarget?.major_name} disabled />
          </Form.Item>
          <Form.Item label="新专业名称" name="major_name" rules={[{ required: true, message: "请输入新的专业名称" }]}>
            <Input maxLength={255} placeholder="请输入标准专业名称" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}





