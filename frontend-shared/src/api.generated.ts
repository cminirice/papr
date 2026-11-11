// 由scripts/export_contracts.py生成；请勿手动修改。

export type AdminJobDetail = {
  "job": AdminJobSummary;
  "questions": Array<MultiplicationQuestion>;
  "validation": ValidationView | null;
};

export type AdminJobList = {
  "date_from": string;
  "date_to": string;
  "items": Array<AdminJobSummary>;
  "next_cursor": string | null;
  "has_more": boolean;
};

export type AdminJobSummary = {
  "id": string;
  "kind": "paper_generate" | "template_validate" | "template_preview";
  "status": "queued" | "running" | "succeeded" | "failed" | "cancelled";
  "phase": "queued" | "generating" | "rendering" | "saving" | "done";
  "attempt": number;
  "max_attempts": number;
  "created_at": string;
  "started_at": string | null;
  "finished_at": string | null;
  "error_code": string | null;
  "error_message": string | null;
  "template_id": string | null;
  "template_name": string | null;
  "template_version_id": string | null;
  "version_no": number | null;
  "validation_run_id": string | null;
  "validation_status": "queued" | "running" | "passed" | "failed" | "stale" | null;
  "paper_id": string | null;
  "paper_status": "active" | "withdrawn" | null;
  "difficulty": "basic" | "standard" | "challenge" | null;
  "total_count": number | null;
  "theme_name": string | null;
};

export type AdminLogin = {
  "username": string;
  "password": string;
};

export type AdminOverview = {
  "usage"?: UsageCounts;
  "date_from": string;
  "date_to": string;
  "as_of": string;
  "totals": GenerationCounts;
  "daily": Array<DailyGenerationCounts>;
  "generation_queue": QueueCounts;
  "validation_queue": QueueCounts;
};

export type AdminPaperDetail = {
  "status"?: "active" | "withdrawn";
  "notices"?: Array<NoticeView>;
  "id": string;
  "title": string;
  "difficulty": "basic" | "standard" | "challenge";
  "total_count": number;
  "catalog_name": string;
  "theme_name": string;
  "question_type_counts": QuestionCounts;
  "generated_at": string;
  "files": Array<PaperFile>;
  "owner_user_id": string;
  "job_id": string;
  "lock_version": number;
  "questions": Array<MultiplicationQuestion>;
  "sources": Array<SourceVersion>;
};

export type AdminPaperList = {
  "items": Array<AdminPaperSummary>;
  "next_cursor": string | null;
  "has_more": boolean;
};

export type AdminPaperSummary = {
  "status"?: "active" | "withdrawn";
  "notices"?: Array<NoticeView>;
  "id": string;
  "title": string;
  "difficulty": "basic" | "standard" | "challenge";
  "total_count": number;
  "catalog_name": string;
  "theme_name": string;
  "question_type_counts": QuestionCounts;
  "generated_at": string;
  "files": Array<PaperFile>;
  "owner_user_id": string;
  "job_id": string;
};

export type AdminSessionCreated = {
  "admin_id": string;
  "expires_at": string;
  "server_now": string;
  "csrf_token": string;
};

export type AdminSessionView = {
  "admin_id": string;
  "expires_at": string;
  "server_now": string;
};

export type CapabilitySelection = {
  "theme_id": string;
  "knowledge_point_ids": Array<string>;
  "difficulty": "basic" | "standard" | "challenge";
};

export type CapabilityView = {
  "content_epoch": number;
  "selection_hash": string;
  "count_options": CountOptions;
  "feasible_counts": Array<QuestionCounts>;
  "point_coverage": Array<string>;
  "warnings": Array<string>;
};

export type CatalogCreate = {
  "code": string;
  "name": string;
  "term": "upper" | "lower";
  "source_id"?: string | null;
  "reason": string;
};

export type CatalogDetail = {
  "id": string;
  "code": string;
  "name": string;
  "term": "upper" | "lower";
  "status": "draft" | "active" | "archived";
  "verification_status": "provisional" | "verified";
  "lock_version": number;
  "source_id": string | null;
  "catalog_version": number;
};

export type CatalogEdit = {
  "name"?: string | null;
  "term"?: "upper" | "lower" | null;
  "source_id"?: string | null;
  "status"?: "draft" | "active" | "archived" | null;
  "reason": string;
};

export type CatalogList = {
  "items": Array<CatalogSummary>;
  "offset": number;
  "limit": number;
  "total": number;
};

export type CatalogState = {
  "reason": string;
  "status": "draft" | "active" | "archived";
};

export type CatalogSummary = {
  "id": string;
  "code": string;
  "name": string;
  "term": "upper" | "lower";
  "status": "draft" | "active" | "archived";
  "verification_status": "provisional" | "verified";
  "lock_version": number;
};

export type ChoiceAnswer = {
  "kind"?: "single_choice";
  "value": string;
  "correct_option_id": string;
};

export type ChoiceOption = {
  "id": string;
  "value": string;
};

export type CloneRequest = {
  "source_version_id": string;
};

export type CopyRevision = {
  "source_revision_id": string;
  "reason": string;
};

export type CountOptions = {
  "choice": Array<number>;
  "fill": Array<number>;
  "answer": Array<number>;
};

export type CountSetting = {
  "choice"?: Array<number>;
  "fill"?: Array<number>;
  "answer"?: Array<number>;
};

export type CreatePaperJob = {
  "theme_id": string;
  "knowledge_point_ids": Array<string>;
  "difficulty": "basic" | "standard" | "challenge";
  "question_type_counts": QuestionCounts;
  "content_epoch": number;
};

export type CsrfToken = {
  "csrf_token": string;
};

export type DailyGenerationCounts = {
  "submitted"?: number;
  "succeeded"?: number;
  "failed"?: number;
  "cancelled"?: number;
  "active_subjects"?: number;
  "date": string;
};

export type DependencyView = {
  "id": string;
  "kind": "knowledge_revision" | "objective_revision";
  "name": string;
  "description": string;
  "content_hash": string;
  "status": string;
  "lock_version": number;
};

export type DisableRequest = {
  "reason": string;
};

export type DraftDetail = {
  "id": string;
  "version_no": number;
  "status": "draft" | "published" | "retired";
  "lock_version": number;
  "content_hash": string;
  "updated_at": string;
  "question_type"?: "answer" | "fill" | "choice";
  "template_id": string;
  "generator_key": string;
  "generator_version": string;
  "objective_code": string;
  "editable": boolean;
  "config": DraftEdit;
};

export type DraftEdit = {
  "profiles": Array<MultiplicationProfile>;
  "test_cases": Array<FixedCaseInput>;
};

export type Envelope_AdminPaperDetail_ = {
  "data": AdminPaperDetail;
  "request_id": string;
};

export type Envelope_AdminPaperList_ = {
  "data": AdminPaperList;
  "request_id": string;
};

export type Envelope_AdminSessionCreated_ = {
  "data": AdminSessionCreated;
  "request_id": string;
};

export type Envelope_AdminSessionView_ = {
  "data": AdminSessionView;
  "request_id": string;
};

export type Envelope_CatalogList_ = {
  "data": CatalogList;
  "request_id": string;
};

export type Envelope_CsrfToken_ = {
  "data": CsrfToken;
  "request_id": string;
};

export type Envelope_DraftDetail_ = {
  "data": DraftDetail;
  "request_id": string;
};

export type Envelope_EventResult_ = {
  "data": EventResult;
  "request_id": string;
};

export type Envelope_Health_ = {
  "data": Health;
  "request_id": string;
};

export type Envelope_OperationList_ = {
  "data": OperationList;
  "request_id": string;
};

export type Envelope_SettingList_ = {
  "data": SettingList;
  "request_id": string;
};

export type Envelope_TemplateDetail_ = {
  "data": TemplateDetail;
  "request_id": string;
};

export type Envelope_TemplateList_ = {
  "data": TemplateList;
  "request_id": string;
};

export type Envelope_UserSessionCreated_ = {
  "data": UserSessionCreated;
  "request_id": string;
};

export type Envelope_UserSessionView_ = {
  "data": UserSessionView;
  "request_id": string;
};

export type Envelope_ValidationList_ = {
  "data": ValidationList;
  "request_id": string;
};

export type Envelope_ValidationView_ = {
  "data": ValidationView;
  "request_id": string;
};

export type ErrorCode = "INVALID_CONFIG" | "NOT_FOUND" | "INTERNAL_ERROR" | "SESSION_EXPIRED" | "CSRF_INVALID" | "IDEMPOTENCY_CONFLICT" | "CAPABILITY_CHANGED" | "EDIT_CONFLICT" | "ACTIVE_JOB_EXISTS" | "CONTENT_UNAVAILABLE" | "UNSUPPORTED_COMBINATION" | "GENERATION_COOLDOWN" | "RATE_LIMITED" | "QUEUE_FULL" | "DATABASE_BUSY" | "GENERATION_EXHAUSTED" | "ENGINE_TIMEOUT" | "WORKER_LOST" | "JOB_NOT_CANCELLABLE" | "FILE_UNAVAILABLE" | "LOGIN_FAILED" | "ORIGIN_INVALID" | "SERVICE_NOT_READY";

export type ErrorDetail = {
  "code": ErrorCode;
  "message": string;
  "details": Record<string, unknown>;
};

export type ErrorResponse = {
  "error": ErrorDetail;
  "request_id": string;
};

export type EventBatch = {
  "events": Array<Record<string, unknown>>;
};

export type EventInput = {
  "event_id": string;
  "type": "preview" | "print_intent";
  "paper_id": string;
  "occurred_at"?: string | null;
  "payload": EventPayload;
};

export type EventPayload = {
  "answer_mode": "student" | "solution";
};

export type EventRejection = {
  "event_id": string | null;
  "code": "INVALID_CONFIG" | "NOT_FOUND" | "EVENT_CONFLICT";
};

export type EventResult = {
  "accepted_ids": Array<string>;
  "duplicate_ids": Array<string>;
  "rejected": Array<EventRejection>;
};

export type ExplanationStep = {
  "blocks": Array<TextBlock | MathBlock>;
};

export type FailureSample = {
  "difficulty": "basic" | "standard" | "challenge";
  "case_code"?: string | null;
  "seed"?: string | null;
  "params"?: MultiplicationParams | null;
  "error_code": string;
  "message": string;
};

export type FixedCaseInput = {
  "code": string;
  "difficulty": "basic" | "standard" | "challenge";
  "params": MultiplicationParams;
  "expected_answer": string;
};

export type GenerationCounts = {
  "submitted"?: number;
  "succeeded"?: number;
  "failed"?: number;
  "cancelled"?: number;
  "active_subjects"?: number;
};

export type GenerationSetting = {
  "queue_limit"?: number;
  "ip_accept_limit"?: number;
};

export type GeneratorChoice = {
  "id": string;
  "key": string;
  "version": string;
  "available": boolean;
  "question_types": Array<string>;
  "difficulties": Array<string>;
  "objective_revision_ids": Array<string>;
  "default_config": DraftEdit;
  "task_configs": Record<string, DraftEdit>;
  "task_objective_revision_ids": Record<string, Array<string>>;
};

export type Health = {
  "status"?: string;
  "server_now": string;
};

export type KnowledgeContent = {
  "name": string;
  "aliases"?: Array<string>;
  "definition": string;
  "boundary": string;
  "misconceptions"?: Array<string>;
  "source_id"?: string | null;
};

export type KnowledgeCreate = {
  "code": string;
  "domain": "number" | "operation" | "geometry" | "model" | "statistics" | "practice";
  "content": KnowledgeContent;
  "reason": string;
};

export type KnowledgeDetail = {
  "id": string;
  "code": string;
  "domain": string;
  "status": "draft" | "active" | "disabled";
  "current_revision_id": string | null;
  "lock_version": number;
  "revisions": Array<KnowledgeView>;
};

export type KnowledgeEdit = {
  "name": string;
  "aliases"?: Array<string>;
  "definition": string;
  "boundary": string;
  "misconceptions"?: Array<string>;
  "source_id"?: string | null;
  "reason": string;
};

export type KnowledgeList = {
  "items": Array<KnowledgeDetail>;
  "total": number;
  "offset": number;
  "limit": number;
};

export type KnowledgeView = {
  "id": string;
  "revision_no": number;
  "status": "draft" | "published";
  "lock_version": number;
  "content_hash": string;
  "content": KnowledgeContent;
};

export type MappingEdit = {
  "items": Array<MappingItem>;
  "reason": string;
};

export type MappingItem = {
  "knowledge_revision_id": string;
  "role"?: "primary" | "review";
};

export type MappingView = {
  "node_id": string;
  "lock_version": number;
  "items": Array<MappingItem>;
};

export type MathBlock = {
  "type"?: "math";
  "latex": string;
};

export type MultiplicationParams = {
  "a": number;
  "b": number;
};

export type MultiplicationProfile = {
  "task"?: "product" | "missing_digit" | "error_choice" | "correction" | "zero_product";
  "difficulty": "basic" | "standard" | "challenge";
  "a_min": number;
  "a_max": number;
  "b_min": number;
  "b_max": number;
  "allow_zero": boolean;
  "max_carry_events": number;
  "max_per_paper"?: number;
  "layout"?: QuestionLayout;
};

export type MultiplicationQuestion = {
  "schema_version"?: 1;
  "id": string;
  "position": number;
  "question_type"?: "answer" | "fill" | "choice";
  "render_mode"?: "vertical" | "direct";
  "difficulty": "basic" | "standard" | "challenge";
  "primary_knowledge_code"?: "O002" | "O003";
  "stem_blocks": Array<TextBlock | MathBlock>;
  "options"?: Array<ChoiceOption>;
  "answer": NumericAnswer | ChoiceAnswer;
  "explanation_steps": Array<ExplanationStep>;
  "layout": QuestionLayout;
  "render_spec": VerticalMultiplication;
};

export type NodeCreate = {
  "code": string;
  "name": string;
  "parent_id"?: string | null;
  "node_type"?: "theme" | "group";
  "sort_order"?: number;
  "reason": string;
};

export type NodeEdit = {
  "name"?: string | null;
  "parent_id"?: string | null;
  "sort_order"?: number | null;
  "status"?: "draft" | "active" | "disabled" | null;
  "reason": string;
};

export type NodeState = {
  "reason": string;
  "status": "draft" | "active" | "disabled";
};

export type NodeView = {
  "id": string;
  "catalog_id": string;
  "code": string;
  "sort_order": number;
  "name": string;
  "parent_id": string | null;
  "node_type": "theme" | "group";
  "status": "draft" | "active" | "disabled";
  "lock_version": number;
};

export type NoticeCreate = {
  "question_id"?: string | null;
  "severity": "info" | "error";
  "action": "notice" | "withdraw";
  "message": string;
  "reason": string;
};

export type NoticeView = {
  "id": string;
  "question_id": string | null;
  "severity": "info" | "error";
  "action": "notice" | "withdraw";
  "message": string;
  "created_at": string;
};

export type NumericAnswer = {
  "kind"?: "numeric";
  "value": string;
  "unit"?: null;
  "precision_requirement"?: "exact_integer";
};

export type ObjectiveContent = {
  "knowledge_revision_id": string;
  "name": string;
  "scope": string;
  "success_criteria": Array<string>;
  "allowed_prerequisites"?: Array<string>;
};

export type ObjectiveCreate = {
  "code": string;
  "content": ObjectiveContent;
  "reason": string;
};

export type ObjectiveDetail = {
  "id": string;
  "point_id": string;
  "code": string;
  "status": "draft" | "active" | "disabled";
  "current_revision_id": string | null;
  "lock_version": number;
  "revisions": Array<ObjectiveView>;
};

export type ObjectiveEdit = {
  "knowledge_revision_id": string;
  "name": string;
  "scope": string;
  "success_criteria": Array<string>;
  "allowed_prerequisites"?: Array<string>;
  "reason": string;
};

export type ObjectiveList = {
  "items": Array<ObjectiveDetail>;
  "total": number;
  "offset": number;
  "limit": number;
};

export type ObjectiveView = {
  "id": string;
  "revision_no": number;
  "status": "draft" | "published";
  "lock_version": number;
  "content_hash": string;
  "content": ObjectiveContent;
};

export type OperationList = {
  "date_from": string;
  "date_to": string;
  "items": Array<OperationView>;
  "next_cursor": string | null;
  "has_more": boolean;
};

export type OperationView = {
  "id": string;
  "admin_id": string;
  "action": string;
  "target_type": string;
  "target_id": string;
  "request_id": string;
  "before_summary": Record<string, unknown> | Array<unknown> | null;
  "after_summary": Record<string, unknown> | Array<unknown> | null;
  "reason": string | null;
  "created_at": string;
};

export type PaperDetail = {
  "status"?: "active" | "withdrawn";
  "notices"?: Array<NoticeView>;
  "id": string;
  "title": string;
  "difficulty": "basic" | "standard" | "challenge";
  "total_count": number;
  "catalog_name": string;
  "theme_name": string;
  "question_type_counts": QuestionCounts;
  "generated_at": string;
  "files": Array<PaperFile>;
  "questions": Array<MultiplicationQuestion>;
  "selection": PaperSelection;
};

export type PaperFile = {
  "id": string;
  "kind": "student_pdf" | "solution_pdf";
  "pages": number;
  "byte_size": number;
};

export type PaperJobList = {
  "items": Array<PaperJobView>;
  "next_cursor": string | null;
  "has_more": boolean;
};

export type PaperJobView = {
  "id": string;
  "status": "queued" | "running" | "succeeded" | "failed" | "cancelled";
  "phase": "queued" | "generating" | "rendering" | "saving" | "done";
  "attempt": number;
  "progress_done": number;
  "progress_total": number;
  "created_at": string;
  "finished_at": string | null;
  "error_code": string | null;
  "error_message": string | null;
  "paper_id": string | null;
};

export type PaperList = {
  "items": Array<PaperSummary>;
  "next_cursor": string | null;
  "has_more": boolean;
};

export type PaperSelection = {
  "theme_id": string;
  "knowledge_point_ids": Array<string>;
  "difficulty": "basic" | "standard" | "challenge";
  "catalog_id": string;
  "question_type_counts": QuestionCounts;
};

export type PaperSummary = {
  "status"?: "active" | "withdrawn";
  "notices"?: Array<NoticeView>;
  "id": string;
  "title": string;
  "difficulty": "basic" | "standard" | "challenge";
  "total_count": number;
  "catalog_name": string;
  "theme_name": string;
  "question_type_counts": QuestionCounts;
  "generated_at": string;
  "files": Array<PaperFile>;
};

export type PointCapabilities = {
  "point": PointView;
  "lock_version": number;
  "policies": Array<PolicyCell>;
};

export type PointView = {
  "id": string;
  "code": string;
  "name": string;
};

export type PolicyCell = {
  "difficulty": "basic" | "standard" | "challenge";
  "question_type": "choice" | "fill" | "answer";
  "count_options": Array<number>;
  "default_count": number | null;
  "supported_count_options": Array<number>;
  "effective_count_options": Array<number>;
  "evidence_version_ids": Array<string>;
  "unavailable_reason": string | null;
};

export type PolicyEdit = {
  "reason": string;
  "policies": Array<QuantityPolicy>;
};

export type PreviewList = {
  "items": Array<PreviewView>;
};

export type PreviewRequest = {
  "lock_version": number;
  "content_hash": string;
  "difficulty": "basic" | "standard" | "challenge";
  "count": number;
  "seed": string;
};

export type PreviewView = {
  "id": string;
  "template_version_id": string;
  "content_hash": string;
  "status": "queued" | "running" | "succeeded" | "failed" | "cancelled";
  "attempt": number;
  "created_at": string;
  "stale": boolean;
  "error_code": string | null;
  "questions": Array<MultiplicationQuestion>;
};

export type ProfileCoverage = {
  "difficulty": "basic" | "standard" | "challenge";
  "exact_capacity": number;
  "random_cases": number;
  "papers_per_count": number;
  "checked_count_options": Array<number>;
};

export type PublishRequest = {
  "version_id": string;
  "validation_run_id": string;
  "review_id": string;
  "reason": string;
};

export type QuantityPolicy = {
  "difficulty": "basic" | "standard" | "challenge";
  "question_type": "choice" | "fill" | "answer";
  "count_options": Array<number>;
  "default_count": number | null;
};

export type QuestionCounts = {
  "choice": number;
  "fill": number;
  "answer": number;
};

export type QuestionLayout = {
  "questions_per_row"?: number;
  "solutions_per_row"?: number;
  "answer_space_mm"?: number;
  "keep_together"?: true;
  "diagram_size_mm"?: null;
};

export type QueueCounts = {
  "queued"?: number;
  "running"?: number;
};

export type ReleaseContext = {
  "template_id": string;
  "template_lock_version": number;
  "template_status": string;
  "current_published_version_id": string | null;
  "dependencies": Array<DependencyView>;
  "reviews": Array<ReviewView>;
};

export type ReleaseView = {
  "id": string;
  "template_id": string;
  "action": string;
  "epoch": number;
  "created_at": string;
};

export type RetentionSetting = {
  "enabled"?: false;
};

export type ReviewRequest = {
  "validation_run_id": string;
  "content_hash": string;
  "decision": "approved" | "rejected";
  "comment": string;
  "sample_refs": Array<string>;
  "print_checked": boolean;
};

export type ReviewView = {
  "id": string;
  "validation_run_id": string;
  "content_hash": string;
  "decision": "approved" | "rejected";
  "comment": string;
  "sample_refs": Array<string>;
  "print_checked": boolean;
  "reviewed_at": string;
};

export type RevisionApproval = {
  "content_hash": string;
  "reason": string;
};

export type RevisionOption = {
  "id": string;
  "point_id": string;
  "code": string;
  "name": string;
  "revision_no": number;
  "status": "draft" | "published";
};

export type RevisionOptions = {
  "items": Array<RevisionOption>;
  "total": number;
  "offset": number;
  "limit": number;
};

export type SettingEdit = {
  "value": CountSetting | GenerationSetting | RetentionSetting;
  "schema_version": 1;
  "reason": string;
};

export type SettingList = {
  "items": Array<SettingView>;
};

export type SettingView = {
  "key": "question_count_options" | "generation_limits" | "retention_policy";
  "value": CountSetting | GenerationSetting | RetentionSetting;
  "schema_version"?: 1;
  "lock_version": number;
  "updated_at": string | null;
};

export type SourceEdit = {
  "title": string;
  "publisher"?: string | null;
  "url"?: string | null;
  "reference_note"?: string | null;
  "published_on"?: string | null;
  "checked_at"?: string | null;
  "verification_status"?: "unverified" | "reference" | "verified";
  "evidence_note"?: string | null;
  "reason": string;
};

export type SourceList = {
  "items": Array<SourceView>;
  "total": number;
  "offset": number;
  "limit": number;
};

export type SourceVersion = {
  "template_id": string;
  "version_id": string;
  "template_name": string;
};

export type SourceView = {
  "title": string;
  "publisher"?: string | null;
  "url"?: string | null;
  "reference_note"?: string | null;
  "published_on"?: string | null;
  "checked_at"?: string | null;
  "verification_status"?: "unverified" | "reference" | "verified";
  "evidence_note"?: string | null;
  "id": string;
  "lock_version": number;
};

export type TemplateCreate = {
  "task"?: "product" | "missing_digit" | "error_choice" | "correction" | "zero_product";
  "question_type"?: "answer" | "fill" | "choice";
  "code": string;
  "name": string;
  "generator_id": string;
  "objective_revision_id": string;
  "config": DraftEdit;
  "reason": string;
};

export type TemplateDetail = {
  "id": string;
  "name": string;
  "code": string;
  "versions": Array<VersionSummary>;
};

export type TemplateList = {
  "items": Array<TemplateSummary>;
  "offset": number;
  "limit": number;
  "total": number;
};

export type TemplateSummary = {
  "id": string;
  "code": string;
  "name": string;
  "status": "active" | "disabled";
  "current_published_version_id": string | null;
  "lock_version": number;
  "updated_at": string;
};

export type TextBlock = {
  "type"?: "text";
  "text": string;
};

export type UsageCounts = {
  "preview"?: number;
  "print_intent"?: number;
};

export type UserSessionCreated = {
  "user_id": string;
  "expires_at": string;
  "server_now": string;
  "next_generation_at": string | null;
  "active_job_id": string | null;
  "can_generate": boolean;
  "csrf_token": string;
};

export type UserSessionView = {
  "user_id": string;
  "expires_at": string;
  "server_now": string;
  "next_generation_at": string | null;
  "active_job_id": string | null;
  "can_generate": boolean;
};

export type ValidationList = {
  "items": Array<ValidationView>;
};

export type ValidationReport = {
  "result": "passed" | "failed";
  "sample_count": number;
  "failure_count": number;
  "failures_truncated": boolean;
  "coverage": Array<ProfileCoverage>;
  "failures": Array<FailureSample>;
  "samples"?: Array<MultiplicationQuestion>;
  "human_review"?: "pending";
  "pdf_review"?: "pending";
};

export type ValidationRequest = {
  "lock_version": number;
  "content_hash": string;
};

export type ValidationView = {
  "id": string;
  "job_id": string;
  "template_version_id": string;
  "content_hash": string;
  "status": "queued" | "running" | "passed" | "failed" | "stale";
  "job_status": "queued" | "running" | "succeeded" | "failed" | "cancelled";
  "attempt": number;
  "error_code": string | null;
  "created_at": string;
  "finished_at": string | null;
  "report": ValidationReport | null;
};

export type VersionSummary = {
  "id": string;
  "version_no": number;
  "status": "draft" | "published" | "retired";
  "lock_version": number;
  "content_hash": string;
  "updated_at": string;
};

export type VerticalMultiplication = {
  "incorrect_tens_partial"?: string | null;
  "incorrect_result"?: string | null;
  "missing_digit_index"?: 1 | null;
  "kind"?: "integer_multiplication";
  "multiplicand": string;
  "multiplier": string;
  "ones_partial": string;
  "tens_partial": string;
  "tens_shift"?: 1;
  "result": string;
};
