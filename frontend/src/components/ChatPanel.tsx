import { useEffect, useMemo, useState } from "react";

import { queryGraph } from "../services/api";
import type { ChatMessage } from "../types/api";

interface ChatPanelProps {
  highlightedNodes: string[];
  onHighlightNodes: (nodeIds: string[]) => void;
}

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function ChatPanel({ highlightedNodes, onHighlightNodes }: ChatPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: createMessageId(),
      role: "assistant",
      text: "Ask about order flows, invoices, payments, customers, products, or addresses to explore the graph with natural language.",
    },
  ]);
  const [isThinking, setIsThinking] = useState(false);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsCollapsed(true);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const activeHighlightCount = useMemo(() => highlightedNodes.length, [highlightedNodes.length]);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || isThinking) {
      return;
    }

    const userMessage: ChatMessage = {
      id: createMessageId(),
      role: "user",
      text: question,
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsThinking(true);

    try {
      const response = await queryGraph(question);
      const rejected = response.answer.includes("designed to answer questions related to the dataset only");
      const assistantMessage: ChatMessage = {
        id: createMessageId(),
        role: "assistant",
        text: response.answer,
        relevantNodeIds: response.relevant_node_ids,
        rawData: response.raw_data,
        rejected,
      };
      setMessages((current) => [...current, assistantMessage]);
      onHighlightNodes(response.relevant_node_ids ?? []);
    } catch (error) {
      const message: ChatMessage = {
        id: createMessageId(),
        role: "assistant",
        text: error instanceof Error ? error.message : "Query failed. Please try again.",
      };
      setMessages((current) => [...current, message]);
      onHighlightNodes([]);
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <aside
      className={`border-t border-slate-800 bg-slate-900/95 backdrop-blur lg:border-l lg:border-t-0 ${
        isCollapsed ? "w-full lg:w-[88px]" : "w-full lg:w-[430px]"
      } transition-all duration-300`}
    >
      <div className="flex h-full min-h-[360px] flex-col">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-4">
          {!isCollapsed ? (
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-cyan-400">Query Copilot</p>
              <h2 className="mt-1 text-lg font-semibold text-white">Natural Language Chat</h2>
            </div>
          ) : (
            <div className="text-xs uppercase tracking-[0.28em] text-cyan-400 [writing-mode:vertical-rl]">
              Chat
            </div>
          )}
          <button
            className="rounded-xl border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white"
            onClick={() => setIsCollapsed((current) => !current)}
            type="button"
          >
            {isCollapsed ? "Open" : "Collapse"}
          </button>
        </div>

        {!isCollapsed ? (
          <>
            <div className="border-b border-slate-800 px-4 py-3 text-xs text-slate-400">
              {activeHighlightCount > 0
                ? `${activeHighlightCount} graph node(s) highlighted from the latest answer.`
                : "No active graph highlights."}
            </div>

            <div className="flex-1 space-y-4 overflow-auto px-4 py-4 scrollbar-thin">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    message.role === "user"
                      ? "ml-auto bg-cyan-500 text-slate-950"
                      : message.rejected
                        ? "bg-amber-500/15 text-amber-100 ring-1 ring-amber-400/30"
                        : "bg-slate-800 text-slate-100"
                  }`}
                >
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.22em] opacity-70">
                    {message.role === "user" ? "You" : "Assistant"}
                  </div>
                  <div>{message.text}</div>
                  {message.relevantNodeIds && message.relevantNodeIds.length > 0 ? (
                    <div className="mt-3 rounded-xl bg-slate-950/30 px-3 py-2 text-xs text-slate-200">
                      Highlighted nodes: {message.relevantNodeIds.slice(0, 8).join(", ")}
                      {message.relevantNodeIds.length > 8 ? " ..." : ""}
                    </div>
                  ) : null}
                </div>
              ))}
              {isThinking ? (
                <div className="max-w-[92%] rounded-2xl bg-slate-800 px-4 py-3 text-sm text-slate-300">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.22em] opacity-70">
                    Assistant
                  </div>
                  Thinking through the graph...
                </div>
              ) : null}
            </div>

            <div className="border-t border-slate-800 p-4">
              <div className="rounded-2xl border border-slate-700 bg-slate-950/80 p-3 shadow-lg shadow-slate-950/30">
                <textarea
                  className="min-h-28 w-full resize-none border-0 bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void handleSend();
                    }
                    if (event.key === "Escape") {
                      setIsCollapsed(true);
                    }
                  }}
                  placeholder="Ask which invoices connect to a payment, trace a billing flow, or find orders for a customer..."
                  value={input}
                />
                <div className="mt-3 flex items-center justify-between gap-4">
                  <p className="text-xs text-slate-500">Press Enter to send, Shift+Enter for newline.</p>
                  <button
                    className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-60"
                    disabled={isThinking || !input.trim()}
                    onClick={() => void handleSend()}
                    type="button"
                  >
                    Send
                  </button>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center px-3 text-center text-xs text-slate-500">
            Natural language query panel. Press Escape to close.
          </div>
        )}
      </div>
    </aside>
  );
}
