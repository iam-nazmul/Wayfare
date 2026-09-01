export interface FieldError {
  field: string;
  message: string;
}

/** RFC 9457 problem details — the only error shape the API emits (api-conventions.md). */
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  request_id?: string;
  errors?: FieldError[];
}

export class ApiError extends Error {
  readonly problem: ProblemDetail;

  constructor(problem: ProblemDetail) {
    super(problem.detail || problem.title);
    this.name = 'ApiError';
    this.problem = problem;
  }

  get status(): number {
    return this.problem.status;
  }

  get code(): string {
    return this.problem.code;
  }

  fieldErrors(): Record<string, string> {
    const map: Record<string, string> = {};
    for (const error of this.problem.errors ?? []) map[error.field] = error.message;
    return map;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function toProblem(status: number, body: unknown): ProblemDetail {
  if (body && typeof body === 'object' && 'code' in body && 'title' in body) {
    return body as ProblemDetail;
  }
  return {
    type: 'about:blank',
    title: 'Request failed',
    status,
    detail: 'The server returned an unexpected response.',
    code: 'unexpected_response',
  };
}
