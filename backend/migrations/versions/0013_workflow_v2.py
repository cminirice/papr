"""Two-level content and attempt-fenced multi-rule jobs."""
from alembic import op
import sqlalchemy as sa
revision="0013"
down_revision="0012"
branch_labels=None
depends_on=None

def upgrade():
    op.execute('\nCREATE TABLE v2_component_state (\n\t"key" TEXT NOT NULL, \n\tenabled INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE ("key")\n)\n\n')
    op.execute("\nCREATE TABLE v2_directory (\n\tparent_id TEXT, \n\tcode TEXT NOT NULL, \n\tname TEXT NOT NULL, \n\tdescription TEXT NOT NULL, \n\tsort INTEGER NOT NULL, \n\tstatus TEXT NOT NULL, \n\trevision INTEGER NOT NULL, \n\tcomponents TEXT NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (status IN ('草稿','启用','停用')), \n\tCHECK (json_valid(components)), \n\tUNIQUE (parent_id, code), \n\tFOREIGN KEY(parent_id) REFERENCES v2_directory (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE UNIQUE INDEX uq_v2_root_code ON v2_directory (code) WHERE parent_id IS NULL')
    op.execute('\nCREATE TABLE v2_template (\n\tcode TEXT NOT NULL, \n\tpublished_id TEXT, \n\tenabled INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (code)\n)\n\n')
    op.execute('\nCREATE TABLE v2_audit (\n\tadmin_id TEXT NOT NULL, \n\taction TEXT NOT NULL, \n\tentity_id TEXT NOT NULL, \n\tdetail TEXT NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(admin_id) REFERENCES admin_user (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('\nCREATE TABLE v2_version (\n\ttemplate_id TEXT NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tsealed INTEGER NOT NULL, \n\tcontent TEXT NOT NULL, \n\tcontent_hash TEXT NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (template_id, number), \n\tCHECK (json_valid(content)), \n\tFOREIGN KEY(template_id) REFERENCES v2_template (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('CREATE UNIQUE INDEX uq_v2_draft ON v2_version (template_id) WHERE sealed = 0')
    op.execute('\nCREATE TABLE v2_task (\n\tuser_id TEXT, \n\tadmin_id TEXT, \n\tkind TEXT NOT NULL, \n\tversion_id TEXT NOT NULL, \n\t"key" TEXT NOT NULL, \n\trequest_hash TEXT NOT NULL, \n\t"plan" TEXT NOT NULL, \n\tstatus TEXT NOT NULL, \n\tphase TEXT NOT NULL, \n\tattempt INTEGER NOT NULL, \n\ttoken TEXT, \n\tlease_until TEXT, \n\tfinished_at TEXT, \n\tsnapshot TEXT, \n\terror TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK ((user_id IS NULL) != (admin_id IS NULL)), \n\tCHECK ((kind=\'paper\' AND user_id IS NOT NULL) OR (kind IN (\'preview\',\'validate\') AND admin_id IS NOT NULL)), \n\tCHECK (status IN (\'queued\',\'running\',\'succeeded\',\'failed\',\'cancelled\')), \n\tCHECK (attempt BETWEEN 0 AND 2), \n\tCHECK (json_valid(plan)), \n\tCHECK (snapshot IS NULL OR json_valid(snapshot)), \n\tUNIQUE (user_id, "key"), \n\tUNIQUE (admin_id, "key"), \n\tFOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(admin_id) REFERENCES admin_user (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(version_id) REFERENCES v2_version (id) ON DELETE RESTRICT\n)\n\n')
    op.execute("CREATE UNIQUE INDEX uq_v2_active_user ON v2_task (user_id) WHERE status IN ('queued','running') AND user_id IS NOT NULL")
    op.execute('CREATE INDEX ix_v2_queue ON v2_task (status, created_at)')
    op.execute("\nCREATE TABLE v2_artifact (\n\ttask_id TEXT NOT NULL, \n\tattempt INTEGER NOT NULL, \n\ttoken TEXT NOT NULL, \n\tkind TEXT NOT NULL, \n\tstatus TEXT NOT NULL, \n\tmetadata_json TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (task_id, attempt, kind), \n\tCHECK (status IN ('pending','ready','failed')), \n\tCHECK (metadata_json IS NULL OR json_valid(metadata_json)), \n\tFOREIGN KEY(task_id) REFERENCES v2_task (id) ON DELETE RESTRICT\n)\n\n")
    op.execute("CREATE UNIQUE INDEX uq_v2_ready ON v2_artifact (task_id, kind) WHERE status='ready'")
    op.execute('\nCREATE TABLE v2_review (\n\tversion_id TEXT NOT NULL, \n\tpreview_id TEXT NOT NULL, \n\tvalidation_id TEXT NOT NULL, \n\tadmin_id TEXT NOT NULL, \n\tcontent_hash TEXT NOT NULL, \n\tapproved INTEGER NOT NULL, \n\tcomment TEXT NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT NOT NULL, \n\tupdated_at TEXT NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(version_id) REFERENCES v2_version (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(preview_id) REFERENCES v2_task (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(validation_id) REFERENCES v2_task (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(admin_id) REFERENCES admin_user (id) ON DELETE RESTRICT\n)\n\n')
    op.execute("CREATE TRIGGER v2_directory_depth BEFORE INSERT ON v2_directory WHEN NEW.parent_id IS NOT NULL BEGIN SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM v2_directory WHERE id=NEW.parent_id AND parent_id IS NULL) THEN RAISE(ABORT,'directory depth') END; END")
    op.execute("CREATE TRIGGER v2_directory_parent_immutable BEFORE UPDATE OF parent_id ON v2_directory WHEN OLD.parent_id IS NOT NEW.parent_id BEGIN SELECT RAISE(ABORT,'parent immutable'); END")
    op.execute("CREATE TRIGGER v2_root_components_insert BEFORE INSERT ON v2_directory WHEN NEW.parent_id IS NULL AND NEW.components != '[]' BEGIN SELECT RAISE(ABORT,'leaf required'); END")
    op.execute("CREATE TRIGGER v2_root_components_update BEFORE UPDATE ON v2_directory WHEN NEW.parent_id IS NULL AND NEW.components != '[]' BEGIN SELECT RAISE(ABORT,'leaf required'); END")
    op.execute("CREATE TRIGGER v2_sealed_immutable BEFORE UPDATE ON v2_version WHEN OLD.sealed=1 BEGIN SELECT RAISE(ABORT,'version immutable'); END")

def downgrade():
    tables=['v2_review','v2_artifact','v2_task','v2_version','v2_template','v2_directory','v2_component_state','v2_audit']
    if any(op.get_bind().execute(sa.text('SELECT count(*) FROM '+name)).scalar_one() for name in tables):
        raise RuntimeError('已有v2内容，禁止自动降级删除历史；请使用保留的旧库回退')
    for name in tables:op.drop_table(name)
