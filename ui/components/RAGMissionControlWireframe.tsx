import React, { useState } from 'react';
import {
  Terminal,
  Search,
  Sliders,
  Cpu,
  Bell,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  FolderGit2,
  FileText,
  Network,
  Activity,
  Radio,
  Settings,
  Plus,
  Upload,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ThumbsUp,
  ThumbsDown,
  Bookmark,
  Share2,
  RotateCw,
  Maximize2,
  ZoomIn,
  ZoomOut,
  Layers,
  Sparkles,
  Database,
  Server,
  Zap,
  Check,
  Download,
  Filter,
  ArrowRight,
  ExternalLink,
} from 'lucide-react';

// ==========================================
// TYPES & INTERFACES (Contracts Compliant)
// ==========================================
export type RetrievalMode = 'auto' | 'agentic' | 'graph' | 'direct';
export type ActiveTab = 'mission' | 'documents' | 'graph' | 'observability' | 'ragops' | 'settings';
export type CRAGStatus = 'CONFIDENT' | 'AMBIGUOUS' | 'REFUSE';

interface DocumentSource {
  id: string;
  name: string;
  chunks: number;
  indexed: number;
  status: 'indexed' | 'processing' | 'failed';
  ocrActive: boolean;
  fileSize: string;
}

interface CitationBadge {
  id: string;
  docName: string;
  page: number;
  index: number;
  bbox: [number, number, number, number];
  similarity: number;
  crossEncoderScore: number;
  snippet: string;
}

export default function RAGMissionControlWireframe() {
  // Navigation & Tab State
  const [activeTab, setActiveTab] = useState<ActiveTab>('mission');
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('llama3.2:3b');
  const [timeWindow, setTimeWindow] = useState<'1h' | '24h' | '7d'>('1h');

  // Inspector & Chat State
  const [inspectorOpen, setInspectorOpen] = useState<boolean>(true);
  const [activeCitation, setActiveCitation] = useState<CitationBadge>({
    id: 'cite_1',
    docName: 'doc_sec_10k_nvda.pdf',
    page: 14,
    index: 2,
    bbox: [0.14, 0.32, 0.85, 0.48],
    similarity: 0.892,
    crossEncoderScore: 0.961,
    snippet:
      'Datacenter compute revenue grew 217% year-over-year to $47.5 billion, propelled by massive hyperscale cloud demand for NVIDIA HGX platforms based on Hopper architecture GPUs (H100/H200). Non-GAAP Gross margin reached 73.8% across the trailing 12 months.',
  });
  const [reasoningOpen, setReasoningOpen] = useState<boolean>(true);
  const [feedbackGiven, setFeedbackGiven] = useState<'up' | 'down' | null>('up');
  const [inputQuery, setInputQuery] = useState<string>(
    "Synthesize NVIDIA's FY24 Datacenter gross margin trajectory and verify against raw Form 10-K cash flow statements."
  );

  // Scoped Document Corpus
  const [sources] = useState<DocumentSource[]>([
    {
      id: 'doc_1',
      name: 'doc_sec_10k_nvda.pdf',
      chunks: 142,
      indexed: 100,
      status: 'indexed',
      ocrActive: true,
      fileSize: '4.8 MB',
    },
    {
      id: 'doc_2',
      name: 'financial_table_fy24.pdf',
      chunks: 38,
      indexed: 100,
      status: 'indexed',
      ocrActive: true,
      fileSize: '1.2 MB',
    },
    {
      id: 'doc_3',
      name: 'transformer_rag_arch.pdf',
      chunks: 84,
      indexed: 100,
      status: 'indexed',
      ocrActive: false,
      fileSize: '2.9 MB',
    },
    {
      id: 'doc_4',
      name: 'earnings_call_transcript.pdf',
      chunks: 56,
      indexed: 100,
      status: 'indexed',
      ocrActive: false,
      fileSize: '820 KB',
    },
  ]);

  return (
    <div className="flex h-screen w-screen flex-col bg-[#09090b] text-[#f4f4f5] antialiased font-sans select-none overflow-hidden">
      {/* ========================================================= */}
      {/* 1. TOP GLOBAL APP BAR                                     */}
      {/* ========================================================= */}
      <header className="flex h-12 w-full shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#0c0d10] px-4">
        {/* Brand & Workspace Breadcrumb */}
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.25)]">
            <Terminal className="h-4 w-4" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold tracking-tight text-white">RAG Mission Control</span>
            <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
              v2.4-craft
            </span>
          </div>
          <span className="text-zinc-600">/</span>
          <div className="flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-zinc-900/60 px-2.5 py-1 text-xs">
            <FolderGit2 className="h-3.5 w-3.5 text-emerald-400" />
            <span className="font-medium text-zinc-200">Financial Compliance & SEC-10K</span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10b981]" />
          </div>
        </div>

        {/* Global Navigation Tabs */}
        <nav className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab('mission')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
              activeTab === 'mission'
                ? 'bg-zinc-800 text-white border border-white/10 shadow-sm'
                : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
            }`}
          >
            <Radio className="h-3.5 w-3.5 text-emerald-400" />
            Mission Cockpit
          </button>
          <button
            onClick={() => setActiveTab('observability')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
              activeTab === 'observability'
                ? 'bg-zinc-800 text-white border border-white/10 shadow-sm'
                : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
            }`}
          >
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
            Observability & Telemetry
          </button>
          <button
            onClick={() => setActiveTab('graph')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
              activeTab === 'graph'
                ? 'bg-zinc-800 text-white border border-white/10 shadow-sm'
                : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
            }`}
          >
            <Network className="h-3.5 w-3.5 text-amber-400" />
            Knowledge Graph
          </button>
          <button
            onClick={() => setActiveTab('documents')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
              activeTab === 'documents'
                ? 'bg-zinc-800 text-white border border-white/10 shadow-sm'
                : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
            }`}
          >
            <FileText className="h-3.5 w-3.5 text-zinc-400" />
            Corpus Library
          </button>
        </nav>

        {/* Distributed Heartbeat Indicators */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-md border border-white/[0.08] bg-zinc-900/80 px-2.5 py-1 font-mono text-[11px]">
            <div className="flex items-center gap-1 text-emerald-400">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              <span>GW:8000 (14ms)</span>
            </div>
            <span className="text-zinc-600">|</span>
            <span className="text-zinc-300">Qdrant: 12.4k vec</span>
            <span className="text-zinc-600">|</span>
            <span className="text-zinc-300">Redis: 99.4% hit</span>
          </div>

          <button
            onClick={() => setInspectorOpen(!inspectorOpen)}
            className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors ${
              inspectorOpen
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                : 'border-white/10 bg-zinc-900 text-zinc-400 hover:bg-zinc-800'
            }`}
            title="Toggle Visual Provenance Inspector"
          >
            <Layers className="h-3.5 w-3.5" />
            <span>Inspector</span>
          </button>
        </div>
      </header>

      {/* ========================================================= */}
      {/* 2. 3-PANE WORKSPACE                                       */}
      {/* ========================================================= */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* --------------------------------------------------------- */}
        {/* PANE A: LEFT NAVIGATION & CORPUS RAIL (260px)             */}
        {/* --------------------------------------------------------- */}
        <aside className="flex w-64 shrink-0 flex-col border-r border-white/[0.08] bg-[#0c0d10] select-none">
          {/* Active Workspace Card */}
          <div className="p-3 border-b border-white/[0.08]">
            <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-wider text-zinc-400">
              <span>Scoped Corpus</span>
              <span className="rounded bg-zinc-800 px-1.5 py-0.2 text-[10px] text-zinc-300">4 docs</span>
            </div>
          </div>

          {/* Document Ingestion & Corpus List */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {sources.map((doc) => (
              <div
                key={doc.id}
                onClick={() => {
                  if (doc.id === 'doc_1') {
                    setActiveCitation((prev) => ({
                      ...prev,
                      docName: doc.name,
                      page: 14,
                      index: 2,
                    }));
                    setInspectorOpen(true);
                  }
                }}
                className={`group flex flex-col gap-1 rounded-md p-2 text-xs transition-all cursor-pointer border ${
                  activeCitation.docName === doc.name
                    ? 'border-emerald-500/40 bg-emerald-950/20 text-emerald-100 shadow-[0_0_10px_rgba(16,185,129,0.1)]'
                    : 'border-transparent hover:border-white/10 hover:bg-zinc-900 text-zinc-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 truncate">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-zinc-400 group-hover:text-emerald-400" />
                    <span className="truncate font-medium">{doc.name}</span>
                  </div>
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
                  <span>{doc.chunks} chunks</span>
                  {doc.ocrActive && (
                    <span className="rounded bg-cyan-950/60 border border-cyan-800/40 px-1 text-cyan-400">
                      OCR v2.4
                    </span>
                  )}
                  <span>{doc.fileSize}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Quick PDF Upload Dropzone */}
          <div className="p-3 border-t border-white/[0.08] bg-zinc-950/40">
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-zinc-700/80 bg-zinc-900/40 p-3 text-center transition-all hover:border-emerald-500/50 hover:bg-emerald-950/10 cursor-pointer">
              <Upload className="h-4 w-4 text-zinc-400 group-hover:text-emerald-400 mb-1" />
              <span className="text-[11px] font-medium text-zinc-300">Drop PDF or DOCX</span>
              <span className="text-[9px] font-mono text-zinc-500 mt-0.5">Auto-chunking & vector index</span>
            </div>
          </div>
        </aside>

        {/* --------------------------------------------------------- */}
        {/* PANE B: MAIN CONTENT (SWITCHABLE COCKPIT / OBSERVABILITY) */}
        {/* --------------------------------------------------------- */}
        <main className="flex flex-1 flex-col overflow-hidden bg-[#09090b]">
          {activeTab === 'mission' && (
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Cockpit Sub-Header & Controls */}
              <div className="flex h-11 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#0c0d10] px-6">
                {/* Retrieval Mode Pills */}
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-mono text-zinc-500 mr-1 uppercase tracking-wide">Mode:</span>
                  {(['auto', 'agentic', 'graph', 'direct'] as RetrievalMode[]).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setRetrievalMode(mode)}
                      className={`rounded px-2.5 py-1 text-xs font-mono transition-all ${
                        retrievalMode === mode
                          ? 'border border-emerald-500/50 bg-emerald-500/15 text-emerald-300 font-semibold shadow-[0_0_8px_rgba(16,185,129,0.2)]'
                          : 'border border-white/5 bg-zinc-900/60 text-zinc-400 hover:bg-zinc-800'
                      }`}
                    >
                      {mode === 'auto' && 'Auto CRAG'}
                      {mode === 'agentic' && 'Agentic Multi-Hop'}
                      {mode === 'graph' && 'GraphRAG'}
                      {mode === 'direct' && 'Direct RRF'}
                    </button>
                  ))}
                </div>

                {/* Session Actions & Model Telemetry */}
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1 text-[11px] font-mono text-zinc-400">
                    <span>Model:</span>
                    <select
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                      className="rounded border border-white/10 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                    >
                      <option value="llama3.2:3b">llama3.2:3b (2.2GB VRAM)</option>
                      <option value="deepseek-r1:8b">deepseek-r1:8b (5.4GB VRAM)</option>
                      <option value="qwen2.5:7b">qwen2.5:7b (4.8GB VRAM)</option>
                    </select>
                  </div>
                  <button className="flex items-center gap-1 rounded border border-white/10 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">
                    <Share2 className="h-3 w-3" />
                    Share Trace
                  </button>
                </div>
              </div>

              {/* Chat Thread Area */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* 1. User Message */}
                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-lg border border-white/[0.08] bg-[#141518] p-4 text-sm text-zinc-100 shadow-sm">
                    <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 mb-2">
                      <span>Investigative Analyst</span>
                      <span>10:42:15 AM</span>
                    </div>
                    <p className="leading-relaxed">
                      Synthesize NVIDIA's FY24 Datacenter gross margin trajectory and verify against raw Form 10-K cash
                      flow statements.
                    </p>
                  </div>
                </div>

                {/* 2. Agent Reasoning & CRAG Self-Correction Stream */}
                <div className="rounded-lg border border-white/[0.08] bg-[#101114] overflow-hidden">
                  <div
                    onClick={() => setReasoningOpen(!reasoningOpen)}
                    className="flex items-center justify-between bg-zinc-900/60 px-4 py-2.5 cursor-pointer hover:bg-zinc-900 transition-colors border-b border-white/[0.04]"
                  >
                    <div className="flex items-center gap-2">
                      {reasoningOpen ? (
                        <ChevronDown className="h-4 w-4 text-zinc-400" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-zinc-400" />
                      )}
                      <span className="text-xs font-mono font-medium text-zinc-200">
                        CRAG Multi-Hop Decomposition Trace
                      </span>
                      <span className="rounded bg-zinc-800 px-1.5 py-0.2 font-mono text-[10px] text-zinc-400">
                        4 steps · 104ms
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-400">
                        <Check className="h-3 w-3" /> CONFIDENT 0.94
                      </span>
                    </div>
                  </div>

                  {reasoningOpen && (
                    <div className="p-4 font-mono text-xs space-y-3 bg-[#0c0d10]/60">
                      {/* Sub-queries */}
                      <div>
                        <div className="text-[10px] uppercase text-zinc-500 tracking-wider mb-1">
                          Sub-Query Execution Plan:
                        </div>
                        <div className="space-y-1 text-zinc-300">
                          <div className="flex items-center gap-2">
                            <span className="text-emerald-400">→ [Hop 1]</span>
                            <span>NVDA FY24 Datacenter segment revenue & margin schedule</span>
                            <span className="text-zinc-500 text-[10px]">(Dense: 0.942, BM25: 18.4)</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-emerald-400">→ [Hop 2]</span>
                            <span>Reconcile operating cash flow against consolidated GAAP net income</span>
                            <span className="text-zinc-500 text-[10px]">(Dense: 0.915, BM25: 14.2)</span>
                          </div>
                        </div>
                      </div>

                      {/* Execution Terminal Steps */}
                      <div className="rounded border border-white/5 bg-black/40 p-2.5 text-[11px] text-zinc-400 space-y-1">
                        <div>
                          [00:00.018] <span className="text-cyan-400">BM25 Sparse Search:</span> retrieved 40 candidate
                          chunks from Qdrant sparse index
                        </div>
                        <div>
                          [00:00.034] <span className="text-emerald-400">Qdrant HNSW Dense:</span> retrieved 40 cosine
                          candidates (384-dim e5-small)
                        </div>
                        <div>
                          [00:00.052] <span className="text-amber-400">FlashRank Cross-Encoder:</span> re-ranked 80 → 6
                          chunks (Min score: 0.884, Max: 0.961)
                        </div>
                        <div>
                          [00:00.098] <span className="text-emerald-400">CRAG Evaluator Gate:</span> PASSED
                          (Hallucination risk: 0.018, Ambiguity: 0.04)
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* 3. Assistant Multimodal Response */}
                <div className="rounded-lg border border-white/[0.08] bg-[#101114] p-5 text-sm space-y-4 shadow-sm">
                  <div className="flex items-center justify-between border-b border-white/[0.04] pb-2 text-[11px] font-mono text-zinc-500">
                    <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
                      <Sparkles className="h-3.5 w-3.5" />
                      Grounded Multimodal Synthesis
                    </span>
                    <span>Llama-3.2:3b · 308ms generation</span>
                  </div>

                  <p className="leading-relaxed text-zinc-200">
                    For fiscal year 2024, NVIDIA recorded unprecedented acceleration across its Compute & Networking
                    architecture. Datacenter segment revenue reached{' '}
                    <strong className="text-white">$47,525 million</strong>, marking a <strong>217% YoY increase</strong>{' '}
                    driven by surging hyper-scaler deployments of HGX Hopper GPUs{' '}
                    <button
                      onClick={() => setInspectorOpen(true)}
                      className="inline-flex items-center gap-1 rounded bg-zinc-800/80 border border-emerald-500/40 px-1.5 py-0.2 font-mono text-[10px] text-emerald-300 hover:bg-zinc-700 transition"
                    >
                      [doc_sec_10k_nvda.pdf p.14 #2]
                    </button>
                    . Consolidated GAAP gross margins expanded 1,580 basis points to <strong>72.7%</strong>, while
                    operating cash flows quadrupled to $28,090 million.
                  </p>

                  {/* Financial Reconciliation Table */}
                  <div className="overflow-x-auto rounded border border-white/[0.08] bg-black/20">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="border-b border-white/[0.08] bg-zinc-900/60 text-zinc-400 text-[11px]">
                        <tr>
                          <th className="p-2.5">Financial Metric (GAAP)</th>
                          <th className="p-2.5 text-right">FY2023</th>
                          <th className="p-2.5 text-right">FY2024 (Reported)</th>
                          <th className="p-2.5 text-right text-emerald-400">YoY Change</th>
                          <th className="p-2.5 text-center">Visual Grounding</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.04] text-zinc-300">
                        <tr className="hover:bg-zinc-800/30">
                          <td className="p-2.5 font-sans font-medium text-white">Datacenter Revenue</td>
                          <td className="p-2.5 text-right">$15,005 M</td>
                          <td className="p-2.5 text-right font-bold text-white">$47,525 M</td>
                          <td className="p-2.5 text-right text-emerald-400 font-semibold">+216.7%</td>
                          <td className="p-2.5 text-center">
                            <span className="cursor-pointer text-emerald-400 hover:underline">
                              [Item 8, p.14]
                            </span>
                          </td>
                        </tr>
                        <tr className="hover:bg-zinc-800/30">
                          <td className="p-2.5 font-sans font-medium text-white">Gross Margin (%)</td>
                          <td className="p-2.5 text-right">56.9%</td>
                          <td className="p-2.5 text-right font-bold text-white">72.7%</td>
                          <td className="p-2.5 text-right text-emerald-400 font-semibold">+1,580 bps</td>
                          <td className="p-2.5 text-center">
                            <span className="cursor-pointer text-emerald-400 hover:underline">
                              [Item 8, p.16]
                            </span>
                          </td>
                        </tr>
                        <tr className="hover:bg-zinc-800/30">
                          <td className="p-2.5 font-sans font-medium text-white">Operating Cash Flow</td>
                          <td className="p-2.5 text-right">$5,641 M</td>
                          <td className="p-2.5 text-right font-bold text-white">$28,090 M</td>
                          <td className="p-2.5 text-right text-emerald-400 font-semibold">+397.9%</td>
                          <td className="p-2.5 text-center">
                            <span className="cursor-pointer text-emerald-400 hover:underline">
                              [Item 8, p.62]
                            </span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  {/* Figure Preview Card (Multimodal Evidence) */}
                  <div className="flex items-center gap-3 rounded-lg border border-white/[0.08] bg-[#0c0d10] p-3">
                    <div className="flex h-16 w-24 shrink-0 items-center justify-center rounded border border-white/10 bg-zinc-900 font-mono text-[10px] text-zinc-500">
                      [PDF Crop Preview]
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-zinc-200">
                          Figure 4.2: Consolidated Statements of Income (Item 8)
                        </span>
                        <span className="font-mono text-[10px] text-emerald-400">[BBox: 124, 310, 420, 65]</span>
                      </div>
                      <p className="text-[11px] text-zinc-400 font-mono">
                        OCR confidence: 99.1% · Extracted table matches Qdrant dense vector #2847
                      </p>
                    </div>
                  </div>

                  {/* 4. Active Learning RAGOps Feedback Bar */}
                  <div className="flex items-center justify-between border-t border-white/[0.04] pt-3 text-xs font-mono text-zinc-400">
                    <div className="flex items-center gap-2">
                      <span>Telemetry:</span>
                      <span className="text-zinc-200">412ms total</span>
                      <span className="text-zinc-600">(18ms BM25 · 34ms Qdrant · 52ms Rerank · 308ms LLM)</span>
                      <span className="text-zinc-600">|</span>
                      <span>1,420 tokens</span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-zinc-500">Active Learning (RAGOps):</span>
                      <button
                        onClick={() => setFeedbackGiven('up')}
                        className={`flex items-center gap-1 rounded px-2 py-1 transition ${
                          feedbackGiven === 'up'
                            ? 'border border-emerald-500/40 bg-emerald-500/20 text-emerald-300'
                            : 'border border-white/5 bg-zinc-900 hover:bg-zinc-800'
                        }`}
                        title="Helpful (Persist ground-truth triplet)"
                      >
                        <ThumbsUp className="h-3 w-3" />
                        <span className="text-[10px]">Helpful</span>
                      </button>
                      <button
                        onClick={() => setFeedbackGiven('down')}
                        className={`flex items-center gap-1 rounded px-2 py-1 transition ${
                          feedbackGiven === 'down'
                            ? 'border border-amber-500/40 bg-amber-500/20 text-amber-300'
                            : 'border border-white/5 bg-zinc-900 hover:bg-zinc-800'
                        }`}
                        title="Inaccurate (Auto-mine hard-negative triplet)"
                      >
                        <ThumbsDown className="h-3 w-3" />
                        <span className="text-[10px]">Inaccurate</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Floating Bottom Command Input Dock */}
              <div className="p-4 border-t border-white/[0.08] bg-[#0c0d10]">
                <div className="flex flex-col rounded-lg border border-white/10 bg-[#121316] shadow-lg focus-within:border-emerald-500/60 focus-within:ring-1 focus-within:ring-emerald-500/30 transition-all">
                  <div className="flex items-center justify-between border-b border-white/[0.04] px-3 py-1.5 text-[11px] font-mono text-zinc-400">
                    <span className="flex items-center gap-1.5 text-emerald-400">
                      <Radio className="h-3 w-3" /> Mode: {retrievalMode.toUpperCase()} CRAG
                    </span>
                    <span>Press Enter to run query · Shift + Enter for newline</span>
                  </div>

                  <textarea
                    rows={2}
                    value={inputQuery}
                    onChange={(e) => setInputQuery(e.target.value)}
                    placeholder="Ask questions across scoped documents or type / to invoke multi-hop sub-agents..."
                    className="w-full resize-none bg-transparent px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none"
                  />

                  <div className="flex items-center justify-between border-t border-white/[0.04] px-3 py-2">
                    <div className="flex items-center gap-2">
                      <button className="flex items-center gap-1 rounded border border-white/10 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">
                        <Upload className="h-3 w-3" /> Attach Evidence
                      </button>
                      <button className="flex items-center gap-1 rounded border border-white/10 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">
                        <Database className="h-3 w-3" /> Scope: 4 Docs
                      </button>
                    </div>

                    <button className="flex items-center gap-1.5 rounded-md bg-emerald-500 px-3.5 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.3)] transition-all">
                      <span>Execute Query</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* OBSERVABILITY TAB */}
          {activeTab === 'observability' && (
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Header */}
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold tracking-tight text-white">Observability & RAGOps Telemetry</h2>
                  <p className="text-xs text-zinc-400 font-mono mt-0.5">
                    Real-time hardware footprint, latency percentiles, and contrastive hard-negative mining loop
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {(['1h', '24h', '7d'] as const).map((win) => (
                    <button
                      key={win}
                      onClick={() => setTimeWindow(win)}
                      className={`rounded px-2.5 py-1 text-xs font-mono ${
                        timeWindow === win
                          ? 'border border-cyan-500/50 bg-cyan-500/20 text-cyan-300 font-semibold'
                          : 'border border-white/5 bg-zinc-900 text-zinc-400'
                      }`}
                    >
                      Last {win}
                    </button>
                  ))}
                  <button className="flex items-center gap-1.5 rounded bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400">
                    <Download className="h-3.5 w-3.5" /> Export Hard-Negatives (248)
                  </button>
                </div>
              </div>

              {/* Latency Percentile Cards */}
              <div className="grid grid-cols-4 gap-4">
                <div className="rounded-lg border border-white/[0.08] bg-[#121316] p-4 space-y-1">
                  <div className="text-[11px] font-mono text-zinc-400 uppercase">p50 Latency</div>
                  <div className="text-2xl font-mono font-bold text-white">184 ms</div>
                  <div className="text-[11px] font-mono text-emerald-400">-12ms vs yesterday</div>
                </div>
                <div className="rounded-lg border border-white/[0.08] bg-[#121316] p-4 space-y-1">
                  <div className="text-[11px] font-mono text-zinc-400 uppercase">p95 Latency</div>
                  <div className="text-2xl font-mono font-bold text-white">412 ms</div>
                  <div className="text-[11px] font-mono text-emerald-400">-28ms vs yesterday</div>
                </div>
                <div className="rounded-lg border border-white/[0.08] bg-[#121316] p-4 space-y-1">
                  <div className="text-[11px] font-mono text-zinc-400 uppercase">p99 Latency</div>
                  <div className="text-2xl font-mono font-bold text-amber-400">680 ms</div>
                  <div className="text-[11px] font-mono text-amber-400">+4ms (LLM queue spike)</div>
                </div>
                <div className="rounded-lg border border-white/[0.08] bg-[#121316] p-4 space-y-1">
                  <div className="text-[11px] font-mono text-zinc-400 uppercase">CRAG Confident Rate</div>
                  <div className="text-2xl font-mono font-bold text-emerald-400">86.4%</div>
                  <div className="text-[11px] font-mono text-zinc-400">11.2% Ambiguous · 2.4% Refuse</div>
                </div>
              </div>

              {/* Retrieval Waterfall Breakdown */}
              <div className="rounded-lg border border-white/[0.08] bg-[#121316] p-5 space-y-3">
                <div className="text-xs font-semibold text-white">End-to-End Latency Waterfall Breakdown</div>
                <div className="space-y-2 font-mono text-xs">
                  <div className="flex items-center justify-between text-zinc-300">
                    <span>1. BM25 Sparse Inverted Index Search</span>
                    <span className="text-cyan-400 font-bold">18 ms (4.3%)</span>
                  </div>
                  <div className="w-full bg-zinc-900 rounded-full h-1.5">
                    <div className="bg-cyan-400 h-1.5 rounded-full" style={{ width: '4.3%' }} />
                  </div>

                  <div className="flex items-center justify-between text-zinc-300">
                    <span>2. Qdrant HNSW Dense Cosine Search</span>
                    <span className="text-emerald-400 font-bold">34 ms (8.2%)</span>
                  </div>
                  <div className="w-full bg-zinc-900 rounded-full h-1.5">
                    <div className="bg-emerald-400 h-1.5 rounded-full" style={{ width: '8.2%' }} />
                  </div>

                  <div className="flex items-center justify-between text-zinc-300">
                    <span>3. FlashRank Cross-Encoder Re-Ranking</span>
                    <span className="text-amber-400 font-bold">52 ms (12.6%)</span>
                  </div>
                  <div className="w-full bg-zinc-900 rounded-full h-1.5">
                    <div className="bg-amber-400 h-1.5 rounded-full" style={{ width: '12.6%' }} />
                  </div>

                  <div className="flex items-center justify-between text-zinc-300">
                    <span>4. Llama-3.2:3b Auto-Regressive Token Generation</span>
                    <span className="text-purple-400 font-bold">308 ms (74.8%)</span>
                  </div>
                  <div className="w-full bg-zinc-900 rounded-full h-1.5">
                    <div className="bg-purple-400 h-1.5 rounded-full" style={{ width: '74.8%' }} />
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>

        {/* --------------------------------------------------------- */}
        {/* PANE C: RIGHT CONTEXTUAL PROVENANCE INSPECTOR (360px)     */}
        {/* --------------------------------------------------------- */}
        {inspectorOpen && (
          <aside className="w-96 shrink-0 border-l border-white/[0.08] bg-[#0c0d10] flex flex-col select-none overflow-hidden">
            {/* Header */}
            <div className="flex h-11 shrink-0 items-center justify-between border-b border-white/[0.08] px-4 bg-zinc-900/40">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-emerald-400" />
                <span className="text-xs font-semibold tracking-tight text-white">Visual Ground-Truth Inspector</span>
              </div>
              <button
                onClick={() => setInspectorOpen(false)}
                className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Citation Target Pill */}
              <div className="rounded-md border border-emerald-500/30 bg-emerald-950/20 p-3">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-emerald-300 font-semibold">[{activeCitation.docName} p.14 #2]</span>
                  <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 text-[10px] text-emerald-300">
                    VERIFIED
                  </span>
                </div>
                <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-zinc-400">
                  <span>Cosine: {activeCitation.similarity}</span>
                  <span>Cross-Encoder: {activeCitation.crossEncoderScore}</span>
                </div>
              </div>

              {/* Rendered PDF Visual Page with SVG Bounding Box */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
                  <span>Page 14 Visual Provenance</span>
                  <span>BBox: [0.14, 0.32, 0.85, 0.48]</span>
                </div>

                <div className="relative aspect-[3/4] w-full rounded border border-white/10 bg-zinc-950 overflow-hidden shadow-inner flex flex-col justify-between p-3 font-serif text-[8px] text-zinc-500 select-none">
                  {/* Faux PDF Text Lines */}
                  <div className="space-y-1">
                    <div className="h-2 w-32 bg-zinc-800 rounded" />
                    <div className="h-1.5 w-full bg-zinc-900 rounded" />
                    <div className="h-1.5 w-5/6 bg-zinc-900 rounded" />
                  </div>

                  {/* Luminous Emerald Bounding Box Overlay */}
                  <div
                    className="absolute rounded border-2 border-emerald-400 bg-emerald-400/15 shadow-[0_0_12px_rgba(16,185,129,0.4)] animate-pulse flex items-center justify-center font-mono text-[9px] font-bold text-emerald-200"
                    style={{
                      left: '14%',
                      top: '32%',
                      width: '71%',
                      height: '16%',
                    }}
                  >
                    NVIDIA SEC Form 10-K Datacenter Scheduled Proof
                  </div>

                  <div className="space-y-1">
                    <div className="h-1.5 w-full bg-zinc-900 rounded" />
                    <div className="h-1.5 w-4/6 bg-zinc-900 rounded" />
                    <div className="h-1.5 w-full bg-zinc-900 rounded" />
                  </div>

                  <div className="text-center font-mono text-[9px] text-zinc-600 border-t border-zinc-900 pt-1">
                    Item 8: Financial Statements — Page 14 of 96
                  </div>
                </div>
              </div>

              {/* Ground-Truth Chunk Match Text */}
              <div className="rounded border border-white/[0.08] bg-[#121316] p-3 space-y-1.5 text-xs">
                <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  Raw Ground-Truth Chunk #2847
                </div>
                <p className="font-mono text-[11px] leading-relaxed text-zinc-300 bg-black/40 p-2.5 rounded border border-white/5">
                  "{activeCitation.snippet}"
                </p>
                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
                  <span>312 tokens</span>
                  <span>MD5: 9f8ac4b2</span>
                </div>
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
