-- GlicoCheck MVP v2
-- Banco novo para evitar alterar ou apagar o banco legado.
CREATE DATABASE IF NOT EXISTS glicocheck_v2
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE glicocheck_v2;

CREATE TABLE IF NOT EXISTS usuarios (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    nome VARCHAR(140) NOT NULL,
    email VARCHAR(190) NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    perfil ENUM('paciente','cuidador','medico') NOT NULL,
    data_nascimento DATE NULL,
    telefone VARCHAR(30) NULL,
    medico_registro VARCHAR(40) NULL,
    medico_uf CHAR(2) NULL,
    medico_verificado TINYINT(1) NOT NULL DEFAULT 0,
    ativo TINYINT(1) NOT NULL DEFAULT 1,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_usuarios_email (email),
    KEY idx_usuarios_perfil (perfil)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vinculos_cuidado (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id BIGINT UNSIGNED NOT NULL,
    usuario_vinculado_id BIGINT UNSIGNED NOT NULL,
    perfil_vinculado ENUM('cuidador','medico') NOT NULL,
    status ENUM('ativo','revogado') NOT NULL DEFAULT 'ativo',
    criado_por BIGINT UNSIGNED NOT NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_vinculo (paciente_id, usuario_vinculado_id, perfil_vinculado),
    KEY idx_vinculos_usuario (usuario_vinculado_id, perfil_vinculado, status),
    CONSTRAINT fk_vinculo_paciente FOREIGN KEY (paciente_id) REFERENCES usuarios(id),
    CONSTRAINT fk_vinculo_usuario FOREIGN KEY (usuario_vinculado_id) REFERENCES usuarios(id),
    CONSTRAINT fk_vinculo_criador FOREIGN KEY (criado_por) REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS convites_vinculo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id BIGINT UNSIGNED NOT NULL,
    criado_por BIGINT UNSIGNED NOT NULL,
    perfil_destino ENUM('cuidador','medico') NOT NULL,
    token_hash CHAR(64) NOT NULL,
    expira_em DATETIME NOT NULL,
    utilizado_em DATETIME NULL,
    utilizado_por BIGINT UNSIGNED NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_convite_hash (token_hash),
    KEY idx_convite_paciente (paciente_id, criado_em),
    CONSTRAINT fk_convite_paciente FOREIGN KEY (paciente_id) REFERENCES usuarios(id),
    CONSTRAINT fk_convite_criador FOREIGN KEY (criado_por) REFERENCES usuarios(id),
    CONSTRAINT fk_convite_utilizado_por FOREIGN KEY (utilizado_por) REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS medicoes_glicemia (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id BIGINT UNSIGNED NOT NULL,
    registrado_por BIGINT UNSIGNED NOT NULL,
    valor DECIMAL(8,2) NOT NULL,
    unidade ENUM('mg/dL','mmol/L') NOT NULL DEFAULT 'mg/dL',
    contexto ENUM('jejum','antes_refeicao','apos_refeicao','ao_deitar','outro') NOT NULL DEFAULT 'outro',
    medido_em DATETIME NOT NULL,
    observacoes VARCHAR(1000) NULL,
    origem ENUM('manual','sensor','importado') NOT NULL DEFAULT 'manual',
    status ENUM('ativo','retificado') NOT NULL DEFAULT 'ativo',
    retifica_medicao_id BIGINT UNSIGNED NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_medicoes_paciente_data (paciente_id, medido_em),
    KEY idx_medicoes_registrador (registrado_por),
    CONSTRAINT fk_medicao_paciente FOREIGN KEY (paciente_id) REFERENCES usuarios(id),
    CONSTRAINT fk_medicao_registrador FOREIGN KEY (registrado_por) REFERENCES usuarios(id),
    CONSTRAINT fk_medicao_retificada FOREIGN KEY (retifica_medicao_id) REFERENCES medicoes_glicemia(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tarefas (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id BIGINT UNSIGNED NOT NULL,
    criado_por BIGINT UNSIGNED NOT NULL,
    titulo VARCHAR(140) NOT NULL,
    descricao VARCHAR(500) NULL,
    tipo ENUM('medicao','medicamento','consulta','exame','autocuidado','outro') NOT NULL DEFAULT 'autocuidado',
    data_hora DATETIME NOT NULL,
    status ENUM('pendente','concluida','cancelada') NOT NULL DEFAULT 'pendente',
    concluida_por BIGINT UNSIGNED NULL,
    concluida_em DATETIME NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tarefas_paciente_data (paciente_id, data_hora, status),
    CONSTRAINT fk_tarefa_paciente FOREIGN KEY (paciente_id) REFERENCES usuarios(id),
    CONSTRAINT fk_tarefa_criador FOREIGN KEY (criado_por) REFERENCES usuarios(id),
    CONSTRAINT fk_tarefa_concluida_por FOREIGN KEY (concluida_por) REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS planos_cuidado (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id BIGINT UNSIGNED NOT NULL,
    medico_id BIGINT UNSIGNED NOT NULL,
    titulo VARCHAR(160) NOT NULL,
    orientacoes TEXT NOT NULL,
    metas TEXT NULL,
    ativo TINYINT(1) NOT NULL DEFAULT 1,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_plano_paciente_ativo (paciente_id, ativo, atualizado_em),
    CONSTRAINT fk_plano_paciente FOREIGN KEY (paciente_id) REFERENCES usuarios(id),
    CONSTRAINT fk_plano_medico FOREIGN KEY (medico_id) REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS consultas (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paciente_id BIGINT UNSIGNED NOT NULL,
    medico_id BIGINT UNSIGNED NOT NULL,
    data_hora DATETIME NOT NULL,
    local VARCHAR(180) NULL,
    motivo VARCHAR(500) NULL,
    status ENUM('agendada','concluida','cancelada') NOT NULL DEFAULT 'agendada',
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_consulta_paciente_data (paciente_id, data_hora, status),
    KEY idx_consulta_medico_data (medico_id, data_hora),
    CONSTRAINT fk_consulta_paciente FOREIGN KEY (paciente_id) REFERENCES usuarios(id),
    CONSTRAINT fk_consulta_medico FOREIGN KEY (medico_id) REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auditoria (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    usuario_id BIGINT UNSIGNED NOT NULL,
    acao VARCHAR(60) NOT NULL,
    recurso VARCHAR(80) NOT NULL,
    recurso_id BIGINT UNSIGNED NULL,
    detalhes VARCHAR(500) NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_auditoria_usuario_data (usuario_id, criado_em),
    KEY idx_auditoria_recurso (recurso, recurso_id),
    CONSTRAINT fk_auditoria_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
