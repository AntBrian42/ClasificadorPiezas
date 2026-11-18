import cv2
import numpy as np

CAMARA = 0
AREA_MINIMA = 800
# Una zona es pieza si su brillo > FACTOR_FONDO * brillo_del_fondo + MARGEN_BRILLO.
# Es proporcional para funcionar igual con poca o mucha luz.
FACTOR_FONDO = 2.0
MARGEN_BRILLO = 10
# Franja lateral (fracción del ancho) donde se ignoran objetos: rieles de madera
MARGEN_LATERAL = 0.11
# Rectángulos (x0, y0, x1, y1 en una imagen de 640x480) que no se analizan
ZONAS_IGNORADAS = [(10, 345, 75, 410)]   # logo "Iriun webcam"
UMBRAL_CIRCULO = 0.90        # con 5-7 vértices, debajo de esto es hexagonal
RELLENO_MIN_REDONDA = 0.86   # con 8+ vértices, encima de esto es redonda
TOLERANCIA_APROX = 0.03
VERTICES_MIN = 5
VERTICES_MAX = 8
KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
# Borra los puntitos brillantes de la textura de la banda (menores a 15 px)
KERNEL_TEXTURA = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))

def _kernels_linea(largo, n=8):
    kernels = []
    for ang in np.linspace(0, np.pi, n, endpoint=False):
        k = np.zeros((largo, largo), np.uint8)
        c = largo // 2
        dx, dy = np.cos(ang) * c, np.sin(ang) * c
        cv2.line(k, (int(round(c - dx)), int(round(c - dy))),
                 (int(round(c + dx)), int(round(c + dy))), 1, 1)
        kernels.append(k)
    return kernels

# Segunda pasada para piezas delgadas (tornillos acostados) que el disco de 15 px borra:
# líneas de 25 px en 8 orientaciones. Solo se aceptan objetos alargados y chicos,
# para no confundir la textura iluminada de la banda con piezas.
KERNELS_LINEA = _kernels_linea(25)
ASPECTO_MIN_DELGADA = 3.0
AREA_MAX_DELGADA = 4000

def _mascara(suave, ancho, alto):
    chica = cv2.resize(suave, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    fondo = cv2.resize(cv2.medianBlur(chica, 51), (ancho, alto),
                       interpolation=cv2.INTER_LINEAR).astype(np.float32)
    return np.where(suave > FACTOR_FONDO * fondo + MARGEN_BRILLO, 255, 0).astype(np.uint8)

def abrir_camara():
    camara = cv2.VideoCapture(CAMARA, cv2.CAP_DSHOW)
    # Reduce el búfer interno para no clasificar cuadros viejos (si el driver lo permite)
    camara.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return camara

def analizar_forma(contorno):
    area = cv2.contourArea(contorno)

    (_, _), radio = cv2.minEnclosingCircle(contorno)
    relleno_circulo = area / (np.pi * radio ** 2)

    casco = cv2.convexHull(contorno)
    aprox = cv2.approxPolyDP(
        casco, TOLERANCIA_APROX * cv2.arcLength(casco, True), True)
    vertices = len(aprox)

    # Medido en la banda: tuerca relleno ~0.87 con 6 vértices; rondana ~0.91 con 8.
    # Se combinan las dos cosas porque el relleno solo tiene poco margen.
    if VERTICES_MIN <= vertices <= 7 and relleno_circulo < UMBRAL_CIRCULO:
        forma = "hexagonal"
    elif relleno_circulo >= RELLENO_MIN_REDONDA:
        forma = "redonda"
    elif VERTICES_MIN <= vertices <= VERTICES_MAX:
        forma = "hexagonal"
    else:
        forma = "otra"

    return forma, vertices, relleno_circulo, radio * 2

def procesar_frame(frame):
    alto, ancho = frame.shape[:2]
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Franjas negras que agrega la cámara (Iriun en 16:9) arriba y abajo
    max_fila = gris.max(axis=1)
    y0 = 0
    while y0 < alto and max_fila[y0] <= 2:
        y0 += 1
    y1 = alto
    while y1 > y0 and max_fila[y1 - 1] <= 2:
        y1 -= 1
    # Si la banda está muy oscura no confundirla con franja: máximo 1/4 por lado
    y0 = min(y0, alto // 4)
    y1 = max(y1, alto - alto // 4)

    suave = cv2.GaussianBlur(gris, (5, 5), 0)
    # Fondo local (la luz de la banda no es pareja): se compara cada punto con su
    # alrededor (ventana ~200 px, calculada a 1/4 de tamaño) y no con un umbral fijo
    umbral = _mascara(cv2.morphologyEx(suave, cv2.MORPH_OPEN, KERNEL_TEXTURA), ancho, alto)
    lineas = _mascara(np.max([cv2.morphologyEx(suave, cv2.MORPH_OPEN, k)
                              for k in KERNELS_LINEA], axis=0), ancho, alto)
    lineas = cv2.morphologyEx(lineas, cv2.MORPH_CLOSE, KERNEL, iterations=2)
    extras, _ = cv2.findContours(lineas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in extras:
        area = cv2.contourArea(c)
        if not (AREA_MINIMA <= area <= AREA_MAX_DELGADA):
            continue
        (_, _), (w, h), _ = cv2.minAreaRect(c)
        if max(w, h) / max(min(w, h), 1) < ASPECTO_MIN_DELGADA:
            continue
        zona = np.zeros_like(umbral)
        cv2.drawContours(zona, [c], 0, 255, -1)
        # Se agrega si la primera pasada no la cubrió (o solo dejó un pedazo)
        if np.count_nonzero(umbral[zona > 0]) < 0.5 * np.count_nonzero(zona):
            umbral = cv2.bitwise_or(umbral, zona)
    umbral[:y0] = 0
    umbral[y1:] = 0
    # Marca de agua de Iriun (logo abajo a la izquierda de la imagen)
    for (mx0, my0, mx1, my1) in ZONAS_IGNORADAS:
        umbral[int(my0 * alto / 480):int(my1 * alto / 480),
               int(mx0 * ancho / 640):int(mx1 * ancho / 640)] = 0
    umbral = cv2.morphologyEx(umbral, cv2.MORPH_CLOSE, KERNEL, iterations=2)
    x0 = int(MARGEN_LATERAL * ancho)
    x1 = ancho - x0

    contornos, jerarquia = cv2.findContours(
        umbral, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    piezas = []

    if jerarquia is not None:
        jerarquia = jerarquia[0]

        for i, c in enumerate(contornos):
            if jerarquia[i][3] != -1:
                continue
            area = cv2.contourArea(c)
            if area < AREA_MINIMA:
                continue

            x, y, w, h = cv2.boundingRect(c)
            momentos = cv2.moments(c)
            if momentos["m00"] != 0:
                cx = momentos["m10"] / momentos["m00"]
                cy = momentos["m01"] / momentos["m00"]
            else:
                cx, cy = x + w / 2, y + h / 2
            # Rieles laterales y reflejos enormes no son piezas
            if cx < x0 or cx > x1:
                continue
            if h > 0.7 * (y1 - y0) or w > 0.7 * ancho:
                continue

            tiene_hoyo = jerarquia[i][2] != -1

            forma, vertices, relleno, diametro = analizar_forma(c)

            motivo = ""
            if tiene_hoyo and forma == "hexagonal":
                etiqueta, color = "Tuerca", (0, 255, 0)
            elif tiene_hoyo and forma == "redonda":
                etiqueta, color = "Rondana", (255, 0, 0)
            else:
                etiqueta, color = "Descarte", (0, 0, 255)
                if not tiene_hoyo:
                    motivo = "Sin agujero"
                else:
                    motivo = "Forma no reconocida"

            cv2.drawContours(frame, [c], 0, color, 2)
            cv2.putText(frame, etiqueta, (x, y - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.putText(frame, f"v={vertices} r={relleno:.2f}",
                        (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, color, 1)

            toca_borde = x <= 1 or y <= y0 + 1 or x + w >= ancho - 1 or y + h >= y1 - 1
            cv2.circle(frame, (int(cx), int(cy)), 4, color, -1)

            piezas.append({
                "etiqueta": etiqueta,
                "vertices": vertices,
                "diametro": round(diametro, 2),
                "area": round(area, 2),
                "motivo": motivo,
                "cx": cx,
                "cy": cy,
                "toca_borde": toca_borde,
            })

    # Líneas de referencia del centro del cuadro
    cv2.line(frame, (ancho // 2, 0), (ancho // 2, alto), (0, 255, 255), 1)
    cv2.line(frame, (0, alto // 2), (ancho, alto // 2), (0, 255, 255), 1)
    cv2.line(frame, (x0, 0), (x0, alto), (128, 128, 128), 1)
    cv2.line(frame, (x1, 0), (x1, alto), (128, 128, 128), 1)

    return frame, piezas

# ---------------- Pulsos de la banda (medidos en la banda real) ----------------
MS_MUERTO = 45            # ms que tarda la banda en empezar a moverse en cada pulso
MS_POR_PIXEL = 4.8        # ms de banda por píxel recorrido en la imagen
PULSO_MIN_MS = 60
PULSO_MAX_MS = 1500

def calcular_pulso(pixeles, ms_por_pixel):
    """Duración del pulso (ms) para mover la pieza 'pixeles' (valor absoluto)."""
    ms = MS_MUERTO + abs(pixeles) * ms_por_pixel
    return int(min(max(ms, PULSO_MIN_MS), PULSO_MAX_MS))

def aprender_ms_por_pixel(ms_por_pixel, ms_enviado, pixeles_movidos):
    """Ajusta la estimación con lo que realmente se movió la pieza."""
    if pixeles_movidos < 4 or ms_enviado <= MS_MUERTO:
        return ms_por_pixel
    medido = (ms_enviado - MS_MUERTO) / pixeles_movidos
    return min(max(0.6 * ms_por_pixel + 0.4 * medido, 1.0), 20.0)

def elegir_pieza(piezas, objetivo=None, eje="x"):
    """Devuelve la pieza más cercana al objetivo (en píxeles sobre el eje dado).
    Prefiere piezas completas (que no tocan el borde). Sin objetivo, la de mayor área.
    Devuelve None si no hay piezas."""
    if len(piezas) == 0:
        return None
    candidatas = [p for p in piezas if not p["toca_borde"]] or piezas
    if objetivo is None:
        return max(candidatas, key=lambda p: p["area"])
    clave = "cx" if eje == "x" else "cy"
    return min(candidatas, key=lambda p: abs(p[clave] - objetivo))