import { InboxOutlined } from "@ant-design/icons";
import { Alert, App, Button, Descriptions, Drawer, Form, Input, Space, Table, Tag, Upload } from "antd";
import type { UploadFile } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type DbfBatch = {
  batch_id: number;
  batch_name: string;
  source_file: string | null;
  status: string;
  total_files: number;
  total_records: number;
  file_size: number | null;
  created_at: string;
  finished_at: string | null;
  error_message: string | null;
};

type DbfField = {
  name: string;
  type: string;
  length: number;
  decimals: number;
};

type DbfTable = {
  id: number;
  table_name: string;
  file_name: string;
  record_count: number;
  field_count: number;
  fields: DbfField[];
};

type DbfBatchDetail = DbfBatch & { tables: DbfTable[] };
type DbfRow = { row_no: number; data: Record<string, unknown> };

export default function DbfImportPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [selectedBatch, setSelectedBatch] = useState<number | null>(null);
  const [selectedTable, setSelectedTable] = useState<DbfTable | null>(null);

  const { data: batches = [] } = useQuery({
    queryKey: ["dbf-imports"],
    queryFn: () =>
      apiFetch<{ items: DbfBatch[] }>("/data/dbf/imports").then((response) => response.items),
  });

  const { data: detail } = useQuery({
    queryKey: ["dbf-import-detail", selectedBatch],
    queryFn: () => apiFetch<DbfBatchDetail>(`/data/dbf/imports/${selectedBatch}`),
    enabled: Boolean(selectedBatch),
  });

  const { data: rows = [] } = useQuery({
    queryKey: ["dbf-import-rows", selectedBatch, selectedTable?.table_name],
    queryFn: () =>
      apiFetch<{ items: DbfRow[] }>(
        `/data/dbf/imports/${selectedBatch}/tables/${selectedTable?.table_name}/rows?limit=20`,
      ).then((response) => response.items),
    enabled: Boolean(selectedBatch && selectedTable),
  });


  function handleNormalize(batchId: number): void {
    modal.confirm({
      title: "归一化 DBF 数据",
      content:
        "此操作会清除现有业务分析数据，并根据当前 DBF 批次重建维度、计划、投档、成绩、志愿和画像表。是否继续？",
      okText: "清除并归一化",
      cancelText: "取消",
      onOk: async () => {
        try {
          const result = await apiFetch<Record<string, number>>(
            `/data/dbf/imports/${batchId}/normalize`,
            {
              method: "POST",
              body: JSON.stringify({ clear_existing: true }),
            },
          );
          message.success(`归一化完成，考生 ${result.candidate_profiles ?? 0} 人`);
          await queryClient.invalidateQueries();
        } catch (error) {
          message.error(error instanceof Error ? error.message : "归一化失败");
        }
      },
    });
  }

  async function handleUpload(values: { batch_name?: string; file: UploadFile[] }): Promise<void> {
    const file = values.file?.[0]?.originFileObj;
    if (!file) {
      message.error("请选择 DBF 压缩包");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    if (values.batch_name) {
      formData.append("batch_name", values.batch_name);
    }

    setUploading(true);
    try {
      const batch = await apiFetch<DbfBatch>("/data/dbf/imports", {
        method: "POST",
        body: formData,
      });
      message.success(`DBF 导入完成：${batch.total_files} 个文件，${batch.total_records} 条记录`);
      await queryClient.invalidateQueries({ queryKey: ["dbf-imports"] });
      setSelectedBatch(batch.batch_id);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "DBF 导入失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="dbf-import-page">
      <PageHero
        title="DBF 原始数据导入"
        description="接收招录系统原始压缩包，保留表结构识别、字段记录和批次审计链路。"
      />

      <Form layout="vertical" onFinish={handleUpload} style={{ maxWidth: 760 }}>
        <Form.Item label="批次名称" name="batch_name">
          <Input placeholder="例如 2026年全部招生原始数据" />
        </Form.Item>
        <Form.Item
          label="DBF 压缩包"
          name="file"
          valuePropName="fileList"
          getValueFromEvent={(event) => event?.fileList}
          rules={[{ required: true, message: "请选择 zip 压缩包" }]}
        >
          <Upload.Dragger beforeUpload={() => false} maxCount={1} accept=".zip">
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽 zip 文件到这里</p>
            <p className="ant-upload-hint">压缩包中可以包含多个 DBF 文件和代码字典表</p>
          </Upload.Dragger>
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={uploading}>
          解析并导入 DBF
        </Button>
      </Form>

      <section className="chart-panel" style={{ marginTop: 24 }}>
        <h2>导入批次</h2>
        <Table
          rowKey="batch_id"
          dataSource={batches}
          pagination={false}
          onRow={(record) => ({ onClick: () => setSelectedBatch(record.batch_id) })}
          columns={[
            { title: "批次", dataIndex: "batch_name" },
            { title: "来源", dataIndex: "source_file" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => (
                <Tag color={value === "COMPLETED" ? "green" : value === "FAILED" ? "red" : "blue"}>
                  {value}
                </Tag>
              ),
            },
            { title: "文件数", dataIndex: "total_files" },
            { title: "记录数", dataIndex: "total_records" },
            { title: "创建时间", dataIndex: "created_at" },
          ]}
        />
      </section>

      <Drawer
        title={detail?.batch_name ?? "DBF 导入详情"}
        width={1000}
        open={Boolean(selectedBatch)}
        onClose={() => setSelectedBatch(null)}
      >
        {detail ? (
          <>
            <Space style={{ marginBottom: 16 }}>
              <Button
                type="primary"
                danger
                onClick={() => handleNormalize(detail.batch_id)}
              >
                清除旧业务数据并归一化
              </Button>
            </Space>
            <Descriptions column={2} size="small" style={{ marginBottom: 20 }}>
              <Descriptions.Item label="来源文件">{detail.source_file}</Descriptions.Item>
              <Descriptions.Item label="状态">{detail.status}</Descriptions.Item>
              <Descriptions.Item label="DBF 文件数">{detail.total_files}</Descriptions.Item>
              <Descriptions.Item label="总记录数">{detail.total_records}</Descriptions.Item>
              <Descriptions.Item label="完成时间">{detail.finished_at}</Descriptions.Item>
              <Descriptions.Item label="错误信息">{detail.error_message ?? "无"}</Descriptions.Item>
            </Descriptions>

            <Table
              rowKey="id"
              dataSource={detail.tables}
              pagination={false}
              onRow={(record) => ({ onClick: () => setSelectedTable(record) })}
              columns={[
                { title: "表名", dataIndex: "table_name" },
                { title: "文件", dataIndex: "file_name" },
                { title: "记录数", dataIndex: "record_count" },
                { title: "字段数", dataIndex: "field_count" },
              ]}
            />
          </>
        ) : null}
      </Drawer>

      <Drawer
        title={selectedTable ? `${selectedTable.table_name} 字段与数据` : "表详情"}
        width={1200}
        open={Boolean(selectedTable)}
        onClose={() => setSelectedTable(null)}
      >
        {selectedTable ? (
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <Alert
              type="warning"
              showIcon
              message="敏感字段已脱敏"
              description="考生号、姓名、证件号、联系方式、体检信息和证明人不会在原始数据预览中显示。"
            />
            <Table
              rowKey="name"
              size="small"
              pagination={false}
              dataSource={selectedTable.fields}
              columns={[
                { title: "字段", dataIndex: "name" },
                { title: "类型", dataIndex: "type" },
                { title: "长度", dataIndex: "length" },
                { title: "小数位", dataIndex: "decimals" },
              ]}
            />
            <Table
              rowKey="row_no"
              size="small"
              dataSource={rows}
              pagination={false}
              scroll={{ x: "max-content" }}
              columns={[
                { title: "行号", dataIndex: "row_no", fixed: "left" },
                ...selectedTable.fields.map((field) => ({
                  title: field.name,
                  key: field.name,
                  render: (_: unknown, row: DbfRow) => String(row.data[field.name] ?? ""),
                })),
              ]}
            />
          </Space>
        ) : null}
      </Drawer>
    </div>
  );
}

