import { App, Button, Form, Input, Modal, Select, Space, Table, Tag } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type UserSummary = {
  id: number;
  username: string;
  display_name: string | null;
  status: string;
  roles: string[];
};

type RoleSummary = {
  id: number;
  role_code: string;
  role_name: string;
};

type UserForm = {
  username?: string;
  password?: string;
  display_name?: string;
  role_codes: string[];
};

export default function UsersPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<UserForm>();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<UserSummary | null>(null);

  const { data: users = [] } = useQuery({
    queryKey: ["system-users"],
    queryFn: () => apiFetch<UserSummary[]>("/users"),
  });

  const { data: roles = [] } = useQuery({
    queryKey: ["system-roles"],
    queryFn: () => apiFetch<RoleSummary[]>("/users/roles"),
  });

  function openCreate(): void {
    setEditing(null);
    form.resetFields();
    setOpen(true);
  }

  function openEdit(user: UserSummary): void {
    setEditing(user);
    form.setFieldsValue({
      display_name: user.display_name ?? "",
      role_codes: user.roles,
    });
    setOpen(true);
  }

  async function handleSubmit(): Promise<void> {
    const values = await form.validateFields();
    try {
      if (editing) {
        await apiFetch(`/users/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            display_name: values.display_name,
            role_codes: values.role_codes,
          }),
        });
        message.success("用户信息已更新");
      } else {
        await apiFetch("/users", {
          method: "POST",
          body: JSON.stringify(values),
        });
        message.success("用户创建成功");
      }
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["system-users"] });
    } catch (error) {
      message.error(error instanceof Error ? error.message : "操作失败");
    }
  }

  async function toggleStatus(user: UserSummary): Promise<void> {
    const nextStatus = user.status === "ACTIVE" ? "DISABLED" : "ACTIVE";
    try {
      await apiFetch(`/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      message.success(nextStatus === "ACTIVE" ? "用户已启用" : "用户已停用");
      await queryClient.invalidateQueries({ queryKey: ["system-users"] });
    } catch (error) {
      message.error(error instanceof Error ? error.message : "操作失败");
    }
  }

  return (
    <div className="system-users-page">
      <PageHero
        title="用户管理"
        description="维护账号、角色与数据访问身份，让每个决策动作都可追溯。"
        actions={<Button type="primary" onClick={openCreate}>新建用户</Button>}
      />

      <Table
        rowKey="id"
        dataSource={users}
        pagination={false}
        columns={[
          { title: "用户名", dataIndex: "username" },
          { title: "显示名称", dataIndex: "display_name" },
          {
            title: "角色",
            dataIndex: "roles",
            render: (value: string[]) => (
              <Space wrap>
                {value.map((role) => (
                  <Tag key={role} color="blue">
                    {role}
                  </Tag>
                ))}
              </Space>
            ),
          },
          {
            title: "状态",
            dataIndex: "status",
            render: (value: string) => (
              <Tag color={value === "ACTIVE" ? "green" : "red"}>
                {value === "ACTIVE" ? "正常" : "停用"}
              </Tag>
            ),
          },
          {
            title: "操作",
            render: (_, user) => (
              <Space>
                <Button size="small" onClick={() => openEdit(user)}>
                  编辑
                </Button>
                <Button size="small" danger={user.status === "ACTIVE"} onClick={() => toggleStatus(user)}>
                  {user.status === "ACTIVE" ? "停用" : "启用"}
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? "编辑用户" : "新建用户"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleSubmit}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          {!editing ? (
            <>
              <Form.Item label="用户名" name="username" rules={[{ required: true, min: 3 }]}>
                <Input />
              </Form.Item>
              <Form.Item label="初始密码" name="password" rules={[{ required: true, min: 8 }]}>
                <Input.Password />
              </Form.Item>
            </>
          ) : null}
          <Form.Item label="显示名称" name="display_name">
            <Input />
          </Form.Item>
          <Form.Item label="角色" name="role_codes" rules={[{ required: true }]}>
            <Select
              mode="multiple"
              options={roles.map((role) => ({
                value: role.role_code,
                label: `${role.role_name} (${role.role_code})`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

