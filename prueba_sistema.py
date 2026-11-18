"""Prueba del sistema sin la interfaz gráfica.

Uso:
  python prueba_sistema.py servos      -> prueba todas las combinaciones de compuerta
  python prueba_sistema.py ciclo [N]   -> corre la banda y centra/clasifica N piezas
Guarda una foto de cada pieza clasificada en la carpeta 'pruebas'.
"""
import os
import sys
import threading
import time

import cv2
import serial
from serial.tools import list_ports

import Main

EJE_BANDA = "y"
SENTIDO_AVANCE = -1
TOLERANCIA_PX = 10
MAX_AJUSTES = 5
ESPERA_ASENTAR = 0.35
CUADROS_FRESCOS = 8
CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruebas")

estado = {"n": 0, "piezas": [], "cuadro": None, "ancho": 640, "alto": 480}


def buscar_puerto():
    for p in list_ports.comports():
        if p.vid in {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4}:
            return p.device
    sys.exit("No se encontró el Arduino conectado por USB.")


def hilo_camara():
    cam = Main.abrir_camara()
    while True:
        ok, cuadro = cam.read()
        if not ok:
            continue
        estado["alto"], estado["ancho"] = cuadro.shape[:2]
        estado["crudo"] = cuadro.copy()
        cuadro, estado["piezas"] = Main.procesar_frame(cuadro)
        estado["cuadro"] = cuadro
        estado["n"] += 1


def esperar_cuadros(k):
    ini = estado["n"]
    lim = time.time() + 2
    while estado["n"] - ini < k and time.time() < lim:
        time.sleep(0.01)


def prueba_servos(ard):
    # Todas las transiciones posibles entre los tres destinos
    secuencia = "dtrdrttdr"
    nombres = {"d": "DESCARTE (frente)", "t": "TUERCA (derecha)", "r": "RONDANA (izquierda)"}
    for c in secuencia:
        print(f"-> {nombres[c]}")
        ard.write(c.encode())
        time.sleep(3)


def centrar(ard, ms_px):
    eje = "cx" if EJE_BANDA == "x" else "cy"
    objetivo = (estado["ancho"] if EJE_BANDA == "x" else estado["alto"]) / 2
    time.sleep(ESPERA_ASENTAR)
    esperar_cuadros(CUADROS_FRESCOS)
    anterior = None
    pieza = None
    for intento in range(MAX_AJUSTES + 1):
        pieza = Main.elegir_pieza(estado["piezas"], objetivo, EJE_BANDA)
        if pieza is None:
            print("   sin pieza detectada")
            return None, ms_px
        pos = pieza[eje]
        if anterior and not pieza["toca_borde"] and not anterior[3]:
            movido = (pos - anterior[0]) * SENTIDO_AVANCE * anterior[2]
            ms_px = Main.aprender_ms_por_pixel(ms_px, anterior[1], movido)
        error = objetivo - pos
        print(f"   intento {intento}: pos={pos:.0f} error={error:+.0f}px "
              f"borde={pieza['toca_borde']} ms/px={ms_px:.2f}")
        if (abs(error) <= TOLERANCIA_PX and not pieza["toca_borde"]) or intento == MAX_AJUSTES:
            break
        avance = error * SENTIDO_AVANCE
        d = 1 if avance > 0 else -1
        ms = Main.calcular_pulso(avance, ms_px)
        ard.write(f"{'f' if d > 0 else 'v'}{ms}\n".encode())
        anterior = (pos, ms, d, pieza["toca_borde"])
        time.sleep(ms / 1000 + ESPERA_ASENTAR)
        esperar_cuadros(CUADROS_FRESCOS)
    return pieza, ms_px


def prueba_ciclo(ard, n):
    os.makedirs(CARPETA, exist_ok=True)
    ms_px = Main.MS_POR_PIXEL
    ard.write(b"i")
    ard.write(b"a")
    for k in range(n):
        print(f"Esperando pieza {k + 1}/{n}... (coloca una pieza en la banda)")
        t_ir = time.time()
        while ard.readline().decode(errors="ignore").strip() != "P":
            pass
        print(f" P recibido ({time.time() - t_ir:.1f}s)")
        time.sleep(ESPERA_ASENTAR)
        esperar_cuadros(CUADROS_FRESCOS)
        llegada = Main.elegir_pieza(estado["piezas"])
        if llegada:
            centro = (estado["ancho"] if EJE_BANDA == "x" else estado["alto"]) / 2
            pos = llegada["cx"] if EJE_BANDA == "x" else llegada["cy"]
            print(f" llegada: pos={pos:.0f} (centro {centro:.0f}) -> desfase {pos - centro:+.0f}px")
        pieza, ms_px = centrar(ard, ms_px)
        if pieza is None or pieza["toca_borde"]:
            etiqueta = "Descarte"
        else:
            etiqueta = pieza["etiqueta"]
        ard.write({"Tuerca": b"t", "Rondana": b"r"}.get(etiqueta, b"d"))
        print(f" Clasificada: {etiqueta}")
        if estado["cuadro"] is not None:
            # imencode + tofile: cv2.imwrite falla con rutas con acentos ("Módulo")
            ok, datos = cv2.imencode(".jpg", estado["cuadro"])
            datos.tofile(os.path.join(CARPETA, f"pieza_{k + 1}_{etiqueta}.jpg"))
            ok, datos = cv2.imencode(".png", estado["crudo"])
            datos.tofile(os.path.join(CARPETA, f"pieza_{k + 1}_crudo.png"))
    ard.write(b"x")


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "servos"
    ard = serial.Serial(buscar_puerto(), 9600, timeout=30)
    time.sleep(2.5)
    ard.reset_input_buffer()
    if modo == "servos":
        prueba_servos(ard)
    else:
        threading.Thread(target=hilo_camara, daemon=True).start()
        time.sleep(2)
        prueba_ciclo(ard, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    ard.close()


if __name__ == "__main__":
    main()
