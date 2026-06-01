CREATE TABLE "users"(
    "user_id" bigserial NOT NULL,
    "user_name" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "password_hash" VARCHAR(255) NOT NULL,
    "phone" VARCHAR(50) NULL,
    "department" VARCHAR(100) NULL,
    "job_title" VARCHAR(100) NULL,
    "location" VARCHAR(255) NULL,
    "profile_picture" VARCHAR(500) NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',
    "two_factor_enabled" BOOLEAN NOT NULL DEFAULT FALSE,
    "api_access_enabled" BOOLEAN NOT NULL DEFAULT FALSE,
    "last_login" BIGINT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "users" ADD PRIMARY KEY("user_id");
ALTER TABLE
    "users" ADD CONSTRAINT "users_email_unique" UNIQUE("email");
CREATE TABLE "roles"(
    "role_id" bigserial NOT NULL,
    "role_name" VARCHAR(255) NOT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "roles" ADD PRIMARY KEY("role_id");
ALTER TABLE
    "roles" ADD CONSTRAINT "roles_role_name_unique" UNIQUE("role_name");
CREATE TABLE "permissions"(
    "permission_id" bigserial NOT NULL,
    "permission_key" VARCHAR(100) NOT NULL,
    "permission_label" VARCHAR(255) NULL,
    "permission_description" VARCHAR(500) NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "permissions" ADD PRIMARY KEY("permission_id");
ALTER TABLE
    "permissions" ADD CONSTRAINT "permissions_permission_key_unique" UNIQUE("permission_key");
CREATE TABLE "user_roles"(
    "user_role_id" bigserial NOT NULL,
    "user_id" BIGINT NOT NULL,
    "role_id" BIGINT NOT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "user_roles" ADD PRIMARY KEY("user_role_id");
CREATE INDEX "user_roles_role_id_index" ON
    "user_roles"("role_id");
CREATE TABLE "role_permissions"(
    "role_permission_id" bigserial NOT NULL,
    "role_id" BIGINT NOT NULL,
    "permission_id" BIGINT NOT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "role_permissions" ADD PRIMARY KEY("role_permission_id");
CREATE INDEX "role_permissions_permission_id_index" ON
    "role_permissions"("permission_id");
CREATE TABLE "review_cycles"(
    "cycle_id" bigserial NOT NULL,
    "client_id" BIGINT NOT NULL,
    "review_period" VARCHAR(50) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "audit_type" VARCHAR(100) NULL,
    "priority" VARCHAR(20) NULL,
    "framework" VARCHAR(100) NULL,
    "start_date" BIGINT NOT NULL,
    "due_date" BIGINT NOT NULL,
    "end_date" BIGINT NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Draft',
    "score" DECIMAL(5, 2) NULL,
    "overview" TEXT NULL,
    "description" TEXT NULL,
    "project_lead" BIGINT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "review_cycles" ADD PRIMARY KEY("cycle_id");
CREATE INDEX "review_cycles_status_index" ON
    "review_cycles"("status");
CREATE TABLE "engagement_team"(
    "engagement_team_id" bigserial NOT NULL,
    "cycle_id" BIGINT NOT NULL,
    "user_id" BIGINT NOT NULL,
    "team_role" VARCHAR(50) NOT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "engagement_team" ADD PRIMARY KEY("engagement_team_id");
CREATE INDEX "engagement_team_user_id_index" ON
    "engagement_team"("user_id");
CREATE TABLE "versions"(
    "version_id" bigserial NOT NULL,
    "version_name" VARCHAR(255) NULL,
    "released_at" BIGINT NULL,
    "is_current" BOOLEAN NOT NULL DEFAULT FALSE,
    "description" TEXT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "versions" ADD PRIMARY KEY("version_id");
CREATE TABLE "control_repository"(
    "control_id" bigserial NOT NULL,
    "control_number" VARCHAR(255) NOT NULL,
    "version_id" BIGINT NULL,
    "control_name" VARCHAR(255) NOT NULL,
    "reference_number" VARCHAR(255) NULL,
    "entity" VARCHAR(255) NOT NULL,
    "control_desc" TEXT NOT NULL,
    "domain" VARCHAR(100) NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Active',
    "frequency" VARCHAR(50) NOT NULL,
    "risk_level" VARCHAR(50) NOT NULL,
    "pwc_reliance" VARCHAR(255) NULL,
    "control_owner" BIGINT NOT NULL,
    "units_fccg_contact" BIGINT NOT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "control_repository" ADD PRIMARY KEY("control_id");
CREATE INDEX "control_repository_control_number_index" ON
    "control_repository"("control_number");
CREATE INDEX "control_repository_domain_index" ON
    "control_repository"("domain");
CREATE INDEX "control_repository_status_index" ON
    "control_repository"("status");
CREATE TABLE "control_frameworks"(
    "control_framework_id" bigserial NOT NULL,
    "control_id" BIGINT NOT NULL,
    "framework_name" VARCHAR(100) NOT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "control_frameworks" ADD PRIMARY KEY("control_framework_id");
CREATE INDEX "control_frameworks_framework_name_index" ON
    "control_frameworks"("framework_name");
CREATE TABLE "config_controls"(
    "config_control_id" bigserial NOT NULL,
    "cycle_id" BIGINT NOT NULL,
    "control_id" BIGINT NOT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "config_controls" ADD PRIMARY KEY("config_control_id");
CREATE INDEX "config_controls_control_id_index" ON
    "config_controls"("control_id");
CREATE TABLE "control_tests_and_evidences"(
    "test_id" bigserial NOT NULL,
    "config_control_id" BIGINT NOT NULL,
    "tests" TEXT NULL,
    "note" TEXT NULL,
    "comments" TEXT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "control_tests_and_evidences" ADD PRIMARY KEY("test_id");
CREATE INDEX "control_tests_and_evidences_config_control_id_index" ON
    "control_tests_and_evidences"("config_control_id");
CREATE TABLE "evidence_files"(
    "evidence_id" bigserial NOT NULL,
    "file_name" VARCHAR(255) NOT NULL,
    "file_type" VARCHAR(50) NULL,
    "file_size" BIGINT NULL,
    "file_path" TEXT NULL,
    "upload_date" BIGINT NOT NULL,
    "uploaded_by" BIGINT NOT NULL,
    "cycle_id" BIGINT NULL,
    "control_id" BIGINT NULL,
    "test_id" BIGINT NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'Pending',
    "comments" TEXT NULL,
    "file_version" INTEGER NOT NULL DEFAULT 1,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "evidence_files" ADD PRIMARY KEY("evidence_id");
CREATE INDEX "evidence_files_uploaded_by_index" ON
    "evidence_files"("uploaded_by");
CREATE INDEX "evidence_files_cycle_id_index" ON
    "evidence_files"("cycle_id");
CREATE INDEX "evidence_files_control_id_index" ON
    "evidence_files"("control_id");
CREATE INDEX "evidence_files_status_index" ON
    "evidence_files"("status");
CREATE TABLE "control_change_log"(
    "change_id" bigserial NOT NULL,
    "control_id" BIGINT NOT NULL,
    "from_version" BIGINT NULL,
    "to_version" BIGINT NOT NULL,
    "change_type" VARCHAR(50) NOT NULL,
    "changed_by" BIGINT NOT NULL,
    "change_timestamp" BIGINT NOT NULL,
    "new_control_name" VARCHAR(255) NULL,
    "new_control_desc" TEXT NULL,
    "change_percentage" DECIMAL(5, 2) NULL,
    "is_archived" BOOLEAN NOT NULL DEFAULT FALSE,
    "note" TEXT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "control_change_log" ADD PRIMARY KEY("change_id");
CREATE INDEX "control_change_log_control_id_index" ON
    "control_change_log"("control_id");
CREATE INDEX "control_change_log_changed_by_index" ON
    "control_change_log"("changed_by");
CREATE TABLE "test_logs"(
    "log_id" bigserial NOT NULL,
    "test_id" BIGINT NULL,
    "control_id" BIGINT NULL,
    "cycle_id" BIGINT NULL,
    "log_date" BIGINT NOT NULL,
    "changed_by" BIGINT NOT NULL,
    "status" VARCHAR(50) NOT NULL,
    "execution_time_seconds" BIGINT NULL,
    "report_link" VARCHAR(255) NULL,
    "notes" TEXT NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "test_logs" ADD PRIMARY KEY("log_id");
CREATE INDEX "test_logs_test_id_index" ON
    "test_logs"("test_id");
CREATE INDEX "test_logs_control_id_index" ON
    "test_logs"("control_id");
CREATE INDEX "test_logs_cycle_id_index" ON
    "test_logs"("cycle_id");
CREATE TABLE "clients"(
    "client_id" bigserial NOT NULL,
    "client_code" VARCHAR(255) NOT NULL,
    "client_name" VARCHAR(255) NOT NULL,
    "definition_scope" TEXT NOT NULL,
    "reference_documents" TEXT NOT NULL,
    "compliance_framework" VARCHAR(255) NULL,
    "created_time" BIGINT NOT NULL,
    "updated_time" BIGINT NOT NULL
);
ALTER TABLE
    "clients" ADD PRIMARY KEY("client_id");
ALTER TABLE
    "clients" ADD CONSTRAINT "clients_client_code_unique" UNIQUE("client_code");
ALTER TABLE
    "control_change_log" ADD CONSTRAINT "control_change_log_control_id_foreign" FOREIGN KEY("control_id") REFERENCES "control_repository"("control_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "role_permissions" ADD CONSTRAINT "role_permissions_permission_id_foreign" FOREIGN KEY("permission_id") REFERENCES "permissions"("permission_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "user_roles" ADD CONSTRAINT "user_roles_role_id_foreign" FOREIGN KEY("role_id") REFERENCES "roles"("role_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "engagement_team" ADD CONSTRAINT "engagement_team_cycle_id_foreign" FOREIGN KEY("cycle_id") REFERENCES "review_cycles"("cycle_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "review_cycles" ADD CONSTRAINT "review_cycles_project_lead_foreign" FOREIGN KEY("project_lead") REFERENCES "users"("user_id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE
    "evidence_files" ADD CONSTRAINT "evidence_files_control_id_foreign" FOREIGN KEY("control_id") REFERENCES "control_repository"("control_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "test_logs" ADD CONSTRAINT "test_logs_changed_by_foreign" FOREIGN KEY("changed_by") REFERENCES "users"("user_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "engagement_team" ADD CONSTRAINT "engagement_team_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "users"("user_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "config_controls" ADD CONSTRAINT "config_controls_control_id_foreign" FOREIGN KEY("control_id") REFERENCES "control_repository"("control_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "test_logs" ADD CONSTRAINT "test_logs_control_id_foreign" FOREIGN KEY("control_id") REFERENCES "control_repository"("control_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "review_cycles" ADD CONSTRAINT "review_cycles_client_id_foreign" FOREIGN KEY("client_id") REFERENCES "clients"("client_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "test_logs" ADD CONSTRAINT "test_logs_test_id_foreign" FOREIGN KEY("test_id") REFERENCES "control_tests_and_evidences"("test_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "test_logs" ADD CONSTRAINT "test_logs_cycle_id_foreign" FOREIGN KEY("cycle_id") REFERENCES "review_cycles"("cycle_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "control_change_log" ADD CONSTRAINT "control_change_log_changed_by_foreign" FOREIGN KEY("changed_by") REFERENCES "users"("user_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "control_frameworks" ADD CONSTRAINT "control_frameworks_control_id_foreign" FOREIGN KEY("control_id") REFERENCES "control_repository"("control_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "evidence_files" ADD CONSTRAINT "evidence_files_cycle_id_foreign" FOREIGN KEY("cycle_id") REFERENCES "review_cycles"("cycle_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "evidence_files" ADD CONSTRAINT "evidence_files_test_id_foreign" FOREIGN KEY("test_id") REFERENCES "control_tests_and_evidences"("test_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "config_controls" ADD CONSTRAINT "config_controls_cycle_id_foreign" FOREIGN KEY("cycle_id") REFERENCES "review_cycles"("cycle_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "user_roles" ADD CONSTRAINT "user_roles_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "users"("user_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "evidence_files" ADD CONSTRAINT "evidence_files_uploaded_by_foreign" FOREIGN KEY("uploaded_by") REFERENCES "users"("user_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "role_permissions" ADD CONSTRAINT "role_permissions_role_id_foreign" FOREIGN KEY("role_id") REFERENCES "roles"("role_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "control_repository" ADD CONSTRAINT "control_repository_version_id_foreign" FOREIGN KEY("version_id") REFERENCES "versions"("version_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "control_change_log" ADD CONSTRAINT "control_change_log_from_version_foreign" FOREIGN KEY("from_version") REFERENCES "versions"("version_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "control_change_log" ADD CONSTRAINT "control_change_log_to_version_foreign" FOREIGN KEY("to_version") REFERENCES "versions"("version_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "control_repository" ADD CONSTRAINT "control_repository_control_owner_foreign" FOREIGN KEY("control_owner") REFERENCES "users"("user_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "control_repository" ADD CONSTRAINT "control_repository_units_fccg_contact_foreign" FOREIGN KEY("units_fccg_contact") REFERENCES "users"("user_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "user_roles" ADD CONSTRAINT "user_roles_user_id_role_id_unique" UNIQUE("user_id", "role_id");
ALTER TABLE
    "role_permissions" ADD CONSTRAINT "role_permissions_role_id_permission_id_unique" UNIQUE("role_id", "permission_id");
ALTER TABLE
    "engagement_team" ADD CONSTRAINT "engagement_team_cycle_id_user_id_unique" UNIQUE("cycle_id", "user_id");
ALTER TABLE
    "config_controls" ADD CONSTRAINT "config_controls_cycle_id_control_id_unique" UNIQUE("cycle_id", "control_id");
ALTER TABLE
    "control_frameworks" ADD CONSTRAINT "control_frameworks_control_id_framework_name_unique" UNIQUE("control_id", "framework_name");
ALTER TABLE
    "review_cycles" ADD CONSTRAINT "review_cycles_score_check" CHECK("score" >= 0 AND "score" <= 100);
ALTER TABLE
    "control_change_log" ADD CONSTRAINT "control_change_log_change_percentage_check" CHECK("change_percentage" >= 0 AND "change_percentage" <= 100);
CREATE INDEX "evidence_files_test_id_index" ON
    "evidence_files"("test_id");
CREATE INDEX "review_cycles_client_id_index" ON
    "review_cycles"("client_id");
CREATE INDEX "review_cycles_project_lead_index" ON
    "review_cycles"("project_lead");
CREATE INDEX "control_repository_version_id_index" ON
    "control_repository"("version_id");
CREATE INDEX "users_status_index" ON
    "users"("status");
CREATE INDEX "clients_client_name_index" ON
    "clients"("client_name");
ALTER TABLE
    "control_tests_and_evidences" ADD CONSTRAINT "control_tests_and_evidences_config_control_id_foreign" FOREIGN KEY("config_control_id") REFERENCES "config_controls"("config_control_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE
    "evidence_files" ADD CONSTRAINT "evidence_files_linkage_check" CHECK(
        "cycle_id" IS NOT NULL OR
        "control_id" IS NOT NULL OR
        "test_id" IS NOT NULL
    );
ALTER TABLE
    "test_logs" ADD CONSTRAINT "test_logs_linkage_check" CHECK(
        "test_id" IS NOT NULL OR
        "control_id" IS NOT NULL OR
        "cycle_id" IS NOT NULL
    );
CREATE INDEX "control_repository_control_owner_index" ON
    "control_repository"("control_owner");
CREATE INDEX "control_repository_units_fccg_contact_index" ON
    "control_repository"("units_fccg_contact");
CREATE INDEX "test_logs_changed_by_index" ON
    "test_logs"("changed_by");
CREATE INDEX "control_change_log_from_version_index" ON
    "control_change_log"("from_version");
CREATE INDEX "control_change_log_to_version_index" ON
    "control_change_log"("to_version");
CREATE UNIQUE INDEX "versions_is_current_unique" ON
    "versions"("is_current") WHERE "is_current" = TRUE;
ALTER TABLE
    "review_cycles" ADD CONSTRAINT "review_cycles_date_order_check"
    CHECK("start_date" <= "due_date");
ALTER TABLE
    "review_cycles" ADD CONSTRAINT "review_cycles_end_date_check"
    CHECK("end_date" IS NULL OR "end_date" >= "start_date");

    