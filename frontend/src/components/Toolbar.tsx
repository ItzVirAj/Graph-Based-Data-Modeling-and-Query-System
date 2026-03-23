import { useState } from "react";

import { addGraphEdge, addGraphNode, exportGraphJson, resetGraph } from "../services/api";

interface ToolbarProps {
  onGraphChanged: (message: string) => void;
  onShowFullGraph: () => void;
}

type ModalMode = "node" | "edge" | null;

const inputClassName =
  "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100";

export function Toolbar({ onGraphChanged, onShowFullGraph }: ToolbarProps) {
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodeForm, setNodeForm] = useState({
    id: "",
    type: "Product",
    metadata: '{\n  "name": "Sample Node"\n}',
  });
  const [edgeForm, setEdgeForm] = useState({
    source: "",
    target: "",
    relationship: "order_to_product",
  });

  const closeModal = () => {
    setError(null);
    setModalMode(null);
  };

  const handleAddNode = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await addGraphNode({
        id: nodeForm.id,
        type: nodeForm.type,
        metadata: JSON.parse(nodeForm.metadata),
      });
      closeModal();
      onGraphChanged(`Added ${nodeForm.type} node ${nodeForm.id}.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to add node");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAddEdge = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await addGraphEdge(edgeForm);
      closeModal();
      onGraphChanged(`Added edge ${edgeForm.relationship} from ${edgeForm.source} to ${edgeForm.target}.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to add edge");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await resetGraph();
      onShowFullGraph();
      onGraphChanged("Graph reset from backend source data.");
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Unable to reset graph");
    } finally {
      setSubmitting(false);
    }
  };

  const handleExport = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const blob = await exportGraphJson();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "sap-o2c-graph.json";
      anchor.click();
      URL.revokeObjectURL(url);
      onGraphChanged("Exported graph JSON.");
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Unable to export graph");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Controls</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-950">Graph Toolbar</h2>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <button className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800" onClick={() => setModalMode("node")} type="button">Add Node</button>
        <button className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50" onClick={() => setModalMode("edge")} type="button">Add Edge</button>
        <button className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60" disabled={submitting} onClick={() => void handleReset()} type="button">Reset Graph</button>
        <button className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60" disabled={submitting} onClick={() => void handleExport()} type="button">Export JSON</button>
      </div>

      {error ? <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}

      {modalMode ? (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-900">{modalMode === "node" ? "Create Node" : "Create Edge"}</h3>
            <button className="text-sm text-slate-500 transition hover:text-slate-900" onClick={closeModal} type="button">Close</button>
          </div>

          {modalMode === "node" ? (
            <div className="space-y-3">
              <input className={inputClassName} onChange={(event) => setNodeForm((current) => ({ ...current, id: event.target.value }))} placeholder="Node ID" value={nodeForm.id} />
              <select className={inputClassName} onChange={(event) => setNodeForm((current) => ({ ...current, type: event.target.value }))} value={nodeForm.type}>
                {["Order", "Delivery", "Invoice", "Payment", "Customer", "Product", "Address"].map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
              <textarea className={`${inputClassName} min-h-32`} onChange={(event) => setNodeForm((current) => ({ ...current, metadata: event.target.value }))} value={nodeForm.metadata} />
              <button className="w-full rounded-xl bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-60" disabled={submitting || !nodeForm.id.trim()} onClick={() => void handleAddNode()} type="button">{submitting ? "Saving..." : "Create Node"}</button>
            </div>
          ) : (
            <div className="space-y-3">
              <input className={inputClassName} onChange={(event) => setEdgeForm((current) => ({ ...current, source: event.target.value }))} placeholder="Source ID" value={edgeForm.source} />
              <input className={inputClassName} onChange={(event) => setEdgeForm((current) => ({ ...current, target: event.target.value }))} placeholder="Target ID" value={edgeForm.target} />
              <select className={inputClassName} onChange={(event) => setEdgeForm((current) => ({ ...current, relationship: event.target.value }))} value={edgeForm.relationship}>
                {["order_to_delivery", "delivery_to_invoice", "invoice_to_payment", "order_to_customer", "order_to_product", "customer_to_address"].map((relationship) => (
                  <option key={relationship} value={relationship}>{relationship}</option>
                ))}
              </select>
              <button className="w-full rounded-xl bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-60" disabled={submitting || !edgeForm.source.trim() || !edgeForm.target.trim()} onClick={() => void handleAddEdge()} type="button">{submitting ? "Saving..." : "Create Edge"}</button>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
