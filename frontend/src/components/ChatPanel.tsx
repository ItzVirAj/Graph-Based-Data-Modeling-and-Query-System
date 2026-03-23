import { useEffect, useMemo, useRef, useState } from "react";

import { clearSession, queryGraph, streamGraphQuery } from "../services/api";
import type { ChatMessage, GeneratedQuery, QueryMemory, QueryResponse } from "../types/api";

interface ChatPanelProps {
  highlightedNodes: string[];
  onApplyQueryFocus: (payload: { edgeIds: string[]; nodeIds: string[]; primaryNodeId: string | null; reasons: Record<string, string> }) => void;
  onClearHighlights: () => void;
  onResetConversationView: () => void;
  onStatusChange: (message: string) => void;
  scrollToNodeId: string | null;
}

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createSessionId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : createMessageId();
}

function normalizeId(value: string) {
  const parts = value.split(":");
  return parts[parts.length - 1] ?? value;
}

function pickPrimaryNodeId(question: string, relevantNodeIds: string[] | undefined): string | null {
  const idsInQuestion = question.match(/[A-Za-z]?\d{6,10}/g) ?? [];
  const normalizedRelevant = (relevantNodeIds ?? []).filter(Boolean);
  for (const candidate of idsInQuestion) {
    const exactMatch = normalizedRelevant.find((value) => normalizeId(value) === candidate || value === candidate);
    if (exactMatch) {
      return exactMatch;
    }
  }
  return normalizedRelevant[0] ?? null;
}

function buildHighlightReasons(nodeIds: string[], question: string): Record<string, string> {
  const questionId = question.match(/[A-Za-z]?\d{6,10}/)?.[0];
  return Object.fromEntries(nodeIds.map((nodeId) => [nodeId, questionId ? `Matched: ${questionId}` : "Matched result"]));
}

function highlightSql(sql: string) {
  const keywords = /\b(SELECT|FROM|JOIN|LEFT|RIGHT|INNER|OUTER|WHERE|GROUP BY|ORDER BY|LIMIT|AS|ON|COUNT|DISTINCT|AND|OR|WITH)\b/gi;
  const parts = sql.split(keywords);
  return parts.map((part, index) => {
    if (part.match(keywords)) {
      return <span key={`${part}-${index}`} className="font-semibold text-sky-700">{part}</span>;
    }
    return <span key={`${part}-${index}`} className="text-slate-700">{part}</span>;
  });
}

export function ChatPanel({ highlightedNodes, onApplyQueryFocus, onClearHighlights, onResetConversationView, onStatusChange, scrollToNodeId }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([{ id: createMessageId(), role: "assistant", text: "Hi! I can help you analyze the Order to Cash process." }]);
  const [isThinking, setIsThinking] = useState(false);
  const [streamingStage, setStreamingStage] = useState<string>("Ready");
  const [sessionId, setSessionId] = useState(createSessionId);
  const [memory, setMemory] = useState<QueryMemory | null>(null);
  const [expandedQueries, setExpandedQueries] = useState<Record<string, boolean>>({});
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    if (!scrollToNodeId) {
      return;
    }
    const targetMessage = [...messages].reverse().find((message) => message.relevantNodeIds?.some((nodeId) => normalizeId(nodeId) === normalizeId(scrollToNodeId)));
    if (targetMessage) {
      messageRefs.current[targetMessage.id]?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [messages, scrollToNodeId]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setInput("");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const activeHighlightCount = useMemo(() => highlightedNodes.length, [highlightedNodes.length]);

  const applyResponse = (question: string, response: QueryResponse, assistantMessageId: string) => {
    const primaryNodeId = pickPrimaryNodeId(question, response.relevant_node_ids);
    const edgeIds = response.raw_data?.graph_result?.path_edges?.map((edge) => edge.edge_id) ?? [];
    const nodeIds = response.relevant_node_ids ?? [];
    onApplyQueryFocus({ edgeIds, nodeIds, primaryNodeId, reasons: buildHighlightReasons(nodeIds, question) });
    onStatusChange(primaryNodeId ? `Focused graph on ${normalizeId(primaryNodeId)}.` : "Query completed.");
    setMessages((current) => current.map((message) => message.id === assistantMessageId ? {
      ...message,
      text: response.answer,
      relevantNodeIds: response.relevant_node_ids,
      relevantEdgeIds: edgeIds,
      rawData: response.raw_data,
      generatedQuery: response.generated_query,
      executionTimeMs: response.execution_time_ms,
      rejected: response.answer.includes("designed to answer questions related to the dataset only"),
    } : message));
    setMemory(response.memory ?? null);
    setSessionId(response.session_id || sessionId);
  };

  const handleSend = async () => {
    const question = input.trim();
    if (!question || isThinking) {
      return;
    }

    const userMessage: ChatMessage = { id: createMessageId(), role: "user", text: question };
    const assistantMessageId = createMessageId();
    const placeholderMessage: ChatMessage = { id: assistantMessageId, role: "assistant", text: "", generatedQuery: null };

    setMessages((current) => [...current, userMessage, placeholderMessage]);
    setInput("");
    setIsThinking(true);
    setStreamingStage("Checking query relevance...");
    onClearHighlights();

    try {
      let streamedQuery: GeneratedQuery | null = null;
      let streamedText = "";
      await streamGraphQuery(question, sessionId, {
        onStatus: (payload) => {
          const message = typeof payload.message === "string" ? payload.message : "Working...";
          setStreamingStage(message);
        },
        onQuery: (payload) => {
          streamedQuery = (payload.generated_query as GeneratedQuery | undefined) ?? null;
          setMessages((current) => current.map((message) => message.id === assistantMessageId ? { ...message, generatedQuery: streamedQuery } : message));
        },
        onToken: (payload) => {
          const token = typeof payload.text === "string" ? payload.text : "";
          streamedText += token;
          setMessages((current) => current.map((message) => message.id === assistantMessageId ? { ...message, text: streamedText } : message));
        },
        onComplete: (payload) => {
          applyResponse(question, payload, assistantMessageId);
        },
      });
    } catch {
      setStreamingStage("Streaming unavailable. Falling back...");
      const response = await queryGraph(question, sessionId);
      applyResponse(question, response, assistantMessageId);
    } finally {
      setIsThinking(false);
      setStreamingStage("Ready");
    }
  };

  const handleNewConversation = async () => {
    await clearSession(sessionId);
    setSessionId(createSessionId());
    setMemory(null);
    setMessages([{ id: createMessageId(), role: "assistant", text: "Starting a fresh conversation. Ask me about the graph." }]);
    setExpandedQueries({});
    onResetConversationView();
    onStatusChange("Started a new conversation.");
  };

  return (
    <aside className="ml-4 flex w-[430px] shrink-0 overflow-hidden rounded-[22px] border border-slate-200 bg-white shadow-sm">
      <div className="flex h-full min-h-0 w-full flex-col">
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-[18px] font-semibold text-slate-950">Chat with Graph</h2>
              <p className="mt-1 text-sm text-slate-500">Order to Cash</p>
            </div>
            <button className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50" onClick={() => void handleNewConversation()} type="button">New Conversation</button>
          </div>
        </div>

        <div className="border-b border-slate-100 px-5 py-5">
          <div className="flex items-start gap-4">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-slate-950 text-lg font-semibold text-white">D</div>
            <div className="min-w-0">
              <h3 className="text-[18px] font-semibold text-slate-950">Dodge AI</h3>
              <p className="text-sm text-slate-500">Graph Agent</p>
              <p className="mt-2 text-xs text-slate-400">Memory: {memory?.turn_count ?? 0}/{memory?.max_turns ?? 10} turns</p>
            </div>
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-auto px-5 py-5">
          {messages.map((message) => (
            <div key={message.id} ref={(element) => { messageRefs.current[message.id] = element; }} className="space-y-3 rounded-2xl border border-transparent p-1">
              <div className={`rounded-2xl px-4 py-3 text-[15px] leading-7 ${message.role === "user" ? "ml-8 bg-slate-950 text-white" : message.rejected ? "bg-amber-50 text-amber-800" : "bg-slate-50 text-slate-900"}`}>
                {message.text || (isThinking && message.id === messages[messages.length - 1]?.id ? "..." : "")}
              </div>
              {message.generatedQuery ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-3">
                  <button className="flex w-full items-center justify-between text-left text-sm font-medium text-slate-700" onClick={() => setExpandedQueries((current) => ({ ...current, [message.id]: !current[message.id] }))} type="button">
                    <span>{expandedQueries[message.id] ? "?" : "?"} View Generated Query</span>
                    {message.executionTimeMs ? <span className="text-xs text-slate-400">{message.executionTimeMs}ms</span> : null}
                  </button>
                  {expandedQueries[message.id] ? (
                    <div className="mt-3 space-y-3 rounded-2xl bg-slate-50 p-3 text-sm">
                      <div>
                        <div className="mb-1 font-semibold text-slate-900">SQL</div>
                        <pre className="overflow-auto rounded-xl bg-white p-3 text-xs leading-6">{highlightSql(message.generatedQuery.sql_query ?? message.generatedQuery.query_string)}</pre>
                      </div>
                      <div>
                        <div className="mb-1 font-semibold text-slate-900">Graph Traversal</div>
                        <pre className="overflow-auto rounded-xl bg-white p-3 text-xs leading-6 text-slate-700">{message.generatedQuery.graph_query_string ?? JSON.stringify(message.generatedQuery.structured_form, null, 2)}</pre>
                      </div>
                      <div className="text-xs leading-5 text-slate-500">{message.generatedQuery.explanation}</div>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {message.relevantNodeIds?.length ? <div className="text-xs text-slate-500">Highlighted {message.relevantNodeIds.length} related nodes.</div> : null}
            </div>
          ))}
          {isThinking ? <div className="text-sm text-sky-600">{streamingStage}<span className="ml-2 inline-block animate-pulse">...</span></div> : null}
        </div>

        <div className="border-t border-slate-200 p-5">
          <div className="mb-3 flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
            <span className="size-2 rounded-full bg-emerald-500" />
            {isThinking ? streamingStage : "Dodge AI is awaiting instructions"}
            <span className="ml-auto text-slate-400">{activeHighlightCount > 0 ? `${activeHighlightCount} focused` : "Ready"}</span>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <textarea
              className="h-28 w-full resize-none border-0 bg-transparent text-[15px] text-slate-900 outline-none placeholder:text-slate-400"
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
                if (event.key === "Escape") {
                  setInput("");
                }
              }}
              placeholder="Analyze anything"
              value={input}
            />
            <div className="mt-4 flex items-center justify-end">
              <button className="rounded-2xl bg-slate-500 px-6 py-3 text-sm font-medium text-white transition hover:bg-slate-600 disabled:opacity-60" disabled={isThinking || !input.trim()} onClick={() => void handleSend()} type="button">Send</button>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
