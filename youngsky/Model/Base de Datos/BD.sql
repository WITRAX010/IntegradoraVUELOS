CREATE DATABASE youngsky;
USE youngsky;

CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    contrasena_hash VARCHAR(255),
    pais_residencia VARCHAR(100),
    rol ENUM('cliente', 'admin') DEFAULT 'cliente',
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE solicitudes_viaje (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT,
    pais_destino VARCHAR(100),
    tipo_viaje VARCHAR(50),
    fecha_estimada DATE,
    preferencias TEXT,
    estado ENUM('pendiente', 'atendida', 'cancelada') DEFAULT 'pendiente',
    fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

CREATE TABLE propuestas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    solicitud_id INT,
    itinerario TEXT,
    costo_estimado DECIMAL(10, 2),
    fecha_propuesta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    estado ENUM('enviada', 'aceptada', 'rechazada') DEFAULT 'enviada',
    FOREIGN KEY (solicitud_id) REFERENCES solicitudes_viaje(id)
);

CREATE TABLE mensajes_contacto (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT,
    asunto VARCHAR(150),
    mensaje TEXT,
    fecha_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    respondido BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

CREATE TABLE historial_notificaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT,
    mensaje TEXT,
    fecha_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo VARCHAR(50),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

INSERT INTO usuarios (
    nombre, email, contrasena_hash, pais_residencia, rol
) VALUES (
    'Admin', 'admin@gmail.com', 'root', 'México', 'admin'
);
INSERT INTO usuarios (
    nombre, email, contrasena_hash, pais_residencia, rol
) VALUES (
    'Kevin', 'kevin@email.com', 'cisco123', 'México', 'cliente'
);

select * from usuarios;
DELETE FROM usuarios WHERE id = 4;