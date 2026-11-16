import { App, Button, Form, Input, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { login } from "@/lib/api/client";

type LoginForm = {
  username: string;
  password: string;
};

export default function LoginPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [form] = Form.useForm<LoginForm>();
  const [loading, setLoading] = useState(false);

  async function handleSubmit(values: LoginForm): Promise<void> {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success("登录成功");
      navigate("/dashboard");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <Typography.Title level={2}>招录智策</Typography.Title>
        <Typography.Paragraph type="secondary">
          高校招生数据管理与分析平台
        </Typography.Paragraph>
        <Form<LoginForm>
          form={form}
          layout="vertical"
          initialValues={{ username: "admin", password: "ChangeMe123!" }}
          onFinish={handleSubmit}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input size="large" placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password size="large" placeholder="请输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={loading}>
            登录
          </Button>
        </Form>
      </section>
    </main>
  );
}


