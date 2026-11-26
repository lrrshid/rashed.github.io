-- Settings > connections: the company directory (LDAP) and the main database, managed from the website (ported from
-- the Asset Availability project). Twin of db/sqlite/V007__settings_connections.sql. Only adds.
-- SETTING_PROFILE (a connection), SETTING_REVISION (its versions: secrets encrypted with AES-256-GCM under
-- SETTINGS_KEY, which is never stored in the database), SETTING_TEST (test outcomes), SETTING_CERT (trusted CA
-- certificates), EGRESS_RULE (approved destinations), CONNECTION_SETTING (the sign-in method and the configuration
-- generation), PROCESS_HEARTBEAT (which process runs which generation) and APP_SESSION.reauth_at.
-- Runtime grants: docs/oracle-migration.md section 3 (the V009 lines).

ALTER TABLE app_session ADD (reauth_at TIMESTAMP WITH TIME ZONE);

CREATE SEQUENCE setting_profile_seq  START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE setting_revision_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE setting_test_seq     START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE setting_cert_seq     START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE egress_rule_seq      START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE setting_profile (
    id                  NUMBER(19,0)        NOT NULL,
    kind                VARCHAR2(10 CHAR)   NOT NULL,
    provider            VARCHAR2(30 CHAR)   NOT NULL,
    name                VARCHAR2(80 CHAR)   NOT NULL,
    description         VARCHAR2(500 CHAR),
    purpose             VARCHAR2(30 CHAR)   NOT NULL,
    enabled             NUMBER(1)           DEFAULT 0 NOT NULL,
    active_revision_id  NUMBER(19,0),
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_setting_profile PRIMARY KEY (id),
    CONSTRAINT ck_setting_profile_kind CHECK (kind IN ('LDAP', 'SSO', 'DATABASE', 'AI')),
    CONSTRAINT ck_setting_profile_provider CHECK (LENGTH(provider) >= 2),
    CONSTRAINT ck_setting_profile_name CHECK (LENGTH(name) >= 2),
    CONSTRAINT ck_setting_profile_purpose CHECK (LENGTH(purpose) >= 2),
    CONSTRAINT ck_setting_profile_enabled CHECK (enabled IN (0, 1)),
    CONSTRAINT ck_setting_profile_archived CHECK ((archived_at IS NULL AND archived_by IS NULL)
                                                  OR (archived_at IS NOT NULL AND archived_by IS NOT NULL)),
    CONSTRAINT fk_setting_profile_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_setting_profile_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_setting_profile_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);
CREATE INDEX ix_setting_profile_kind ON setting_profile (kind, purpose);

CREATE TABLE setting_revision (
    id                  NUMBER(19,0)        NOT NULL,
    profile_id          NUMBER(19,0)        NOT NULL,
    revision_no         NUMBER(10,0)        NOT NULL,
    state               VARCHAR2(10 CHAR)   NOT NULL,
    schema_version      NUMBER(10,0)        NOT NULL,
    fields_json         CLOB                NOT NULL,
    secrets_json        CLOB,
    fingerprint         VARCHAR2(64 CHAR)   NOT NULL,
    note                VARCHAR2(500 CHAR),
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_setting_revision PRIMARY KEY (id),
    CONSTRAINT uq_setting_revision_no UNIQUE (profile_id, revision_no),
    CONSTRAINT ck_setting_revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_setting_revision_state CHECK (state IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'DISCARDED')),
    CONSTRAINT ck_setting_revision_schema CHECK (schema_version >= 1),
    CONSTRAINT ck_setting_revision_fp CHECK (LENGTH(fingerprint) = 64),
    CONSTRAINT fk_setting_revision_profile FOREIGN KEY (profile_id) REFERENCES setting_profile (id),
    CONSTRAINT fk_setting_revision_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_setting_revision_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id)
);

ALTER TABLE setting_profile ADD CONSTRAINT fk_setting_profile_active
    FOREIGN KEY (active_revision_id) REFERENCES setting_revision (id);

CREATE TABLE setting_test (
    id                  NUMBER(19,0)        NOT NULL,
    profile_id          NUMBER(19,0)        NOT NULL,
    revision_id         NUMBER(19,0),
    fingerprint         VARCHAR2(64 CHAR)   NOT NULL,
    stage               VARCHAR2(30 CHAR)   NOT NULL,
    outcome             VARCHAR2(10 CHAR)   NOT NULL,
    code                VARCHAR2(40 CHAR),
    message             VARCHAR2(500 CHAR),
    latency_ms          NUMBER(10,0),
    tested_at           TIMESTAMP WITH TIME ZONE NOT NULL,
    tested_by           NUMBER(19,0)        NOT NULL,
    CONSTRAINT pk_setting_test PRIMARY KEY (id),
    CONSTRAINT ck_setting_test_fp CHECK (LENGTH(fingerprint) = 64),
    CONSTRAINT ck_setting_test_stage CHECK (LENGTH(stage) >= 2),
    CONSTRAINT ck_setting_test_outcome CHECK (outcome IN ('PASSED', 'WARNING', 'FAILED', 'SKIPPED')),
    CONSTRAINT ck_setting_test_latency CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CONSTRAINT fk_setting_test_profile FOREIGN KEY (profile_id) REFERENCES setting_profile (id),
    CONSTRAINT fk_setting_test_revision FOREIGN KEY (revision_id) REFERENCES setting_revision (id),
    CONSTRAINT fk_setting_test_by FOREIGN KEY (tested_by) REFERENCES app_user (id)
);
CREATE INDEX ix_setting_test_profile ON setting_test (profile_id, tested_at);

CREATE TABLE setting_cert (
    id                  NUMBER(19,0)        NOT NULL,
    name                VARCHAR2(80 CHAR)   NOT NULL,
    pem                 CLOB                NOT NULL,
    sha256              VARCHAR2(64 CHAR)   NOT NULL,
    subject             VARCHAR2(500 CHAR)  NOT NULL,
    issuer              VARCHAR2(500 CHAR)  NOT NULL,
    not_before          TIMESTAMP WITH TIME ZONE NOT NULL,
    not_after           TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_setting_cert PRIMARY KEY (id),
    CONSTRAINT uq_setting_cert_sha256 UNIQUE (sha256),
    CONSTRAINT ck_setting_cert_name CHECK (LENGTH(name) >= 2),
    CONSTRAINT ck_setting_cert_sha256 CHECK (LENGTH(sha256) = 64),
    CONSTRAINT ck_setting_cert_archived CHECK ((archived_at IS NULL AND archived_by IS NULL)
                                               OR (archived_at IS NOT NULL AND archived_by IS NOT NULL)),
    CONSTRAINT fk_setting_cert_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_setting_cert_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_setting_cert_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE TABLE egress_rule (
    id                  NUMBER(19,0)        NOT NULL,
    host                VARCHAR2(253 CHAR)  NOT NULL,
    port                NUMBER(5,0)         NOT NULL,
    purpose             VARCHAR2(10 CHAR)   NOT NULL,
    note                VARCHAR2(500 CHAR),
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_egress_rule PRIMARY KEY (id),
    CONSTRAINT ck_egress_rule_port CHECK (port BETWEEN 1 AND 65535),
    CONSTRAINT ck_egress_rule_purpose CHECK (purpose IN ('LDAP', 'SSO', 'DATABASE', 'AI')),
    CONSTRAINT ck_egress_rule_archived CHECK ((archived_at IS NULL AND archived_by IS NULL)
                                              OR (archived_at IS NOT NULL AND archived_by IS NOT NULL)),
    CONSTRAINT fk_egress_rule_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_egress_rule_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_egress_rule_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE TABLE connection_setting (
    name                VARCHAR2(40 CHAR)   NOT NULL,
    value               VARCHAR2(500 CHAR)  NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_by          NUMBER(19,0),
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_connection_setting PRIMARY KEY (name),
    CONSTRAINT ck_connection_setting_name CHECK (LENGTH(name) >= 2),
    CONSTRAINT fk_connection_setting_by FOREIGN KEY (updated_by) REFERENCES app_user (id)
);

CREATE TABLE process_heartbeat (
    id                  VARCHAR2(120 CHAR)  NOT NULL,
    generation          NUMBER(19,0)        NOT NULL,
    started_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_process_heartbeat PRIMARY KEY (id),
    CONSTRAINT ck_process_heartbeat_generation CHECK (generation >= 0)
);
