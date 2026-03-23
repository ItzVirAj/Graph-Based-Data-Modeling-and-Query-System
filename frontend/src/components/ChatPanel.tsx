import { useEffect, useMemo, useState } from "react";

import { queryGraph } from "../services/api";
import type { ChatMessage } from "../types/api";

interface ChatPanelProps {
  highlightedNodes: string[];
  onFocusNode: (nodeId: string | null) => void;
  onHighlightNodes: (nodeIds: string[]) => void;
}

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function pickPrimaryNodeId(question: string, rawData: unknown, relevantNodeIds: string[] | undefined): string | null {
  const normalizedRelevant = (relevantNodeIds ?? []).filter(Boolean);
  const idsInQuestion: string[] = question.match(/[A-Za-z]?\d{6,10}/g) ?? [];

  for (const candidate of idsInQuestion) {
    const exactMatch = normalizedRelevant.find((value) => value === candidate || value.endsWith(`:${candidate}`));
    if (exactMatch) {
      return exactMatch;
    }
  }

  const records =
    rawData && typeof rawData === "object" && "records" in rawData && Array.isArray((rawData as { records?: unknown[] }).records)
      ? (rawData as { records: unknown[] }).records
      : [];

  const firstRecord = records[0];
  if (firstRecord && typeof firstRecord === "object") {
    const candidate = firstRecord as Record<string, unknown>;
    if (typeof candidate.entity_id === "string") {
      return candidate.entity_id;
    }
    if (typeof candidate.node_id === "string") {
      return candidate.node_id;
    }
    if (Array.isArray(candidate.chain) && candidate.chain.length > 0) {
      const matchingChainNode = candidate.chain.find((item) => {
        if (!item || typeof item !== "object") {
          return false;
        }
        const chainCandidate = item as Record<string, unknown>;
        const entityId = chainCandidate.entity_id;
        return typeof entityId === "string" && idsInQuestion.includes(entityId);
      });
      if (matchingChainNode && typeof matchingChainNode === "object") {
        const chainCandidate = matchingChainNode as Record<string, unknown>;
        if (typeof chainCandidate.entity_id === "string") {
          return chainCandidate.entity_id;
        }
        if (typeof chainCandidate.node_id === "string") {
          return chainCandidate.node_id;
        }
      }
      const firstChainNode = candidate.chain[0];
      if (firstChainNode && typeof firstChainNode === "object") {
        const chainCandidate = firstChainNode as Record<string, unknown>;
        if (typeof chainCandidate.entity_id === "string") {
          return chainCandidate.entity_id;
        }
        if (typeof chainCandidate.node_id === "string") {
          return chainCandidate.node_id;
        }
      }
    }
  }

  return normalizedRelevant[0] ?? null;
}

export function ChatPanel({ highlightedNodes, onFocusNode, onHighlightNodes }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: createMessageId(),
      role: "assistant",
      text: "Hi! I can help you analyze the Order to Cash process.",
    },
  ]);
  const [isThinking, setIsThinking] = useState(false);

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

      const primaryNodeId = pickPrimaryNodeId(question, response.raw_data, response.relevant_node_ids);
      onFocusNode(primaryNodeId);
      onHighlightNodes(primaryNodeId ? [primaryNodeId] : []);
    } catch (error) {
      const message: ChatMessage = {
        id: createMessageId(),
        role: "assistant",
        text: error instanceof Error ? error.message : "Query failed. Please try again.",
      };
      setMessages((current) => [...current, message]);
      onFocusNode(null);
      onHighlightNodes([]);
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <aside className="ml-4 flex w-[430px] shrink-0 overflow-hidden rounded-[22px] border border-slate-200 bg-white shadow-sm">
      <div className="flex h-full min-h-0 w-full flex-col">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-[18px] font-semibold text-slate-950">Chat with Graph</h2>
          <p className="mt-1 text-sm text-slate-500">Order to Cash</p>
        </div>

        <div className="border-b border-slate-100 px-5 py-5">
          <div className="flex items-start gap-4">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-slate-950 text-lg font-semibold text-white">
              D
            </div>
            <div>
              <h3 className="text-[18px] font-semibold text-slate-950">Dodge AI</h3>
              <p className="text-sm text-slate-500">Graph Agent</p>
            </div>
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-auto px-5 py-5">
          {messages.map((message) => (
            <div key={message.id} className="space-y-2">
              <div className={`text-[15px] leading-8 ${message.rejected ? "text-amber-700" : "text-slate-900"}`}>
                {message.text}
              </div>
              {message.relevantNodeIds && message.relevantNodeIds.length > 0 ? (
                <div className="text-xs text-slate-500">
                  Focused graph on the matched result node.
                </div>
              ) : null}
            </div>
          ))}
          {isThinking ? <div className="text-[15px] text-slate-500">Thinking through the graph...</div> : null}
        </div>

        <div className="border-t border-slate-200 p-5">
          <div className="mb-3 flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
            <span className="size-2 rounded-full bg-emerald-500" />
            Dodge AI is awaiting instructions
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
              <button
                className="rounded-2xl bg-slate-500 px-6 py-3 text-sm font-medium text-white transition hover:bg-slate-600 disabled:opacity-60"
                disabled={isThinking || !input.trim()}
                onClick={() => void handleSend()}
                type="button"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}


