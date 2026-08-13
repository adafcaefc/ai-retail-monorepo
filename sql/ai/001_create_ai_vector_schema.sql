/*
  AI Retail 360 Phase 5 semantic document and vector layer for Azure SQL.

  This migration is additive and rerunnable. It creates only missing ai.*
  objects, never modifies retail.*, and deliberately uses exact
  VECTOR_DISTANCE search rather than preview-only vector-index features.
*/
IF SCHEMA_ID(N'ai') IS NULL
    EXEC(N'CREATE SCHEMA ai');
GO

IF OBJECT_ID(N'ai.EmbeddingProfile', N'U') IS NULL
BEGIN
    CREATE TABLE ai.EmbeddingProfile (
        embedding_profile_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ai_EmbeddingProfile PRIMARY KEY,
        profile_key NVARCHAR(128) NOT NULL,
        provider NVARCHAR(100) NOT NULL,
        model_name NVARCHAR(240) NOT NULL,
        model_revision NVARCHAR(100) NULL,
        dimensions INT NOT NULL,
        normalization BIT NOT NULL,
        max_sequence_length INT NOT NULL,
        document_instruction NVARCHAR(1000) NOT NULL,
        query_instruction NVARCHAR(1000) NOT NULL,
        chunk_target_tokens INT NOT NULL,
        chunk_overlap_tokens INT NOT NULL,
        configuration_json NVARCHAR(MAX) NOT NULL,
        status NVARCHAR(20) NOT NULL,
        created_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_ai_EmbeddingProfile_created_at DEFAULT SYSUTCDATETIME(),
        activated_at DATETIME2(3) NULL,
        retired_at DATETIME2(3) NULL,
        CONSTRAINT UQ_ai_EmbeddingProfile_key UNIQUE (profile_key),
        CONSTRAINT CK_ai_EmbeddingProfile_dimensions CHECK (dimensions = 384),
        CONSTRAINT CK_ai_EmbeddingProfile_normalization CHECK (normalization = 1),
        CONSTRAINT CK_ai_EmbeddingProfile_sequence CHECK (
            max_sequence_length > 0
            AND chunk_target_tokens > 0
            AND chunk_target_tokens <= max_sequence_length
            AND chunk_overlap_tokens >= 0
            AND chunk_overlap_tokens < chunk_target_tokens
        ),
        CONSTRAINT CK_ai_EmbeddingProfile_configuration_json CHECK (ISJSON(configuration_json) = 1),
        CONSTRAINT CK_ai_EmbeddingProfile_status CHECK (
            status IN (N'BUILDING', N'ACTIVE', N'RETIRED')
        )
    );
    CREATE UNIQUE INDEX UX_ai_EmbeddingProfile_single_active
        ON ai.EmbeddingProfile(status)
        WHERE status = N'ACTIVE';
    CREATE INDEX IX_ai_EmbeddingProfile_provider_model
        ON ai.EmbeddingProfile(provider, model_name, status);
END;
GO

IF OBJECT_ID(N'ai.RetailDocument', N'U') IS NULL
BEGIN
    CREATE TABLE ai.RetailDocument (
        document_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ai_RetailDocument PRIMARY KEY,
        doc_key NVARCHAR(450) NOT NULL,
        doc_type NVARCHAR(80) NOT NULL,
        retrieval_domain NVARCHAR(80) NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_key NVARCHAR(450) NOT NULL,
        content NVARCHAR(MAX) NOT NULL,
        metadata_json NVARCHAR(MAX) NOT NULL,
        content_hash CHAR(64) NOT NULL,
        is_active BIT NOT NULL
            CONSTRAINT DF_ai_RetailDocument_is_active DEFAULT 1,
        created_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_ai_RetailDocument_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_ai_RetailDocument_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_ai_RetailDocument_doc_key UNIQUE (doc_key),
        CONSTRAINT CK_ai_RetailDocument_metadata_json CHECK (ISJSON(metadata_json) = 1),
        CONSTRAINT CK_ai_RetailDocument_content_hash CHECK (
            LEN(content_hash) = 64
            AND content_hash COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
        )
    );
    CREATE INDEX IX_ai_RetailDocument_type
        ON ai.RetailDocument(doc_type, is_active);
    CREATE INDEX IX_ai_RetailDocument_domain
        ON ai.RetailDocument(retrieval_domain, is_active);
    CREATE INDEX IX_ai_RetailDocument_active_domain_type
        ON ai.RetailDocument(is_active, retrieval_domain, doc_type)
        INCLUDE (doc_key, source_key, content_hash);
END;
GO

IF OBJECT_ID(N'ai.RetailChunk', N'U') IS NULL
BEGIN
    CREATE TABLE ai.RetailChunk (
        chunk_id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ai_RetailChunk PRIMARY KEY,
        document_id BIGINT NOT NULL,
        chunk_index INT NOT NULL,
        chunk_key NVARCHAR(450) NOT NULL,
        content NVARCHAR(MAX) NOT NULL,
        chunk_hash CHAR(64) NOT NULL,
        token_count INT NOT NULL,
        created_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_ai_RetailChunk_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_ai_RetailChunk_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ai_RetailChunk_document FOREIGN KEY (document_id)
            REFERENCES ai.RetailDocument(document_id) ON DELETE CASCADE,
        CONSTRAINT UQ_ai_RetailChunk_document_index UNIQUE (document_id, chunk_index),
        CONSTRAINT UQ_ai_RetailChunk_key UNIQUE (chunk_key),
        CONSTRAINT CK_ai_RetailChunk_index CHECK (chunk_index >= 0),
        CONSTRAINT CK_ai_RetailChunk_tokens CHECK (token_count > 0 AND token_count <= 512),
        CONSTRAINT CK_ai_RetailChunk_hash CHECK (
            LEN(chunk_hash) = 64
            AND chunk_hash COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
        )
    );
    CREATE INDEX IX_ai_RetailChunk_document
        ON ai.RetailChunk(document_id, chunk_index)
        INCLUDE (chunk_hash, token_count);
END;
GO

IF OBJECT_ID(N'ai.RetailEmbedding', N'U') IS NULL
BEGIN
    CREATE TABLE ai.RetailEmbedding (
        embedding_profile_id BIGINT NOT NULL,
        chunk_id BIGINT NOT NULL,
        embedding VECTOR(384) NOT NULL,
        embedded_chunk_hash CHAR(64) NOT NULL,
        embedded_at DATETIME2(3) NOT NULL
            CONSTRAINT DF_ai_RetailEmbedding_embedded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_ai_RetailEmbedding PRIMARY KEY (embedding_profile_id, chunk_id),
        CONSTRAINT FK_ai_RetailEmbedding_profile FOREIGN KEY (embedding_profile_id)
            REFERENCES ai.EmbeddingProfile(embedding_profile_id),
        CONSTRAINT FK_ai_RetailEmbedding_chunk FOREIGN KEY (chunk_id)
            REFERENCES ai.RetailChunk(chunk_id) ON DELETE CASCADE,
        CONSTRAINT CK_ai_RetailEmbedding_hash CHECK (
            LEN(embedded_chunk_hash) = 64
            AND embedded_chunk_hash COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
        )
    );
    CREATE INDEX IX_ai_RetailEmbedding_chunk_profile
        ON ai.RetailEmbedding(chunk_id, embedding_profile_id)
        INCLUDE (embedded_chunk_hash, embedded_at);
END;
GO
