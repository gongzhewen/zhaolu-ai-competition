import { App, Button, Card, Checkbox, Select, Space, Spin, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { PageHero } from "@/components/layout/page-hero";

type RoleSummary = {
  id: number;
  role_code: string;
  role_name: string;
};

type PermissionSummary = {
  id: number;
  permission_code: string;
  permission_name: string;
  permission_type: string;
};

type RolePermissions = {
  role_id: number;
  role_code: string;
  role_name: string;
  permission_codes: string[];
};

export default function RolesPage() {
  const { message } = App.useApp();
  const [selectedRoleId, setSelectedRoleId] = useState<number | undefined>();
  const [checkedPermissions, setCheckedPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const { data: roles = [] } = useQuery({
    queryKey: ["system-roles"],
    queryFn: () => apiFetch<RoleSummary[]>("/users/roles"),
  });
  const { data: permissions = [] } = useQuery({
    queryKey: ["system-permissions"],
    queryFn: () => apiFetch<PermissionSummary[]>("/users/permissions"),
  });

  const selectedRole = roles.find((role) => role.id === selectedRoleId);

  useEffect(() => {
    if (!selectedRoleId && roles.length) {
      setSelectedRoleId(roles[0].id);
    }
  }, [roles, selectedRoleId]);

  useEffect(() => {
    if (!selectedRoleId) {
      return;
    }
    setLoading(true);
    apiFetch<RolePermissions>(`/users/roles/${selectedRoleId}/permissions`)
      .then((response) => setCheckedPermissions(response.permission_codes))
      .catch((error) => message.error(error instanceof Error ? error.message : "权限加载失败"))
      .finally(() => setLoading(false));
  }, [message, selectedRoleId]);

  const groupedPermissions = useMemo(() => {
    const groups = new Map<string, PermissionSummary[]>();
    for (const permission of permissions) {
      const list = groups.get(permission.permission_type) ?? [];
      list.push(permission);
      groups.set(permission.permission_type, list);
    }
    return Array.from(groups.entries());
  }, [permissions]);

  async function handleSave(): Promise<void> {
    if (!selectedRoleId) {
      return;
    }
    setLoading(true);
    try {
      await apiFetch(`/users/roles/${selectedRoleId}/permissions`, {
        method: "PUT",
        body: JSON.stringify({ permission_codes: checkedPermissions }),
      });
      message.success("角色权限已保存");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "权限保存失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="system-roles-page">
      <PageHero
        title="角色权限"
        description="配置菜单、按钮与数据操作能力，让权限边界和业务责任保持一致。"
      />

      <Space wrap style={{ marginBottom: 20 }}>
        <Select
          style={{ width: 280 }}
          value={selectedRoleId}
          onChange={setSelectedRoleId}
          options={roles.map((role) => ({
            value: role.id,
            label: `${role.role_name} (${role.role_code})`,
          }))}
        />
        <Tag color="blue">权限数：{checkedPermissions.length}</Tag>
        <Button type="primary" onClick={handleSave} loading={loading}>
          保存权限
        </Button>
      </Space>

      {loading ? <Spin /> : null}

      <div className="permission-grid">
        {groupedPermissions.map(([type, items]) => (
          <Card key={type} title={type} size="small">
            <Checkbox.Group
              value={checkedPermissions}
              onChange={(values) => setCheckedPermissions(values as string[])}
              style={{ display: "grid", gap: 10 }}
            >
              {items.map((permission) => (
                <Checkbox key={permission.permission_code} value={permission.permission_code}>
                  {permission.permission_name} · {permission.permission_code}
                </Checkbox>
              ))}
            </Checkbox.Group>
          </Card>
        ))}
      </div>

      {selectedRole ? (
        <p style={{ color: "#6b7280", marginTop: 16 }}>
          当前正在编辑：{selectedRole.role_name}
        </p>
      ) : null}
    </div>
  );
}

