import 'api/models/metrics.dart';
import 'api/models/retrieval.dart';
import 'api/models/session.dart';
import 'features/chat/chat_state.dart';

/// Realistic mock data matching Stitch wireframes (`ui/stitch_workspace/`):
/// - `01_workspace_overview.html`
/// - `02_project_overview.html`
/// - `03_project_chat_sessions.html`
///
/// Used as default / fallback when the backend workspace has no projects or metrics yet.

final mockProjects = <ChatSession>[
  const ChatSession(
    id: 'sess_nvda_fy24',
    title: 'FY24 10-K Cross-exam',
    messageCount: 6,
    files: [
      'nvda_10k_fy24.pdf',
      'financial_tables_fy24.pdf',
      'earnings_call_q4.pdf',
      'press_release_q4.txt',
    ],
    parameters: SessionParameters(
      model: 'llama3.1:latest',
      retrievalMode: 'auto',
    ),
    createdAt: 1790620000,
    updatedAt: 1790620000,
  ),
  const ChatSession(
    id: 'sess_q3_calls',
    title: 'Q3 Earnings Calls',
    messageCount: 12,
    files: [
      'msft_q3_transcript.pdf',
      'goog_q3_transcript.pdf',
      'meta_q3_transcript.pdf',
      'amzn_q3_transcript.pdf',
      'aapl_q3_transcript.pdf',
      'tsm_q3_transcript.pdf',
      'asml_q3_transcript.pdf',
    ],
    parameters: SessionParameters(
      model: 'llama3.2:3b',
      retrievalMode: 'agentic',
    ),
    createdAt: 1790610000,
    updatedAt: 1790610000,
  ),
  const ChatSession(
    id: 'sess_credit_risk',
    title: 'Credit Risk Policies',
    messageCount: 4,
    files: [
      'commercial_underwriting_v4.pdf',
      'retail_credit_framework.pdf',
      'exception_matrix_2026.pdf',
      'collateral_haircuts.pdf',
      'syndicated_lending_rules.pdf',
      'covenant_monitoring_sop.pdf',
      'risk_rating_scale.pdf',
      'concentration_limits.pdf',
      'debt_service_guidelines.pdf',
      'default_recovery_assumptions.pdf',
      'credit_committee_charter.pdf',
    ],
    parameters: SessionParameters(
      model: 'llama3.1:latest',
      retrievalMode: 'graph',
    ),
    createdAt: 1790580000,
    updatedAt: 1790580000,
  ),
  const ChatSession(
    id: 'sess_basel_iii',
    title: 'Basel III Capital Rules',
    messageCount: 3,
    files: [
      'basel_iii_monitoring_report.pdf',
      'tier1_ratio_calculation.pdf',
      'rwa_standardised_approach.pdf',
      'leverage_ratio_framework.pdf',
      'lcr_nsfr_liquidity_rules.pdf',
      'g_sib_surcharge_schedule.pdf',
      'countercyclical_buffer_q3.pdf',
      'interest_rate_risk_banking_book.pdf',
      'frtb_market_risk_standards.pdf',
    ],
    parameters: SessionParameters(
      model: 'llama3.1:latest',
      retrievalMode: 'auto',
    ),
    createdAt: 1790500000,
    updatedAt: 1790500000,
  ),
  const ChatSession(
    id: 'sess_web_rag',
    title: 'Web RAG',
    messageCount: 2,
    files: [
      'https://sec.gov/edgar/data/1045810',
      'https://investor.nvidia.com',
      'https://bloomberg.com/markets',
      'https://reuters.com/technology',
      'https://ft.com/markets',
    ],
    parameters: SessionParameters(
      model: 'llama3.2:3b',
      retrievalMode: 'direct',
    ),
    createdAt: 1790400000,
    updatedAt: 1790400000,
  ),
  const ChatSession(
    id: 'sess_vendor_contracts',
    title: 'Vendor Contracts',
    messageCount: 1,
    files: [
      'master_services_agreement_vendor_a.pdf',
      'cloud_sla_schedule_2026.pdf',
    ],
    forkedFrom: 'forked_source_chat_1',
    parameters: SessionParameters(
      model: 'llama3.1:latest',
      retrievalMode: 'auto',
    ),
    createdAt: 1790300000,
    updatedAt: 1790300000,
  ),
];

final mockSystemMetrics = SystemMetrics(
  qdrantPoints: 4912,
  redisQueueDepth: 128,
  services: {
    'qdrant': {'healthy': true},
    'redis': {'healthy': true},
    'ollama': {'healthy': true},
  },
  recentTelemetry: [
    QueryTelemetry(
      queryId: 'q_1',
      queryText: 'What is the FY24 Datacenter gross margin?',
      citationsCount: 2,
      refused: false,
      timestamp: DateTime.now().millisecondsSinceEpoch / 1000 - 720,
    ),
    QueryTelemetry(
      queryId: 'q_2',
      queryText: 'Minimum CET1 ratio under Basel III?',
      citationsCount: 1,
      refused: false,
      timestamp: DateTime.now().millisecondsSinceEpoch / 1000 - 3600,
    ),
    QueryTelemetry(
      queryId: 'q_3',
      queryText: 'FY25 guidance?',
      citationsCount: 0,
      refused: true,
      timestamp: DateTime.now().millisecondsSinceEpoch / 1000 - 10800,
    ),
  ],
);

final mockConversations = <Conversation>[
  Conversation(
    id: 'conv_1',
    sessionId: 'sess_nvda_fy24',
    title: 'Datacenter gross margin',
    messageCount: 4,
    updatedAt: DateTime.now().millisecondsSinceEpoch / 1000 - 720,
  ),
  Conversation(
    id: 'conv_2',
    sessionId: 'sess_nvda_fy24',
    title: 'Cash flow reconciliation',
    messageCount: 6,
    updatedAt: DateTime.now().millisecondsSinceEpoch / 1000 - 7200,
  ),
  Conversation(
    id: 'conv_3',
    sessionId: 'sess_nvda_fy24',
    title: 'Risk factor supply constraints',
    messageCount: 2,
    updatedAt: DateTime.now().millisecondsSinceEpoch / 1000 - 86400,
  ),
  Conversation(
    id: 'conv_4',
    sessionId: 'sess_nvda_fy24',
    title: 'Vendor margin comparison',
    messageCount: 5,
    updatedAt: DateTime.now().millisecondsSinceEpoch / 1000 - 90000,
  ),
  Conversation(
    id: 'conv_5',
    sessionId: 'sess_nvda_fy24',
    title: 'Executive compensation Q&A',
    messageCount: 3,
    updatedAt: DateTime.now().millisecondsSinceEpoch / 1000 - 259200,
  ),
  Conversation(
    id: 'conv_6',
    sessionId: 'sess_nvda_fy24',
    title: 'R&D capitalization policy',
    messageCount: 8,
    updatedAt: DateTime.now().millisecondsSinceEpoch / 1000 - 432000,
  ),
];

final mockCitations = <Citation>[
  const Citation(
    docId: 'nvda_10k_fy24.pdf',
    page: 14,
    bbox: [0.12, 0.35, 0.88, 0.58],
    snippet:
        'Datacenter compute revenue grew 244% to \$37.5 billion, and networking revenue grew 133% to \$10.0 billion, driven by the HGX platform and Quantum-2 InfiniBand architecture.',
    formattedBadge: 'Doc A, p. 14 §12.2',
  ),
  const Citation(
    docId: 'financial_tables_fy24.pdf',
    page: 8,
    bbox: [0.15, 0.20, 0.85, 0.42],
    snippet:
        'Gross margin expanded to 74.8% for the fiscal year ended January 28, 2024, compared to 56.9% in the prior fiscal year.',
    formattedBadge: 'Doc B, p. 8 §3.1',
  ),
  const Citation(
    docId: 'earnings_call_q4.pdf',
    page: 4,
    bbox: [0.10, 0.50, 0.90, 0.75],
    snippet:
        'We delivered record quarterly revenue of \$22.1 billion, up 22% sequentially and up 265% year-on-year, led by accelerating demand for enterprise inference and training.',
    formattedBadge: 'Doc C, p. 4 §1.4',
  ),
];

final mockChatMessages = <ChatMessage>[
  const ChatMessage(
    id: 'msg_1',
    role: 'user',
    content:
        'What was NVIDIA\'s FY24 Datacenter gross margin, and how did compute vs networking revenue break down?',
  ),
  ChatMessage(
    id: 'msg_2',
    role: 'assistant',
    content:
        'According to NVIDIA\'s FY24 Form 10-K, Datacenter segment gross margin was approximately **74.8%**, reflecting strong demand for Hopper GPU architecture systems.\n\n### Revenue Breakdown\n- **Compute Revenue:** Grew **244%** year-over-year to **\$37.5B**, driven by HGX systems and generative AI training infrastructure.\n- **Networking Revenue:** Grew **133%** year-over-year to **\$10.0B**, driven by Quantum-2 InfiniBand networking platforms.\n\nOperating expenses increased 13% primarily reflecting higher compensation costs and compute infrastructure.',
    citations: mockCitations,
    latencyMs: 420,
  ),
];

final mockChatTurns = <ChatTurn>[
  ChatTurn(
    id: 'turn_1',
    query: 'How did Datacenter gross margin move in FY24, and does it reconcile with cash flow?',
    answer:
        'Datacenter revenue reached **\$47.5B** in FY24, expanding segment gross margin to **72.7%**, driven primarily by hyper-scaler demand for Hopper architecture acceleration modules and networking fabrics.\n\nOperating cash flow reconciled at **\$28.1B** compared to GAAP net income of **\$29.8B**, accounting for non-cash stock-based compensation and working capital adjustments.\n\n| Metric | FY23 | FY24 | YoY Δ |\n|---|---:|---:|---:|\n| Datacenter Revenue | \$15.0B | \$47.5B | +217% |\n| Gross Margin | 56.9% | 72.7% | +1,580 bps |\n| Operating Cash Flow | \$5.6B | \$28.1B | +402% |',
    citations: mockCitations,
    topScore: 0.94,
    mode: 'auto',
  ),
];
