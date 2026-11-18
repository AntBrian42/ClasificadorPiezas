import mysql.connector

def conectar():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234567",
        database="inspeccion_industrial"
    )

def obtener_id_pieza(cursor, tipo):
    cursor.execute("SELECT id_pieza FROM pieza WHERE tipo_pieza = %s", (tipo,))
    fila = cursor.fetchone()
    if fila is None:
        cursor.execute("INSERT INTO pieza (tipo_pieza, contador) VALUES (%s, 0)", (tipo,))
        return cursor.lastrowid
    return fila[0]

def registrar_pieza(etiqueta, vertices, diametro, area, motivo):
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        id_pieza = obtener_id_pieza(cursor, etiqueta)
        if etiqueta == "Descarte":
            cursor.execute(
                "INSERT INTO pieza_rechazada (pieza_id_pieza, motivo_rechazo, fecha_hora_procesamiento) "
                "VALUES (%s, %s, NOW())",
                (id_pieza, motivo))
        else:
            cursor.execute(
                "INSERT INTO clasificacion (pieza_id_pieza, cantidad_vertice, `tamaño`, area, fecha_hora_procesamiento) "
                "VALUES (%s, %s, %s, %s, NOW())",
                (id_pieza, str(vertices), diametro, area))
        cursor.execute("UPDATE pieza SET contador = contador + 1 WHERE id_pieza = %s", (id_pieza,))
        conexion.commit()
        cursor.close()
    finally:
        conexion.close()

def obtener_clasificadas():
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT c.id_clasificacion, p.tipo_pieza, c.cantidad_vertice, c.`tamaño`, c.area, c.fecha_hora_procesamiento "
            "FROM clasificacion c INNER JOIN pieza p ON c.pieza_id_pieza = p.id_pieza "
            "ORDER BY c.id_clasificacion DESC LIMIT 15")
        registros = cursor.fetchall()
        cursor.close()
        return registros
    finally:
        conexion.close()

def obtener_rechazadas():
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT r.id_rechazo, p.tipo_pieza, r.motivo_rechazo, r.fecha_hora_procesamiento "
            "FROM pieza_rechazada r INNER JOIN pieza p ON r.pieza_id_pieza = p.id_pieza "
            "ORDER BY r.id_rechazo DESC LIMIT 15")
        registros = cursor.fetchall()
        cursor.close()
        return registros
    finally:
        conexion.close()