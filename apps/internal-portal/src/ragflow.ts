export type ReferenceChunk = {
  id?: string;
  doc_id?: string;
  document_id?: string;
  doc_name?: string;
  document_name?: string;
  content_with_weight?: string;
  content_ltks?: string;
  similarity?: number;
  page_num?: number | number[];
  positions?: number[][];
};

export type RagflowReference = {
  chunks?: ReferenceChunk[];
  doc_aggs?: Array<Record<string, unknown>>;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  references?: ReferenceChunk[];
  pending?: boolean;
  error?: boolean;
};

export type ConversationSummary = {
  id: string;
  assistant_id: string;
  session_id?: string | null;
  title: string;
  preview: string;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type ConversationRecord = ConversationSummary & {
  messages: ChatMessage[];
};

type CompletionEvent = {
  code?: number;
  message?: string;
  data?:
    | boolean
    | {
        answer?: string;
        session_id?: string;
        final?: boolean;
        start_to_think?: boolean;
        end_to_think?: boolean;
        reference?: RagflowReference | ReferenceChunk[];
      };
};

type StreamCallbacks = {
  onAnswer: (answer: string, final: boolean) => void;
  onReferences: (references: ReferenceChunk[]) => void;
  onSession: (sessionId: string) => void;
};

export type AuthStatus = {
  authenticated: boolean;
  mode: 'trusted_lan' | 'wecom' | string;
  user?: string | null;
};

export type SyncDatasetStatus = {
  key: string;
  name: string;
  current_candidates: number;
  ragflow_documents: number;
  unchanged: number;
  added: number;
  modified: number;
  metadata_refresh: number;
  duplicate_current_path: number;
  historical_retained: number;
  missing_from_source: number;
};

export type SyncStatus = {
  available: boolean;
  state: 'healthy' | 'pending' | 'running' | 'error' | 'unavailable' | string;
  finished_at?: string | null;
  age_seconds?: number | null;
  source_nas_name?: string;
  deletion_policy?: string;
  applied_count?: number;
  pending_count?: number;
  error_count?: number;
  change_count?: number;
  datasets: SyncDatasetStatus[];
};

export type EvaluationGroupStatus = {
  name: string;
  case_count: number;
  passed: number;
  failed: number;
  pass_rate: number;
};

export type EvaluationStatus = {
  available: boolean;
  state: 'healthy' | 'failed' | 'unavailable' | string;
  generated_at?: string | null;
  age_seconds?: number | null;
  case_count?: number;
  passed?: number;
  failed?: number;
  pass_rate?: number;
  error_count?: number;
  suites: EvaluationGroupStatus[];
  knowledge_bases: EvaluationGroupStatus[];
};

export type OperationsStatus = {
  sync: SyncStatus;
  evaluation: EvaluationStatus;
};

function extractReferences(reference: RagflowReference | ReferenceChunk[] | undefined): ReferenceChunk[] {
  if (!reference) return [];
  return Array.isArray(reference) ? reference : (reference.chunks ?? []);
}

function mergeAnswer(current: string, incoming: string, final: boolean): string {
  if (!incoming) return current;
  if (final || incoming.startsWith(current)) return incoming;
  if (current.endsWith(incoming)) return current;
  return current + incoming;
}

function isRefusalText(content: string): boolean {
  const compact = content.replace(/\s+/g, '');
  if (!compact || compact.length > 240) return false;
  return [
    /^(?:抱歉[，,]?)?(?:根据.{0,40})?(?:没有找到|未找到).{0,80}(?:信息|资料|证据)/,
    /^(?:抱歉[，,]?)?(?:根据.{0,40})?(?:没有|不存在).{0,120}(?:信息|资料|证据)[。.!！]?$/,
    /^(?:当前)?知识库.{0,30}(?:没有|缺少|不足).{0,30}(?:证据|信息|资料)/,
    /^(?:抱歉[，,]?)?(?:根据.{0,40})?无法(?:回答|确定|提供)/,
    /^(?:抱歉[，,]?)?.{0,50}证据不足/,
  ].some((pattern) => pattern.test(compact));
}

export async function streamChat(
  assistantId: string,
  sessionId: string | null,
  messages: ChatMessage[],
  signal: AbortSignal,
  callbacks: StreamCallbacks,
): Promise<void> {
  const response = await fetch('/internal-api/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      assistant_id: assistantId,
      session_id: sessionId ?? undefined,
      messages: messages.map(({ role, content }) => ({ role, content })),
      pass_all_history_messages: true,
      reasoning: false,
      stream: true,
    }),
    signal,
  });

  if (response.status === 401) throw new Error('AUTH_REQUIRED');
  if (response.status === 403) throw new Error('ACCESS_DENIED');
  if (!response.ok || !response.body) {
    throw new Error(`请求失败（HTTP ${response.status}）`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let answer = '';
  let isThinking = false;

  const consume = (raw: string) => {
    const line = raw.trim();
    if (!line.startsWith('data:')) return;
    const payload = line.slice(5).trim();
    if (!payload || payload === '[DONE]') return;

    let event: CompletionEvent;
    try {
      event = JSON.parse(payload) as CompletionEvent;
    } catch {
      return;
    }

    if (event.code && event.code !== 0) {
      throw new Error(event.message || 'RAGFlow 返回错误');
    }
    if (!event.data || event.data === true) return;

    if (event.data.session_id) callbacks.onSession(event.data.session_id);
    if (event.data.start_to_think) {
      isThinking = true;
      return;
    }
    if (event.data.end_to_think) {
      isThinking = false;
      return;
    }
    if (isThinking) return;
    if (event.data.answer !== undefined) {
      answer = mergeAnswer(answer, event.data.answer, Boolean(event.data.final));
      callbacks.onAnswer(answer, Boolean(event.data.final));
    }

    const references = extractReferences(event.data.reference);
    if (isRefusalText(answer)) {
      callbacks.onReferences([]);
    } else if (references.length) {
      callbacks.onReferences(references);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';
    events.forEach(consume);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
}

export async function getAuthStatus(): Promise<AuthStatus> {
  const response = await fetch('/internal-api/auth/status', { cache: 'no-store' });
  if (!response.ok) throw new Error(`认证状态检查失败（HTTP ${response.status}）`);
  return response.json() as Promise<AuthStatus>;
}

export async function getOperationsStatus(): Promise<OperationsStatus> {
  const response = await fetch('/internal-api/operations/status', { cache: 'no-store' });
  if (response.status === 401) throw new Error('AUTH_REQUIRED');
  if (response.status === 403) throw new Error('ACCESS_DENIED');
  if (!response.ok) throw new Error(`运行状态检查失败（HTTP ${response.status}）`);
  return response.json() as Promise<OperationsStatus>;
}

async function historyRequest<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, { ...init, credentials: 'same-origin' });
  if (response.status === 401) throw new Error('AUTH_REQUIRED');
  if (response.status === 403) throw new Error('ACCESS_DENIED');
  if (!response.ok) throw new Error(`历史记录请求失败（HTTP ${response.status}）`);
  return response.json() as Promise<T>;
}

export async function listConversations(assistantId: string): Promise<ConversationSummary[]> {
  const result = await historyRequest<{ items: ConversationSummary[] }>(
    `/internal-api/conversations?assistant_id=${encodeURIComponent(assistantId)}`,
    { cache: 'no-store' },
  );
  return result.items ?? [];
}

export async function getConversation(conversationId: string): Promise<ConversationRecord> {
  return historyRequest<ConversationRecord>(`/internal-api/conversations/${encodeURIComponent(conversationId)}`, {
    cache: 'no-store',
  });
}

export async function saveConversation(
  conversation: Pick<ConversationRecord, 'id' | 'assistant_id' | 'session_id' | 'title' | 'messages'>,
): Promise<ConversationRecord> {
  return historyRequest<ConversationRecord>('/internal-api/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(conversation),
  });
}

export function redirectToLogin(): void {
  const next = `${window.location.pathname}${window.location.search}`;
  window.location.href = `${window.location.origin}/internal-api/auth/login?next=${encodeURIComponent(next)}`;
}
