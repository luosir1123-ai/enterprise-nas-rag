import {
  ArrowUp,
  BookOpenText,
  Bot,
  BriefcaseBusiness,
  FileCheck2,
  FileSearch2,
  CircleAlert,
  CircleCheck,
  Database,
  Gauge,
  History,
  LayoutDashboard,
  Menu,
  ExternalLink,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  RotateCcw,
  Search,
  ShoppingCart,
  Sparkles,
  X,
} from 'lucide-react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ChatMessage,
  ConversationSummary,
  EvaluationStatus,
  getConversation,
  getAuthStatus,
  getOperationsStatus,
  listConversations,
  OperationsStatus,
  ReferenceChunk,
  redirectToLogin,
  saveConversation,
  streamChat,
  SyncStatus,
} from './ragflow';

type AssistantKey = 'purchase' | 'sales' | 'product';

type AssistantConfig = {
  key: AssistantKey;
  chatId: string;
  knowledgeBaseId: string;
  name: string;
  shortName: string;
  description: string;
  scope: string;
  icon: typeof ShoppingCart;
  suggestions: string[];
};

const ASSISTANTS: AssistantConfig[] = [
  {
    key: 'purchase',
    chatId: 'b12c3984841511f1b6171536aff2886e',
    knowledgeBaseId: '1f8ef26c79ea11f188ae0568c90e9371',
    name: '采购知识助手',
    shortName: '采购',
    description: '供应商报价、采购资料、认证与规格查询',
    scope: '采购知识库',
    icon: ShoppingCart,
    suggestions: ['查询 GS-30W0989 的报价和 MOQ'],
  },
  {
    key: 'sales',
    chatId: '1077ccfa841611f1b6171536aff2886e',
    knowledgeBaseId: '1f9106ec79ea11f188ae0568c90e9371',
    name: '销售知识助手',
    shortName: '销售',
    description: '客户方案、历史报价、订单与项目资料查询',
    scope: '销售知识库',
    icon: BriefcaseBusiness,
    suggestions: ['查询 LT-W80 的历史销售资料'],
  },
  {
    key: 'product',
    chatId: '97347fe67aab11f19289392309541330',
    knowledgeBaseId: '1f91c47e79ea11f188ae0568c90e9371',
    name: '产品资料助手',
    shortName: '产品',
    description: '产品规格、设计文档、BOM 与测试报告查询',
    scope: '产品设计知识库',
    icon: FileSearch2,
    suggestions: ['查询 CR2032 CB 报告中的额定电压、容量和测试标准'],
  },
];

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: '请选择一个业务问题开始查询。我会优先引用知识库中的原始文件；证据不足时会明确拒答。',
};

let fallbackMessageId = 0;

function createMessageId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }

  fallbackMessageId += 1;
  return `message-${Date.now().toString(36)}-${fallbackMessageId.toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function makeConversationState() {
  return {
    id: null as string | null,
    messages: [WELCOME_MESSAGE],
    sessionId: null as string | null,
  };
}

function App() {
  const [authReady, setAuthReady] = useState(false);
  const [activeView, setActiveView] = useState<'overview' | 'assistant'>('assistant');
  const [activeKey, setActiveKey] = useState<AssistantKey>('purchase');
  const [conversations, setConversations] = useState<Record<AssistantKey, ReturnType<typeof makeConversationState>>>(() => ({
    purchase: makeConversationState(),
    sales: makeConversationState(),
    product: makeConversationState(),
  }));
  const [history, setHistory] = useState<Record<AssistantKey, ConversationSummary[]>>({
    purchase: [],
    sales: [],
    product: [],
  });
  const [historyLoading, setHistoryLoading] = useState(false);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedReferences, setSelectedReferences] = useState<ReferenceChunk[]>([]);
  const [operations, setOperations] = useState<OperationsStatus | null>(null);
  const [operationsLoading, setOperationsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const historyInitializedRef = useRef<Record<AssistantKey, boolean>>({ purchase: false, sales: false, product: false });
  const assistant = useMemo(() => ASSISTANTS.find((item) => item.key === activeKey)!, [activeKey]);
  const conversation = conversations[activeKey];

  useEffect(() => {
    let active = true;
    void getAuthStatus()
      .then((status) => {
        if (status.mode === 'wecom' && !status.authenticated) {
          redirectToLogin();
          return;
        }
        if (active) setAuthReady(true);
      })
      .catch(() => {
        if (active) setAuthReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const refreshOperations = async () => {
    setOperationsLoading(true);
    try {
      setOperations(await getOperationsStatus());
    } catch (error) {
      const message = error instanceof Error ? error.message : '';
      if (message === 'AUTH_REQUIRED') redirectToLogin();
    } finally {
      setOperationsLoading(false);
    }
  };

  const loadHistory = async (key: AssistantKey, openLatest: boolean) => {
    setHistoryLoading(true);
    try {
      const items = await listConversations(key);
      setHistory((current) => ({ ...current, [key]: items }));
      if (openLatest && items.length && conversations[key].messages.length === 1) {
        const record = await getConversation(items[0].id);
        setConversations((current) => ({
          ...current,
          [key]: {
            id: record.id,
            sessionId: record.session_id ?? null,
            messages: [WELCOME_MESSAGE, ...record.messages],
          },
        }));
        if (key === activeKey) {
          setSelectedReferences(record.messages.at(-1)?.references ?? []);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '';
      if (message === 'AUTH_REQUIRED') redirectToLogin();
      else if (message !== 'ACCESS_DENIED') console.warn('无法读取历史会话', error);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    void refreshOperations();
    const timer = window.setInterval(() => void refreshOperations(), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!authReady || historyInitializedRef.current[activeKey]) return;
    historyInitializedRef.current[activeKey] = true;
    void loadHistory(activeKey, true);
  }, [authReady, activeKey]);

  if (!authReady) {
    return (
      <div className="auth-loading" role="status">
        <img src="/internal/letouch-logo.svg" alt="LeTouch" />
        <span>正在验证企业身份</span>
      </div>
    );
  }

  if (window.location.pathname.startsWith('/internal/file/')) {
    return <DocumentViewer />;
  }

  const selectAssistant = (key: AssistantKey) => {
    setActiveView('assistant');
    setActiveKey(key);
    setSelectedReferences([]);
    setMobileMenuOpen(false);
  };

  const openHistory = async (item: ConversationSummary) => {
    try {
      const record = await getConversation(item.id);
      setConversations((current) => ({
        ...current,
        [activeKey]: {
          id: record.id,
          sessionId: record.session_id ?? null,
          messages: [WELCOME_MESSAGE, ...record.messages],
        },
      }));
      setSelectedReferences(record.messages.at(-1)?.references ?? []);
      setActiveView('assistant');
      setMobileMenuOpen(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : '历史会话读取失败';
      if (message === 'AUTH_REQUIRED') redirectToLogin();
    }
  };

  const resetConversation = () => {
    abortRef.current?.abort();
    setConversations((current) => ({ ...current, [activeKey]: makeConversationState() }));
    setSelectedReferences([]);
    setIsSending(false);
  };

  const send = async (question: string) => {
    const value = question.trim();
    if (!value || isSending) return;

    const userMessage: ChatMessage = { id: createMessageId(), role: 'user', content: value };
    const assistantMessage: ChatMessage = {
      id: createMessageId(),
      role: 'assistant',
      content: '',
      pending: true,
    };
    const requestMessages = [...conversation.messages.filter((item) => item.id !== 'welcome'), userMessage];
    const assistantKey = assistant.key;
    const currentConversation = conversation;
    let savedSessionId = currentConversation.sessionId;
    let latestAnswer = '';
    let latestReferences: ReferenceChunk[] = [];

    setInput('');
    setSelectedReferences([]);
    setIsSending(true);
    setConversations((current) => ({
      ...current,
      [activeKey]: {
        ...current[activeKey],
        messages: [...current[activeKey].messages, userMessage, assistantMessage],
      },
    }));

    const controller = new AbortController();
    abortRef.current = controller;

    const updateAssistantMessage = (updates: Partial<ChatMessage>) => {
      setConversations((current) => ({
        ...current,
        [activeKey]: {
          ...current[activeKey],
          messages: current[activeKey].messages.map((message) =>
            message.id === assistantMessage.id ? { ...message, ...updates } : message,
          ),
        },
      }));
    };

    try {
      await streamChat(assistantKey, currentConversation.sessionId, requestMessages, controller.signal, {
        onAnswer: (answer) => {
          latestAnswer = answer;
          updateAssistantMessage({ content: answer, pending: false });
        },
        onReferences: (references) => {
          latestReferences = references;
          setSelectedReferences(references);
          updateAssistantMessage({ references });
        },
        onSession: (sessionId) => {
          savedSessionId = sessionId;
          setConversations((current) => ({
            ...current,
            [activeKey]: { ...current[activeKey], sessionId },
          }));
        },
      });
      updateAssistantMessage({ pending: false });
      try {
        const saved = await saveConversation({
          id: currentConversation.id ?? '',
          assistant_id: assistantKey,
          session_id: savedSessionId,
          title: value,
          messages: [
            ...requestMessages.slice(0, -1),
            userMessage,
            { ...assistantMessage, content: latestAnswer, pending: false, references: latestReferences },
          ],
        });
        setConversations((current) => ({
          ...current,
          [assistantKey]: {
            ...current[assistantKey],
            id: saved.id,
            sessionId: saved.session_id ?? savedSessionId,
          },
        }));
        await loadHistory(assistantKey, false);
      } catch (historyError) {
        console.warn('历史会话保存失败', historyError);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = error instanceof Error ? error.message : '请求失败，请稍后重试。';
      if (message === 'AUTH_REQUIRED') {
        redirectToLogin();
        return;
      }
      if (message === 'ACCESS_DENIED') {
        updateAssistantMessage({ content: '当前设备不在公司内网允许范围内。请连接办公室网络后重试。', pending: false, error: true });
        return;
      }
      updateAssistantMessage({ content: message, pending: false, error: true });
    } finally {
      setIsSending(false);
      abortRef.current = null;
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-row">
          <img src="/internal/letouch-logo.svg" alt="LeTouch" className="brand-logo" />
          <button className="icon-button mobile-only" onClick={() => setMobileMenuOpen(false)} aria-label="关闭菜单" title="关闭菜单">
            <X size={19} />
          </button>
        </div>

        <div className="workspace-label">公司知识中心</div>
        <nav className="primary-nav" aria-label="业务助手">
          <button
            className={`nav-item overview-item ${activeView === 'overview' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('overview');
              setMobileMenuOpen(false);
              void refreshOperations();
            }}
            type="button"
          >
            <LayoutDashboard size={18} />
            <span>工作台</span>
          </button>
          <div className="nav-section-label">知识助手</div>
          {ASSISTANTS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={`nav-item ${activeView === 'assistant' && item.key === activeKey ? 'active' : ''}`}
                key={item.key}
                onClick={() => selectAssistant(item.key)}
                type="button"
              >
                <Icon size={18} />
                <span>{item.name}</span>
                <span className="status-dot" aria-label="可用" />
              </button>
            );
          })}
        </nav>

        {activeView === 'assistant' && (
          <section className="history-section" aria-label="历史记录">
            <div className="history-heading"><History size={14} /><span>历史记录</span></div>
            <div className="history-list">
              {history[activeKey].map((item) => (
                <button className="history-item" type="button" key={item.id} onClick={() => void openHistory(item)} title={item.title}>
                  <strong>{item.title}</strong>
                  <span>{formatHistoryTime(item.updated_at)}</span>
                </button>
              ))}
              {!historyLoading && history[activeKey].length === 0 && <span className="history-empty">暂无历史记录</span>}
              {historyLoading && <span className="history-empty">正在读取记录</span>}
            </div>
          </section>
        )}

        <div className="sidebar-footer">
          <div className="sync-state">
            <RefreshCw size={16} />
            <div>
              <strong>{syncSidebarTitle(operations?.sync)}</strong>
              <span>{syncSidebarDetail(operations?.sync)}</span>
            </div>
          </div>
        </div>
      </aside>

      {mobileMenuOpen && <button className="sidebar-scrim" aria-label="关闭菜单" onClick={() => setMobileMenuOpen(false)} />}

      <main className="chat-workspace">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setMobileMenuOpen(true)} aria-label="打开菜单" title="打开菜单">
            <Menu size={20} />
          </button>
          <div className="assistant-heading">
            <div className="assistant-icon">
              {activeView === 'overview' ? <Gauge size={20} /> : <assistant.icon size={20} />}
            </div>
            <div>
              <h1>{activeView === 'overview' ? '运行工作台' : assistant.name}</h1>
              <p>{activeView === 'overview' ? '知识库同步与回答质量' : assistant.description}</p>
            </div>
          </div>
          <div className="topbar-actions">
            {activeView === 'overview' ? (
              <button className="icon-button" onClick={() => void refreshOperations()} aria-label="刷新运行状态" title="刷新运行状态">
                <RefreshCw className={operationsLoading ? 'spin' : ''} size={18} />
              </button>
            ) : (
              <>
                <span className="scope-badge"><BookOpenText size={15} />{assistant.scope}</span>
                <button className="icon-button" onClick={resetConversation} aria-label="新建对话" title="新建对话">
                  <RotateCcw size={18} />
                </button>
                <button className="icon-button desktop-only" onClick={() => setEvidenceOpen((open) => !open)} aria-label="切换证据栏" title="切换证据栏">
                  {evidenceOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
                </button>
              </>
            )}
          </div>
        </header>

        {activeView === 'overview' ? (
          <OperationsDashboard operations={operations} loading={operationsLoading} />
        ) : <div className={`content-grid ${evidenceOpen ? '' : 'evidence-hidden'}`}>
          <section className="conversation" aria-live="polite">
            <div className="message-list">
              {conversation.messages.map((message) => (
                <Message key={message.id} message={message} onShowReferences={setSelectedReferences} />
              ))}

              {conversation.messages.length === 1 && (
                <div className="suggestions">
                  <div className="suggestion-heading"><Sparkles size={16} />常用查询</div>
                  <div className="suggestion-grid">
                    {assistant.suggestions.map((suggestion) => (
                      <button key={suggestion} type="button" onClick={() => void send(suggestion)}>
                        <Search size={16} />
                        <span>{suggestion}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="composer-wrap">
              <form className="composer" onSubmit={handleSubmit}>
                <textarea
                  aria-label="输入问题"
                  placeholder={`向${assistant.shortName}知识库提问`}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault();
                      void send(input);
                    }
                  }}
                  rows={1}
                />
                <button className="send-button" type="submit" disabled={!input.trim() || isSending} aria-label="发送" title="发送">
                  <ArrowUp size={19} />
                </button>
              </form>
              <div className="composer-meta">
                <span><FileCheck2 size={14} />回答基于原始文件并显示引用</span>
                <span>证据不足时拒答</span>
              </div>
            </div>
          </section>

          {evidenceOpen && <EvidencePanel references={selectedReferences} knowledgeBaseId={assistant.knowledgeBaseId} />}
        </div>}
      </main>
    </div>
  );
}

function syncSidebarTitle(sync?: SyncStatus): string {
  if (!sync?.available) return '等待运行数据';
  if (sync.state === 'error') return '同步存在异常';
  if (sync.state === 'running') return '正在同步';
  if (sync.state === 'pending') return '同步队列处理中';
  return '知识库在线';
}

function syncSidebarDetail(sync?: SyncStatus): string {
  if (!sync?.available) return '尚未读取同步报告';
  if (sync.error_count) return `${sync.error_count} 项异常`;
  if (sync.pending_count) return `${sync.pending_count} 项等待后续批次`;
  return sync.finished_at ? `更新于 ${formatShortTime(sync.finished_at)}` : '三库索引可用';
}

function formatShortTime(value?: string | null): string {
  if (!value) return '暂无';
  return value.slice(5, 16);
}

function formatHistoryTime(value?: string | null): string {
  if (!value) return '暂无时间';
  return value.replace('T', ' ').slice(5, 16);
}

function percent(value?: number): string {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function statusTone(state?: string): 'good' | 'warn' | 'bad' | 'muted' {
  if (state === 'healthy') return 'good';
  if (state === 'pending' || state === 'running') return 'warn';
  if (state === 'error' || state === 'failed') return 'bad';
  return 'muted';
}

function OperationsDashboard({ operations, loading }: { operations: OperationsStatus | null; loading: boolean }) {
  const sync = operations?.sync;
  const evaluation = operations?.evaluation;
  const syncTone = statusTone(sync?.state);
  const evaluationTone = statusTone(evaluation?.state);

  return (
    <div className="operations-dashboard">
      <div className="ops-summary-grid">
        <article className="ops-metric">
          <div className={`ops-metric-icon ${syncTone}`}><Database size={18} /></div>
          <div><span>最近同步</span><strong>{formatShortTime(sync?.finished_at)}</strong></div>
          <small>{sync?.available ? `${sync.applied_count ?? 0} 项已处理` : '暂无报告'}</small>
        </article>
        <article className="ops-metric">
          <div className={`ops-metric-icon ${syncTone}`}><RefreshCw size={18} /></div>
          <div><span>待处理</span><strong>{sync?.pending_count ?? 0}</strong></div>
          <small>{sync?.error_count ? `${sync.error_count} 项异常` : '按小时继续处理'}</small>
        </article>
        <article className="ops-metric">
          <div className={`ops-metric-icon ${evaluationTone}`}><Gauge size={18} /></div>
          <div><span>自动评测</span><strong>{evaluation?.available ? percent(evaluation.pass_rate) : '暂无'}</strong></div>
          <small>{evaluation?.available ? `${evaluation.passed ?? 0}/${evaluation.case_count ?? 0} 通过` : '等待首次运行'}</small>
        </article>
      </div>

      <section className="ops-section">
        <div className="ops-section-heading">
          <div><h2>知识库同步</h2><p>{sync?.source_nas_name ?? 'LeTouch NAS'}</p></div>
          <StatusLabel state={sync?.state} />
        </div>
        {sync?.datasets?.length ? (
          <div className="ops-table-wrap">
            <table className="ops-table">
              <thead><tr><th>知识库</th><th>当前 NAS</th><th>RAGFlow 文档</th><th>重复副本</th><th>历史保留</th><th>来源已移除</th><th>本批变化</th></tr></thead>
              <tbody>
                {sync.datasets.map((dataset) => (
                  <tr key={dataset.key}>
                    <td><strong>{dataset.name}</strong></td>
                    <td>{dataset.current_candidates}</td>
                    <td>{dataset.ragflow_documents}</td>
                    <td>{dataset.duplicate_current_path}</td>
                    <td>{dataset.historical_retained}</td>
                    <td>{dataset.missing_from_source}</td>
                    <td>{dataset.added + dataset.modified + dataset.metadata_refresh}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyOperations loading={loading} />}
      </section>

      <section className="ops-section">
        <div className="ops-section-heading">
          <div><h2>质量回归</h2><p>{evaluation?.generated_at ? `运行于 ${evaluation.generated_at}` : '尚未运行'}</p></div>
          <StatusLabel state={evaluation?.state} />
        </div>
        {evaluation?.available ? (
          <div className="quality-groups">
            <div>
              <h3>评测套件</h3>
              <div className="quality-grid">
                {evaluation.suites.map((suite) => (
                  <QualityRow
                    key={suite.name}
                    label={suite.name === 'source_coverage' ? '来源召回覆盖' : '业务答案准确性'}
                    result={suite}
                  />
                ))}
              </div>
            </div>
            <div>
              <h3>知识库</h3>
              <div className="quality-grid">
                {evaluation.knowledge_bases.map((knowledgeBase) => (
                  <QualityRow key={knowledgeBase.name} label={knowledgeBase.name} result={knowledgeBase} />
                ))}
              </div>
            </div>
          </div>
        ) : <EmptyOperations loading={loading} />}
      </section>
    </div>
  );
}

function QualityRow({ label, result }: { label: string; result: { case_count: number; passed: number; failed: number; pass_rate: number } }) {
  return (
    <article className="quality-row">
      <div><strong>{label}</strong><span>{result.case_count} 条用例</span></div>
      <div className="quality-score"><strong>{percent(result.pass_rate)}</strong><span>{result.passed} 通过 / {result.failed} 失败</span></div>
    </article>
  );
}

function StatusLabel({ state }: { state?: string }) {
  const tone = statusTone(state);
  const labels: Record<string, string> = {
    healthy: '正常', pending: '处理中', running: '运行中', error: '异常', failed: '未通过', unavailable: '暂无数据',
  };
  return <span className={`ops-status ${tone}`}>{tone === 'good' ? <CircleCheck size={14} /> : <CircleAlert size={14} />}{labels[state ?? 'unavailable'] ?? '暂无数据'}</span>;
}

function EmptyOperations({ loading }: { loading: boolean }) {
  return <div className="ops-empty">{loading ? '正在读取运行状态' : '暂无可用报告'}</div>;
}

function Message({ message, onShowReferences }: { message: ChatMessage; onShowReferences: (references: ReferenceChunk[]) => void }) {
  if (message.role === 'user') {
    return <div className="message-row user-message"><div className="message-bubble">{message.content}</div></div>;
  }

  return (
    <div className={`message-row assistant-message ${message.error ? 'error-message' : ''}`}>
      <div className="message-avatar"><Bot size={18} /></div>
      <div className="message-body">
        <div className="message-author">LeTouch AI</div>
        {message.pending && !message.content ? (
          <div className="thinking"><span /><span /><span />正在检索资料</div>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        )}
        {!!message.references?.length && (
          <button className="reference-trigger" type="button" onClick={() => onShowReferences(message.references ?? [])}>
            <FileSearch2 size={15} />查看 {message.references.length} 条来源证据
          </button>
        )}
      </div>
    </div>
  );
}

function getDocumentUrl(reference: ReferenceChunk): string | null {
  const referenceDocumentId = reference.document_id || reference.doc_id;
  if (!referenceDocumentId) return null;
  const name = reference.doc_name || reference.document_name || '';
  const documentId = encodeURIComponent(referenceDocumentId);
  return `/internal/file/${documentId}?name=${encodeURIComponent(name)}`;
}

function EvidencePanel({ references, knowledgeBaseId }: { references: ReferenceChunk[]; knowledgeBaseId: string }) {
  return (
    <aside className="evidence-panel">
      <div className="evidence-header">
        <div>
          <h2>来源证据</h2>
          <p>本次回答引用的原始资料</p>
        </div>
        <span className="evidence-count">{references.length}</span>
      </div>
      {references.length ? (
        <div className="evidence-list">
          {references.map((reference, index) => {
            const name = reference.doc_name || reference.document_name || '未命名文件';
            const page = Array.isArray(reference.page_num) ? reference.page_num[0] : reference.page_num;
            const snippet = reference.content_with_weight || reference.content_ltks || '';
            const documentUrl = getDocumentUrl(reference);
            const content = (
              <>
                <div className="evidence-index">{index + 1}</div>
                <div>
                  <div className="evidence-title-row">
                    <h3>{name}</h3>
                    {documentUrl && <ExternalLink size={13} aria-hidden="true" />}
                  </div>
                  <div className="evidence-meta">
                    {page ? <span>第 {page} 页</span> : <span>原始切片</span>}
                    {typeof reference.similarity === 'number' && <span>相关度 {Math.round(reference.similarity * 100)}%</span>}
                  </div>
                  {snippet && <p>{snippet.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 180)}</p>}
                </div>
              </>
            );
            const key = `${reference.id ?? reference.document_id ?? reference.doc_id ?? name}-${index}`;
            return documentUrl ? (
              <a
                aria-label={`打开来源文件：${name}`}
                className="evidence-item evidence-link"
                href={documentUrl}
                key={key}
                rel="noreferrer"
                target="_blank"
                title="打开原文件"
              >
                {content}
              </a>
            ) : (
              <article className="evidence-item" key={key}>{content}</article>
            );
          })}
        </div>
      ) : (
        <div className="evidence-empty">
          <History size={24} />
          <strong>等待检索</strong>
          <span>提问后，相关文件会显示在这里</span>
        </div>
      )}
    </aside>
  );
}

function DocumentViewer() {
  const prefix = '/internal/file/';
  const documentId = decodeURIComponent(window.location.pathname.slice(prefix.length));
  const name = new URLSearchParams(window.location.search).get('name') || '来源文件';
  const previewUrl = `/internal-api/documents/${encodeURIComponent(documentId)}/preview?name=${encodeURIComponent(name)}`;
  const downloadUrl = `${previewUrl}&download=1`;

  return (
    <div className="document-viewer">
      <header className="document-viewer-header">
        <div>
          <div className="document-viewer-kicker">LeTouch 知识中心</div>
          <h1>{name}</h1>
        </div>
        <div className="document-viewer-actions">
          <a className="document-download" href={downloadUrl}>下载原文件</a>
          <a className="document-back" href="/internal/">返回助手</a>
        </div>
      </header>
      <main className="document-frame-wrap">
        <iframe className="document-frame" src={previewUrl} title="来源文件预览" />
      </main>
    </div>
  );
}

export default App;
