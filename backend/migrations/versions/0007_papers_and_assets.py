"""Paper snapshots, private PDF assets and worker readiness."""
from alembic import op
import sqlalchemy as sa
revision = '0007'
down_revision = '0006'
branch_labels = depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE paper (
        owner_user_id TEXT NOT NULL, 
        job_id TEXT NOT NULL, 
        title TEXT NOT NULL, 
        catalog_snapshot TEXT NOT NULL, 
        config_snapshot TEXT NOT NULL, 
        difficulty TEXT NOT NULL, 
        choice_count INTEGER NOT NULL, 
        fill_count INTEGER NOT NULL, 
        answer_count INTEGER NOT NULL, 
        total_count INTEGER NOT NULL, 
        content_schema_version INTEGER NOT NULL, 
        status TEXT NOT NULL, 
        generated_at TEXT NOT NULL, 
        deleted_at TEXT, 
        id TEXT NOT NULL, 
        created_at TEXT NOT NULL, 
        updated_at TEXT NOT NULL, 
        PRIMARY KEY (id), 
        CONSTRAINT ck_paper_uuid CHECK (length(id) = 36), 
        CONSTRAINT ck_paper_created_at CHECK (length(created_at) = 32 AND substr(created_at, 27) = '+08:00'), 
        CONSTRAINT ck_paper_updated_at CHECK (length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'), 
        CONSTRAINT ck_paper_generated_at CHECK (length(generated_at) = 32 AND substr(generated_at, 27) = '+08:00'), 
        CONSTRAINT ck_paper_deleted_at CHECK (deleted_at IS NULL OR (length(deleted_at) = 32 AND substr(deleted_at, 27) = '+08:00')), 
        CONSTRAINT ck_paper_status CHECK (status IN ('active','withdrawn')), 
        CONSTRAINT ck_paper_counts CHECK (choice_count >= 0 AND fill_count >= 0 AND answer_count >= 0 AND total_count > 0 AND total_count = choice_count + fill_count + answer_count), 
        CONSTRAINT ck_paper_json CHECK (json_valid(catalog_snapshot) AND json_valid(config_snapshot)), 
        FOREIGN KEY(owner_user_id) REFERENCES app_user (id) ON DELETE RESTRICT, 
        UNIQUE (job_id), 
        FOREIGN KEY(job_id) REFERENCES job (id) ON DELETE RESTRICT
    )
    """)
    op.execute('CREATE INDEX ix_paper_owner_generated ON paper (owner_user_id, generated_at, id)')
    op.execute("""
    CREATE TABLE question (
        source_type TEXT NOT NULL, 
        template_version_id TEXT NOT NULL, 
        profile_id TEXT NOT NULL, 
        generator_id TEXT NOT NULL, 
        question_type TEXT NOT NULL, 
        difficulty TEXT NOT NULL, 
        render_mode TEXT NOT NULL, 
        content_schema_version INTEGER NOT NULL, 
        content_snapshot TEXT NOT NULL, 
        answer_snapshot TEXT NOT NULL, 
        explanation_snapshot TEXT NOT NULL, 
        layout_snapshot TEXT NOT NULL, 
        generation_params TEXT NOT NULL, 
        seed TEXT NOT NULL, 
        semantic_signature TEXT NOT NULL, 
        status TEXT NOT NULL, 
        id TEXT NOT NULL, 
        created_at TEXT NOT NULL, 
        updated_at TEXT NOT NULL, 
        PRIMARY KEY (id), 
        CONSTRAINT ck_question_uuid CHECK (length(id) = 36), 
        CONSTRAINT ck_question_created_at CHECK (length(created_at) = 32 AND substr(created_at, 27) = '+08:00'), 
        CONSTRAINT ck_question_updated_at CHECK (length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'), 
        CONSTRAINT ck_question_source CHECK (source_type = 'generated' AND length(seed) = 32), 
        CONSTRAINT ck_question_status CHECK (status IN ('active','flagged','withdrawn')), 
        CONSTRAINT ck_question_json CHECK (json_valid(content_snapshot) AND json_valid(answer_snapshot) AND json_valid(explanation_snapshot) AND json_valid(layout_snapshot) AND json_valid(generation_params)), 
        FOREIGN KEY(template_version_id) REFERENCES template_version (id) ON DELETE RESTRICT, 
        FOREIGN KEY(profile_id) REFERENCES template_profile (id) ON DELETE RESTRICT, 
        FOREIGN KEY(generator_id) REFERENCES generator_definition (id) ON DELETE RESTRICT
    )
    """)
    op.execute('CREATE INDEX ix_question_signature ON question (semantic_signature)')
    op.execute('CREATE INDEX ix_question_template ON question (template_version_id, created_at)')
    op.execute("""
    CREATE TABLE question_knowledge (
        question_id TEXT NOT NULL, 
        knowledge_revision_id TEXT NOT NULL, 
        objective_revision_id TEXT NOT NULL, 
        role TEXT NOT NULL, 
        id TEXT NOT NULL, 
        created_at TEXT NOT NULL, 
        updated_at TEXT NOT NULL, 
        PRIMARY KEY (id), 
        CONSTRAINT ck_question_knowledge_uuid CHECK (length(id) = 36), 
        CONSTRAINT ck_question_knowledge_created_at CHECK (length(created_at) = 32 AND substr(created_at, 27) = '+08:00'), 
        CONSTRAINT ck_question_knowledge_updated_at CHECK (length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'), 
        CONSTRAINT uq_question_knowledge UNIQUE (question_id, knowledge_revision_id, role), 
        CONSTRAINT ck_question_knowledge_role CHECK (role IN ('primary','secondary','prerequisite')), 
        FOREIGN KEY(question_id) REFERENCES question (id) ON DELETE RESTRICT, 
        FOREIGN KEY(knowledge_revision_id) REFERENCES knowledge_revision (id) ON DELETE RESTRICT, 
        FOREIGN KEY(objective_revision_id) REFERENCES objective_revision (id) ON DELETE RESTRICT
    )
    """)
    op.execute("""
    CREATE TABLE paper_question (
        paper_id TEXT NOT NULL, 
        question_id TEXT NOT NULL, 
        position INTEGER NOT NULL, 
        section TEXT NOT NULL, 
        section_position INTEGER NOT NULL, 
        semantic_signature TEXT NOT NULL, 
        id TEXT NOT NULL, 
        created_at TEXT NOT NULL, 
        updated_at TEXT NOT NULL, 
        PRIMARY KEY (id), 
        CONSTRAINT ck_paper_question_uuid CHECK (length(id) = 36), 
        CONSTRAINT ck_paper_question_created_at CHECK (length(created_at) = 32 AND substr(created_at, 27) = '+08:00'), 
        CONSTRAINT ck_paper_question_updated_at CHECK (length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'), 
        CONSTRAINT uq_paper_position UNIQUE (paper_id, position), 
        CONSTRAINT uq_paper_question UNIQUE (paper_id, question_id), 
        CONSTRAINT uq_paper_signature UNIQUE (paper_id, semantic_signature), 
        CONSTRAINT ck_paper_question_position CHECK (position > 0 AND section_position > 0), 
        FOREIGN KEY(paper_id) REFERENCES paper (id) ON DELETE RESTRICT, 
        FOREIGN KEY(question_id) REFERENCES question (id) ON DELETE RESTRICT
    )
    """)
    op.execute("""
    CREATE TABLE file_asset (
        owner_user_id TEXT NOT NULL, 
        job_id TEXT NOT NULL, 
        paper_id TEXT, 
        attempt INTEGER NOT NULL, 
        lease_token TEXT NOT NULL, 
        kind TEXT NOT NULL, 
        storage_key TEXT NOT NULL, 
        mime_type TEXT NOT NULL, 
        byte_size INTEGER, 
        sha256 TEXT, 
        pages INTEGER, 
        renderer_version TEXT, 
        metadata_json TEXT, 
        status TEXT NOT NULL, 
        error_code TEXT, 
        id TEXT NOT NULL, 
        created_at TEXT NOT NULL, 
        updated_at TEXT NOT NULL, 
        PRIMARY KEY (id), 
        CONSTRAINT ck_file_asset_uuid CHECK (length(id) = 36), 
        CONSTRAINT ck_file_asset_created_at CHECK (length(created_at) = 32 AND substr(created_at, 27) = '+08:00'), 
        CONSTRAINT ck_file_asset_updated_at CHECK (length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'), 
        CONSTRAINT ck_asset_kind CHECK (kind IN ('student_pdf','solution_pdf')), 
        CONSTRAINT ck_asset_status CHECK (status IN ('pending','ready','failed','deleted')), 
        CONSTRAINT ck_asset_attempt CHECK (attempt BETWEEN 1 AND 2 AND length(lease_token) = 36), 
        CONSTRAINT ck_asset_ready CHECK (status != 'ready' OR (paper_id IS NOT NULL AND byte_size IS NOT NULL AND byte_size > 0 AND sha256 IS NOT NULL AND length(sha256) = 64 AND renderer_version IS NOT NULL AND pages IS NOT NULL AND pages > 0 AND metadata_json IS NOT NULL)), 
        CONSTRAINT ck_asset_json CHECK (metadata_json IS NULL OR json_valid(metadata_json)), 
        CONSTRAINT uq_asset_attempt_kind UNIQUE (job_id, attempt, kind), 
        FOREIGN KEY(owner_user_id) REFERENCES app_user (id) ON DELETE RESTRICT, 
        FOREIGN KEY(job_id) REFERENCES job (id) ON DELETE RESTRICT, 
        FOREIGN KEY(paper_id) REFERENCES paper (id) ON DELETE RESTRICT, 
        UNIQUE (storage_key)
    )
    """)
    op.execute('CREATE INDEX ix_asset_job ON file_asset (job_id, status)')
    op.execute("CREATE UNIQUE INDEX uq_asset_ready_kind ON file_asset (paper_id, kind) WHERE status = 'ready'")
    op.execute("""
    CREATE TABLE pdf_worker_state (
        id INTEGER NOT NULL, 
        config_hash TEXT NOT NULL, 
        ready_until TEXT NOT NULL, 
        PRIMARY KEY (id), 
        CONSTRAINT ck_pdf_worker_singleton CHECK (id = 1)
    )
    """)


def downgrade():
    if any(op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {name}')) for name in ('paper', 'file_asset')):
        raise RuntimeError('0007已有试卷或资产记录，禁止自动降级删除历史')
    op.drop_table('pdf_worker_state')
    op.drop_table('file_asset')
    op.drop_table('paper_question')
    op.drop_table('question_knowledge')
    op.drop_table('question')
    op.drop_table('paper')
