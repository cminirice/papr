"""从后端DTO导出会话、出卷请求及首个内容类型；--check用于检查漂移。"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from pydantic import BaseModel
from app.schemas.common import Envelope, Health, ErrorResponse
from app.schemas.identity import UserSessionView, UserSessionCreated, AdminSessionView, AdminSessionCreated, AdminLogin, CsrfToken
from app.schemas.generation import CreatePaperJob
from app.schemas.content import MultiplicationQuestion, MultiplicationProfile
from app.schemas.catalog import CatalogList, TemplateList
from app.schemas.template_edit import DraftEdit, DraftDetail, TemplateDetail
from app.schemas.validation import ValidationRequest, ValidationView, ValidationList
from app.schemas.releases import ReviewRequest, ReviewView, RevisionApproval, PublishRequest, DisableRequest, ReleaseContext, ReleaseView, CloneRequest
from app.schemas.capabilities import (CatalogState, NodeState, NodeView, PointView, PointCapabilities, PolicyEdit, CapabilitySelection, CapabilityView)
from app.schemas.paper_jobs import PaperJobView, PaperJobList
from app.schemas.papers import PaperSummary, PaperDetail, PaperList
from app.schemas.admin_operations import AdminJobList, AdminJobDetail, AdminOverview
from app.schemas.catalog_edit import CatalogCreate, CatalogDetail, CatalogEdit, NodeCreate, NodeEdit, MappingEdit, MappingView, RevisionOptions
from app.schemas.knowledge_edit import SourceEdit, SourceList, KnowledgeCreate, ObjectiveCreate, KnowledgeEdit, ObjectiveEdit, CopyRevision, KnowledgeList, ObjectiveList
from app.schemas.template_tools import GeneratorChoice, TemplateCreate, PreviewRequest, PreviewList
from app.schemas.paper_admin import AdminPaperList, AdminPaperDetail, NoticeCreate
from app.schemas.settings import SettingList, SettingEdit, SettingView
from app.schemas.audit import OperationList
from app.schemas.events import EventInput, EventBatch, EventResult
from app.main import create_app


class Contracts(BaseModel):
    event_input: EventInput
    event_batch: EventBatch
    event_result: Envelope[EventResult]
    operation_list: Envelope[OperationList]
    settings: Envelope[SettingList]
    setting_edit: SettingEdit
    setting_view: SettingView
    admin_papers: Envelope[AdminPaperList]
    admin_paper: Envelope[AdminPaperDetail]
    notice_create: NoticeCreate
    user_session: Envelope[UserSessionView]
    user_bootstrap: Envelope[UserSessionCreated]
    admin_session: Envelope[AdminSessionView]
    admin_login_response: Envelope[AdminSessionCreated]
    admin_login_request: AdminLogin
    csrf: Envelope[CsrfToken]
    health: Envelope[Health]
    paper_request: CreatePaperJob
    error: ErrorResponse
    multiplication_question: MultiplicationQuestion
    multiplication_profile: MultiplicationProfile
    catalog_list: Envelope[CatalogList]
    template_list: Envelope[TemplateList]
    template_detail: Envelope[TemplateDetail]
    draft_detail: Envelope[DraftDetail]
    draft_edit: DraftEdit
    validation_request: ValidationRequest
    validation_view: Envelope[ValidationView]
    validation_list: Envelope[ValidationList]
    review_request: ReviewRequest
    review_view: ReviewView
    revision_approval: RevisionApproval
    publish_request: PublishRequest
    disable_request: DisableRequest
    release_context: ReleaseContext
    release_view: ReleaseView
    clone_request: CloneRequest
    catalog_state: CatalogState
    node_state: NodeState
    node_view: NodeView
    point_view: PointView
    point_capabilities: PointCapabilities
    policy_edit: PolicyEdit
    capability_selection: CapabilitySelection
    capability_view: CapabilityView
    paper_job_view: PaperJobView
    paper_job_list: PaperJobList
    paper_summary: PaperSummary
    paper_detail: PaperDetail
    paper_list: PaperList
    admin_job_list: AdminJobList
    admin_job_detail: AdminJobDetail
    admin_overview: AdminOverview
    catalog_create: CatalogCreate
    catalog_detail: CatalogDetail
    catalog_edit: CatalogEdit
    node_create: NodeCreate
    node_edit: NodeEdit
    mapping_edit: MappingEdit
    mapping_view: MappingView
    revision_options: RevisionOptions
    source_edit: SourceEdit
    source_list: SourceList
    knowledge_create: KnowledgeCreate
    objective_create: ObjectiveCreate
    knowledge_edit: KnowledgeEdit
    objective_edit: ObjectiveEdit
    copy_revision: CopyRevision
    knowledge_list: KnowledgeList
    objective_list: ObjectiveList
    generator_choice: GeneratorChoice
    template_create: TemplateCreate
    preview_request: PreviewRequest
    preview_list: PreviewList


def ts_type(schema):
    if '$ref' in schema:
        return schema['$ref'].rsplit('/', 1)[-1]
    if 'enum' in schema:
        return ' | '.join(json.dumps(v, ensure_ascii=False) for v in schema['enum'])
    if 'const' in schema:
        return json.dumps(schema['const'], ensure_ascii=False)
    if 'oneOf' in schema:
        return ' | '.join(ts_type(s) for s in schema['oneOf'])
    if 'anyOf' in schema:
        return ' | '.join(ts_type(s) for s in schema['anyOf'])
    kind = schema.get('type')
    if kind in {'integer', 'number'}:
        return 'number'
    if kind in {'string', 'boolean', 'null'}:
        return kind
    if kind == 'array':
        return f"Array<{ts_type(schema['items'])}>"
    if kind == 'object':
        required = set(schema.get('required', []))
        lines = [f"  {json.dumps(k)}{'' if k in required else '?'}: {ts_type(v)};" for k, v in schema.get('properties', {}).items()]
        additional = schema.get('additionalProperties')
        if additional is not False and not lines:
            return 'Record<string, unknown>' if additional in (None, True, {}) else f'Record<string, {ts_type(additional)}>'
        return '{\n' + '\n'.join(lines) + '\n}'
    if not schema:
        return 'unknown'
    raise ValueError(f'未支持的schema：{schema}')


def artifacts():
    schema = Contracts.model_json_schema(mode='serialization')
    declarations = ['// 由scripts/export_contracts.py生成；请勿手动修改。\n']
    for name, definition in sorted(schema['$defs'].items()):
        declarations.append(f'export type {name} = {ts_type(definition)};\n')
    app = create_app()
    try:
        openapi = app.openapi()
    finally:
        app.state.engine.dispose()
    return {
        ROOT / 'frontend-shared/src/api.generated.ts': '\n'.join(declarations),
        ROOT / 'docs/contracts/identity-v1.schema.json': json.dumps(schema, ensure_ascii=False, indent=2) + '\n',
        ROOT / 'docs/contracts/openapi.json': json.dumps(openapi, ensure_ascii=False, indent=2) + '\n',
        ROOT / 'docs/contracts/multiplication-v1.schema.json': json.dumps(
            MultiplicationQuestion.model_json_schema(mode='serialization'), ensure_ascii=False, indent=2) + '\n',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for path, content in artifacts().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f'契约产物需要更新：{path.relative_to(ROOT)}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    print('共享契约与OpenAPI检查通过' if args.check else '已导出共享契约与OpenAPI')


if __name__ == '__main__':
    main()
