import { DislikeOutlined, LikeOutlined } from "@ant-design/icons";
import { App, Button, Collapse, Empty, Input, Space, Spin, Table, Tag } from "antd";
import { useState } from "react";

import { ResultExportMenu } from "@/components/actions/result-export-menu";
import type { ChartOption } from "@/components/charts/echarts-container";
import { LazyEChartsContainer } from "@/components/charts/lazy-echarts-container";
import { PageHero } from "@/components/layout/page-hero";
import { apiFetch, apiStream } from "@/lib/api/client";

type ChatResponse = {
  conversation_id: number;
  message_id: number;
  intent: string;
  answer: string;
  confidence: string;
  need_human: boolean;
  data_sources: Array<Record<string, string>>;
  citations: Array<{ title: string; url: string }>;
  charts: ChartOption[];
  table: {
    columns: string[];
    rows: Array<Array<string | number | null>>;
  } | null;
  tool_calls: Array<Record<string, unknown>>;
  suggestions: string[];
  plan_summary: string | null;
  reasoning_trace: string[];
  self_check: {
    score?: number;
    action?: string;
    issues?: string[];
    dimensions?: Record<string, number>;
  };
  memory_used: Array<{ summary: string; memory_type: string }>;
  knowledge_sources: Array<{ title: string; content?: string; score?: number }>;
  school_context: Record<string, unknown>;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  question?: string;
  response?: ChatResponse;
  feedback?: "positive" | "negative";
  feedbackLoading?: "positive" | "negative";
  reflection?: {
    summary: string;
    error_points: Array<{ code: string; label: string; detail: string }>;
    second_answer: string;
    selection_mode: string;
    selection_reason: string;
    second_error?: string | null;
    compression?: {
      compressed: boolean;
      active_count: number;
      summary_memory_id?: number;
    };
  };
};

type FeedbackResponse = {
  status: string;
  feedback: "positive" | "negative";
  reflection?: ChatMessage["reflection"];
};

const examples = [
  "2025年各专业招生计划完成情况怎么样？",
  "生源渠道和报到情况怎么样？",
  "各省招生计划是多少？",
  "最低录取分和最低位次是多少？",
];

export default function AiAssistantPage() {
  const { message } = App.useApp();
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState("正在查询和校验数据...");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "我是招录智策 AI 助手。可以查询招生计划、录取、专业、生源和渠道等统计数据。",
    },
  ]);

  async function sendFeedback(messageIndex: number, rating: number): Promise<void> {
    const target = messages[messageIndex];
    if (!target?.response || target.feedback || target.feedbackLoading) {
      return;
    }
    const history = messages
      .slice(0, messageIndex)
      .filter((item) => item.content)
      .slice(-6)
      .map((item) => ({ role: item.role, content: item.content.slice(0, 800) }));
    setMessages((current) =>
      current.map((item, index) =>
        index === messageIndex
          ? { ...item, feedbackLoading: rating >= 4 ? "positive" : "negative" }
          : item,
      ),
    );
    try {
      const result = await apiFetch<FeedbackResponse>("/ai/feedback", {
        method: "POST",
        body: JSON.stringify({
          message_id: target.response.message_id,
          rating,
          question: target.question || "",
          answer: target.content,
          conversation_id: conversationId,
          history,
        }),
      });
      setMessages((current) =>
        current.map((item, index) =>
          index === messageIndex
            ? {
                ...item,
                feedbackLoading: undefined,
                feedback: result.feedback,
                reflection: result.reflection,
              }
            : item,
        ),
      );
      message.success(
        rating >= 4
          ? "已认同这条回答"
          : result.reflection?.compression?.compressed
            ? "已记录错误原因，并完成反思记忆压缩"
            : "已记录错误原因并完成二次复核",
      );
    } catch (error) {
      setMessages((current) =>
        current.map((item, index) =>
          index === messageIndex ? { ...item, feedbackLoading: undefined } : item,
        ),
      );
      message.error(error instanceof Error ? error.message : "反馈失败");
    }
  }

  async function sendQuestion(value?: string): Promise<void> {
    const text = (value ?? question).trim();
    if (!text) {
      return;
    }

    setMessages((current) => [...current, { role: "user", content: text }]);
    setQuestion("");
    setLoading(true);
    setStatusText("已提交问题，正在识别意图...");

    try {
      let response: ChatResponse | undefined;
      const requestBody = JSON.stringify({
        message: text,
        conversation_id: conversationId,
        context: {
          history: messages
            .filter((item) => item.content)
            .slice(-6)
            .map((item) => ({ role: item.role, content: item.content.slice(0, 800) })),
        },
      });
      try {
        await apiStream("/ai/chat/stream", { method: "POST", body: requestBody }, (event, data) => {
          if (event === "heartbeat") {
            const elapsed = Number(data.elapsed_ms ?? 0);
            setStatusText(elapsed > 0 ? `正在查询和校验数据... ${Math.round(elapsed)}ms` : "正在查询和校验数据...");
          } else if (event === "answer") {
            response = data as unknown as ChatResponse;
            setConversationId(response.conversation_id);
            setMessages((current) => [
              ...current,
              {
                role: "assistant",
                content: response!.answer,
                question: text,
                response: response!,
              },
            ]);
          } else if (event === "error") {
            throw new Error(String(data.message ?? "流式请求失败"));
          }
        });
      } catch (streamError) {
        if (response) {
          throw streamError;
        }
        response = await apiFetch<ChatResponse>("/ai/chat", {
          method: "POST",
          body: requestBody,
        });
      }
      if (!response) {
        throw new Error("AI 未返回有效回答");
      }
      setConversationId(response.conversation_id);
      if (!messages.some((item) => item.response?.message_id === response?.message_id)) {
        setMessages((current) => {
          if (current.some((item) => item.response?.message_id === response?.message_id)) {
            return current;
          }
          return [
            ...current,
            {
              role: "assistant",
              content: response!.answer,
              question: text,
              response: response!,
            },
          ];
        });
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "AI 问数失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ai-assistant-page">
      <PageHero
        title="AI 招录助手"
        description="用自然语言发起招生问数、证据核验与行动建议，关键数字始终回到受控数据工具。"
      />

      <Space wrap style={{ marginBottom: 16 }}>
        {examples.map((example) => (
          <Button key={example} onClick={() => sendQuestion(example)}>
            {example}
          </Button>
        ))}
      </Space>

      <section className="chat-panel">
        {messages.map((item, index) => (
          <article className={`chat-message ${item.role}`} key={`${item.role}-${index}`}>
            <div className="chat-role">{item.role === "user" ? "用户" : "AI 助手"}</div>
            <div className="chat-content">{item.content}</div>

            {item.response?.charts?.map((chart, chartIndex) => (
              <div className="chat-chart" key={`chart-${chartIndex}`}>
                <LazyEChartsContainer option={chart} height={300} />
              </div>
            ))}

            {item.response ? (
              <Collapse
                ghost
                size="small"
                style={{ marginTop: 12 }}
                items={[
                  {
                    key: "reasoning",
                    label: `智能体思考与自查 · ${Math.round((item.response.self_check?.score ?? 0) * 100)}分`,
                    children: (
                      <Space direction="vertical" size={8} style={{ width: "100%" }}>
                        {(item.response.reasoning_trace ?? []).map((step) => (
                          <Tag key={step} color="geekblue">
                            {step}
                          </Tag>
                        ))}
                        {item.response.self_check?.issues?.length ? (
                          <Space wrap>
                            {item.response.self_check.issues.map((issue) => (
                              <Tag key={issue} color="orange">
                                自查：{issue}
                              </Tag>
                            ))}
                          </Space>
                        ) : (
                          <Tag color="green">自查通过：数据依据、数字一致性和回答完整性正常</Tag>
                        )}
                        {item.response.memory_used?.length ? (
                          <div>
                            长期记忆：
                            {item.response.memory_used.map((memory) => (
                              <Tag key={memory.summary} color="purple">
                                {memory.summary}
                              </Tag>
                            ))}
                          </div>
                        ) : null}
                      </Space>
                    ),
                  },
                ]}
              />
            ) : null}

            {item.response?.table ? (
              <Table
                size="small"
                rowKey="key"
                pagination={false}
                dataSource={item.response.table.rows.map((row, rowIndex) => {
                  const record: Record<string, string | number | null> = { key: rowIndex };
                  item.response?.table?.columns.forEach((column, columnIndex) => {
                    record[column] = row[columnIndex];
                  });
                  return record;
                })}
                columns={item.response.table.columns.map((column) => ({
                  title: column,
                  dataIndex: column,
                  key: column,
                }))}
                scroll={{ x: "max-content" }}
              />
            ) : null}

            {item.response ? (
              <Space wrap style={{ marginTop: 12 }}>
                <Tag color={item.response.confidence === "high" ? "green" : "gold"}>
                  置信度：{item.response.confidence}
                </Tag>
                {item.response.data_sources.map((source) => (
                  <Tag key={`${source.table}-${source.metric}`} color="blue">
                    {source.table} · {source.metric}
                  </Tag>
                ))}
                {item.response.citations?.map((citation) => (
                  <a key={citation.url} href={citation.url} target="_blank" rel="noreferrer">
                    <Tag color="cyan">{citation.title}</Tag>
                  </a>
                ))}
                {item.response.need_human ? <Tag color="red">建议转人工</Tag> : null}
                {item.response.plan_summary ? (
                  <Tag color="purple">AI 处理：{item.response.plan_summary}</Tag>
                ) : null}
                <ResultExportMenu
                  kind="query"
                  title={`AI问数结果：${item.question ?? item.response.intent}`}
                  filename={`AI问数结果_${item.response.message_id}`}
                  question={item.question}
                  answer={item.content}
                  table={item.response.table}
                  metrics={{
                    intent: item.response.intent,
                    confidence: item.response.confidence,
                    need_human: item.response.need_human,
                    self_check_score: item.response.self_check?.score,
                  }}
                  sections={[
                    {
                      title: "智能体自查",
                      text: JSON.stringify(item.response.self_check ?? {}, null, 2),
                    },
                    {
                      title: "工具调用",
                      text: JSON.stringify(item.response.tool_calls ?? [], null, 2),
                    },
                  ]}
                  metadata={{
                    message_id: item.response.message_id,
                    conversation_id: item.response.conversation_id,
                    intent: item.response.intent,
                    sources: item.response.data_sources,
                  }}
                />
                <Button
                  size="small"
                  icon={<LikeOutlined />}
                  type={item.feedback === "positive" ? "primary" : "default"}
                  loading={item.feedbackLoading === "positive"}
                  disabled={item.feedback === "negative"}
                  onClick={() => void sendFeedback(index, 5)}
                >
                  认同
                </Button>
                <Button
                  size="small"
                  icon={<DislikeOutlined />}
                  danger={item.feedback === "negative"}
                  loading={item.feedbackLoading === "negative"}
                  disabled={item.feedback === "positive"}
                  onClick={() => void sendFeedback(index, 1)}
                >
                  否定
                </Button>
              </Space>
            ) : null}

            {item.reflection ? (
              <section className="reflection-result">
                <div className="reflection-result-heading">
                  <strong>反思与二次复核</strong>
                  <Tag color={item.reflection.selection_mode === "insufficient" ? "orange" : "blue"}>
                    {item.reflection.selection_mode === "refined"
                      ? "已修正"
                      : item.reflection.selection_mode === "maintained"
                        ? "维持原结论"
                        : "证据不足"}
                  </Tag>
                </div>
                <div className="reflection-result-points">
                  {item.reflection.error_points.map((point) => (
                    <div key={point.code}>
                      <strong>{point.label}</strong>
                      <span>{point.detail}</span>
                    </div>
                  ))}
                </div>
                <div className="reflection-secondary-answer">
                  <span>二次复核结论</span>
                  <p>{item.reflection.second_answer}</p>
                  <small>{item.reflection.selection_reason}</small>
                </div>
                {item.reflection.second_error ? (
                  <div className="reflection-result-error">
                    二次复核异常：{item.reflection.second_error}
                  </div>
                ) : null}
                {item.reflection.compression?.compressed ? (
                  <div className="reflection-compressed">
                    已将 {item.reflection.compression.active_count} 条错误记忆压缩为后续检查规则。
                  </div>
                ) : (
                  <div className="reflection-compressed">
                    错误原因已记录，累计同类问题后将自动压缩为检查规则。
                  </div>
                )}
              </section>
            ) : null}

            {item.response?.suggestions?.length ? (
              <Space wrap style={{ marginTop: 12 }}>
                {item.response.suggestions.map((suggestion) => (
                  <Button key={suggestion} size="small" onClick={() => sendQuestion(suggestion)}>
                    {suggestion}
                  </Button>
                ))}
              </Space>
            ) : null}
          </article>
        ))}

        {loading ? (
          <div className="chat-message assistant">
            <Spin /> <span style={{ marginLeft: 10 }}>{statusText}</span>
          </div>
        ) : null}

        {!messages.length ? <Empty description="暂无对话" /> : null}
      </section>

      <Space.Compact style={{ width: "100%", marginTop: 16 }}>
        <Input.TextArea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="例如：2025年各专业招生计划完成情况怎么样？"
          autoSize={{ minRows: 1, maxRows: 3 }}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              void sendQuestion();
            }
          }}
        />
        <Button type="primary" onClick={() => void sendQuestion()} loading={loading}>
          发送
        </Button>
      </Space.Compact>
    </div>
  );
}

