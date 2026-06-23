-- ============================================
-- SCRIPT DE INSERCIÓN DE DATOS ALEATORIOS
-- Ventas de la Semana Pasada y Compra del Sábado
-- ============================================

USE Ferreteria;
GO

-- ============================================
-- PASO 1: VERIFICAR DATOS NECESARIOS
-- ============================================
-- Descomenta estas consultas para verificar que tienes datos base
/*
SELECT COUNT(*) as total_usuarios FROM usuario;
SELECT COUNT(*) as total_clientes FROM cliente;
SELECT COUNT(*) as total_proveedores FROM proveedor;
SELECT COUNT(*) as total_productos FROM producto;
*/

-- ============================================
-- PASO 2: INSERTAR VENTAS DE LA SEMANA PASADA (Lunes a Viernes)
-- ============================================

-- Lunes de la semana pasada
INSERT INTO venta (id_cliente, id_usuario, fecha, total)
SELECT 
    (SELECT id_cliente FROM cliente ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY),
    1,
    DATEADD(DAY, -5, CAST(GETDATE() AS DATE)),
    ROUND(RAND() * 1000 + 50, 2);

-- Martes de la semana pasada
INSERT INTO venta (id_cliente, id_usuario, fecha, total)
SELECT 
    (SELECT id_cliente FROM cliente ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY),
    1,
    DATEADD(DAY, -4, CAST(GETDATE() AS DATE)),
    ROUND(RAND() * 1000 + 50, 2);

-- Miércoles de la semana pasada
INSERT INTO venta (id_cliente, id_usuario, fecha, total)
SELECT 
    (SELECT id_cliente FROM cliente ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY),
    1,
    DATEADD(DAY, -3, CAST(GETDATE() AS DATE)),
    ROUND(RAND() * 1000 + 50, 2);

-- Jueves de la semana pasada
INSERT INTO venta (id_cliente, id_usuario, fecha, total)
SELECT 
    (SELECT id_cliente FROM cliente ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY),
    1,
    DATEADD(DAY, -2, CAST(GETDATE() AS DATE)),
    ROUND(RAND() * 1000 + 50, 2);

-- Viernes de la semana pasada
INSERT INTO venta (id_cliente, id_usuario, fecha, total)
SELECT 
    (SELECT id_cliente FROM cliente ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY),
    1,
    DATEADD(DAY, -1, CAST(GETDATE() AS DATE)),
    ROUND(RAND() * 1000 + 50, 2);

PRINT '✓ 5 Ventas insertadas de Lunes a Viernes';
GO

-- ============================================
-- PASO 3: INSERTAR DETALLES DE VENTAS ALEATORIOS
-- ============================================

DECLARE @max_producto INT = (SELECT COUNT(*) FROM producto);
DECLARE @max_venta INT = (SELECT MAX(id_venta) FROM venta);
DECLARE @min_venta INT = (SELECT MAX(id_venta) - 4 FROM venta);
DECLARE @venta_actual INT = @min_venta;

WHILE @venta_actual <= @max_venta
BEGIN
    DECLARE @num_detalles INT = FLOOR(RAND() * 3) + 2; -- 2-4 productos por venta
    DECLARE @contador_detalle INT = 0;
    
    WHILE @contador_detalle < @num_detalles
    BEGIN
        DECLARE @producto_id INT = (SELECT id_producto FROM producto ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY);
        DECLARE @cantidad INT = FLOOR(RAND() * 10) + 1;
        DECLARE @precio_unitario DECIMAL(18,2) = (SELECT precio_venta FROM producto WHERE id_producto = @producto_id);
        DECLARE @subtotal DECIMAL(18,2) = @cantidad * @precio_unitario;
        
        INSERT INTO detalle_venta (id_venta, id_producto, cantidad, precio_unitario, subtotal)
        VALUES (@venta_actual, @producto_id, @cantidad, @precio_unitario, @subtotal);
        
        SET @contador_detalle = @contador_detalle + 1;
    END
    
    SET @venta_actual = @venta_actual + 1;
END

PRINT '✓ Detalles de ventas insertados';
GO

-- ============================================
-- PASO 4: INSERTAR COMPRA DEL SÁBADO
-- ============================================

-- Obtener la fecha del sábado pasado o próximo
DECLARE @fecha_sabado DATE = CAST(
    DATEADD(DAY, 
        CASE 
            WHEN DATEPART(WEEKDAY, GETDATE()) >= 7 THEN 7 - DATEPART(WEEKDAY, GETDATE())
            ELSE 7 - DATEPART(WEEKDAY, GETDATE()) - 7
        END, 
        GETDATE()
    ) AS DATE
);

INSERT INTO compra (id_proveedor, id_usuario, fecha, total)
SELECT 
    (SELECT id_proveedor FROM proveedor ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY),
    1,
    @fecha_sabado,
    ROUND(RAND() * 5000 + 500, 2);

PRINT '✓ Compra del sábado insertada';
GO

-- ============================================
-- PASO 5: INSERTAR DETALLES DE COMPRA ALEATORIOS
-- ============================================

DECLARE @compra_id INT = (SELECT MAX(id_compra) FROM compra);
DECLARE @max_producto_compra INT = (SELECT COUNT(*) FROM producto);
DECLARE @num_items_compra INT = FLOOR(RAND() * 5) + 3; -- 3-7 productos por compra
DECLARE @contador_compra INT = 0;

WHILE @contador_compra < @num_items_compra
BEGIN
    DECLARE @prod_id INT = (SELECT id_producto FROM producto ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY);
    DECLARE @cant INT = FLOOR(RAND() * 50) + 5;
    DECLARE @precio_comp DECIMAL(18,2) = (SELECT precio_compra FROM producto WHERE id_producto = @prod_id);
    
    INSERT INTO detalle_compra (id_compra, id_producto, cantidad, precio_unitario)
    VALUES (@compra_id, @prod_id, @cant, @precio_comp);
    
    SET @contador_compra = @contador_compra + 1;
END

PRINT '✓ Detalles de compra insertados';
GO

-- ============================================
-- PASO 6: ACTUALIZAR TOTALES EN COMPRA
-- ============================================

UPDATE compra
SET total = ISNULL((
    SELECT SUM(cantidad * precio_unitario)
    FROM detalle_compra
    WHERE id_compra = compra.id_compra
), 0)
WHERE id_compra = (SELECT MAX(id_compra) FROM compra);

PRINT '✓ Total de compra actualizado';
GO

-- ============================================
-- PASO 7: ACTUALIZAR TOTALES EN VENTAS
-- ============================================

UPDATE venta
SET total = ISNULL((
    SELECT SUM(subtotal)
    FROM detalle_venta
    WHERE id_venta = venta.id_venta
), 0)
WHERE id_venta >= (SELECT MAX(id_venta) - 4 FROM venta);

PRINT '✓ Totales de ventas actualizados';
GO

-- ============================================
-- CONSULTAS DE VERIFICACIÓN
-- ============================================

PRINT '';
PRINT '========================================';
PRINT 'VENTAS DE LA SEMANA PASADA';
PRINT '========================================';

SELECT 
    v.id_venta,
    CAST(v.fecha AS DATE) as [Fecha],
    ISNULL(c.nombre, 'Sin Cliente') as [Cliente],
    COUNT(DISTINCT p.id_producto) as [Productos],
    SUM(dv.cantidad) as [Cantidad Total],
    v.total as [Total]
FROM venta v
LEFT JOIN cliente c ON v.id_cliente = c.id_cliente
LEFT JOIN detalle_venta dv ON v.id_venta = dv.id_venta
LEFT JOIN producto p ON dv.id_producto = p.id_producto
WHERE CAST(v.fecha AS DATE) >= DATEADD(DAY, -7, CAST(GETDATE() AS DATE))
GROUP BY v.id_venta, CAST(v.fecha AS DATE), c.nombre, v.total
ORDER BY v.fecha DESC;

PRINT '';
PRINT '========================================';
PRINT 'DETALLES DE VENTAS';
PRINT '========================================';

SELECT 
    v.id_venta,
    CAST(v.fecha AS DATE) as [Fecha],
    p.nombre as [Producto],
    dv.cantidad as [Cantidad],
    dv.precio_unitario as [Precio Unitario],
    dv.subtotal as [Subtotal]
FROM venta v
LEFT JOIN detalle_venta dv ON v.id_venta = dv.id_venta
LEFT JOIN producto p ON dv.id_producto = p.id_producto
WHERE CAST(v.fecha AS DATE) >= DATEADD(DAY, -7, CAST(GETDATE() AS DATE))
ORDER BY v.fecha DESC, v.id_venta DESC;

PRINT '';
PRINT '========================================';
PRINT 'COMPRA DEL SÁBADO';
PRINT '========================================';

SELECT 
    c.id_compra,
    CAST(c.fecha AS DATE) as [Fecha],
    pr.nombre as [Proveedor],
    COUNT(DISTINCT p.id_producto) as [Productos],
    SUM(dc.cantidad) as [Cantidad Total],
    c.total as [Total]
FROM compra c
LEFT JOIN proveedor pr ON c.id_proveedor = pr.id_proveedor
LEFT JOIN detalle_compra dc ON c.id_compra = dc.id_compra
LEFT JOIN producto p ON dc.id_producto = p.id_producto
WHERE DATEPART(WEEKDAY, c.fecha) = 7 OR CAST(c.fecha AS DATE) = CAST(DATEADD(DAY, -(DATEPART(WEEKDAY, GETDATE())-2), CAST(GETDATE() AS DATE)) AS DATE)
GROUP BY c.id_compra, CAST(c.fecha AS DATE), pr.nombre, c.total
ORDER BY c.fecha DESC;

PRINT '';
PRINT '========================================';
PRINT 'DETALLES DE COMPRA';
PRINT '========================================';

SELECT 
    c.id_compra,
    CAST(c.fecha AS DATE) as [Fecha],
    p.nombre as [Producto],
    dc.cantidad as [Cantidad],
    dc.precio_unitario as [Precio Unitario],
    (dc.cantidad * dc.precio_unitario) as [Subtotal]
FROM compra c
LEFT JOIN detalle_compra dc ON c.id_compra = dc.id_compra
LEFT JOIN producto p ON dc.id_producto = p.id_producto
WHERE DATEPART(WEEKDAY, c.fecha) = 7 OR CAST(c.fecha AS DATE) = CAST(DATEADD(DAY, -(DATEPART(WEEKDAY, GETDATE())-2), CAST(GETDATE() AS DATE)) AS DATE)
ORDER BY c.fecha DESC;

PRINT '';
PRINT '✓✓✓ SCRIPT COMPLETADO EXITOSAMENTE ✓✓✓';
