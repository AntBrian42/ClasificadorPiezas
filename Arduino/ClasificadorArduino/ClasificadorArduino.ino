#include <Servo.h>
Servo banda;
Servo frente;
Servo lados;
int ENA = 9;
int IN1 = 22;
int IN2 = 24;

int infrarrojo = 30;
int valorIR = 0;
bool vibracionActiva = false;

// Velocidades del servo de la banda (rotación continua)
const int BANDA_AVANCE = 25;
const int BANDA_RETROCESO = 155;   // ajustar si la banda retrocede muy rápido/lento
const int BANDA_DETENIDA = 90;

// Tiempos (ms)
// Del IR a la cámara. Medido: con 9400 las piezas llegaban ~94 px (~450 ms) pasadas
const unsigned long TIEMPO_A_CAMARA = 8950;
const unsigned long ESPERA_TRAS_CLASIFICAR = 2500;   // banda parada tras recibir t/r/d
const unsigned long TIMEOUT_CLASIFICACION = 15000;   // si la PC no responde, reanuda
const unsigned long PULSO_MAXIMO = 1500;
const unsigned long PASO_SERVOS = 700;               // entre cada movimiento de servo

// Ángulos de la compuerta (tomados de la prueba ServosPrueba que funciona)
const int LADOS_CENTRO = 90;
const int LADOS_TUERCA = 55;      // derecha
const int LADOS_RONDANA = 140;    // izquierda
// En descarte la plataforma se ladeaba a la derecha con 90; se compensa hacia
// la izquierda (ángulo mayor = izquierda). 100, 95 y 92 se pasaban a la izquierda.
const int LADOS_DESCARTE = 90;
// El servo se detiene en un punto un poco distinto según de qué lado llega
// (venir de tuerca=55 o de rondana=140). Para que el descarte quede siempre
// igual, primero va a este ángulo y después baja a LADOS_DESCARTE.
const int LADOS_APROXIMACION = 100;
const unsigned long PASO_APROXIMACION = 400;
const int FRENTE_DESCARTE = 150;  // al frente
const int FRENTE_TUERCA = 110;
const int FRENTE_RONDANA = 90;

unsigned long tiempoAnterior = 0;
unsigned long tiempoParada = 0;
unsigned long tiempoServos = 0;
unsigned long duracionPulso = 0;
int estadoBanda = 0;
int estadoTrasPulso = 3;
// 0 = detenida, 1 = esperando pieza en IR, 2 = viajando a cámara,
// 3 = parada bajo cámara esperando ajuste o clasificación,
// 4 = pulso de ajuste en curso, 5 = clasificada, esperando para reanudar
int estadoServos = 0;
int tipoPieza = 0;

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50);   // para que parseInt no bloquee
  banda.attach(8);
  frente.attach(13);
  lados.attach(10);
  pinMode(infrarrojo, INPUT);
  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  banda.write(BANDA_DETENIDA);
  lados.write(LADOS_CENTRO);
  frente.write(FRENTE_RONDANA);
  Serial.println("LISTO");
}

void loop() {
  if (Serial.available() > 0) {
    int opcion = Serial.read();
    if (opcion == 'a') {
      vibracionActiva = true;
    }
    if (opcion == 'b') {
      vibracionActiva = false;
    }
    if (opcion == 'i') {
      estadoBanda = 1;
      banda.write(BANDA_AVANCE);
    }
    if (opcion == 'x') {
      estadoBanda = 0;
      banda.write(BANDA_DETENIDA);
      vibracionActiva = false;
      estadoServos = 0;
    }
    // Pulso de ajuste: "f<ms>\n" avanza, "v<ms>\n" retrocede
    if (opcion == 'f' || opcion == 'v') {
      long ms = Serial.parseInt();
      // Se aceptan bajo la cámara (3) o con el sistema detenido (0, para calibrar)
      if ((estadoBanda == 3 || estadoBanda == 0) && ms > 0) {
        if (ms > (long)PULSO_MAXIMO) ms = PULSO_MAXIMO;
        duracionPulso = ms;
        estadoTrasPulso = estadoBanda;
        banda.write(opcion == 'f' ? BANDA_AVANCE : BANDA_RETROCESO);
        tiempoAnterior = millis();
        estadoBanda = 4;
      }
    }
    if (opcion == 't' || opcion == 'r' || opcion == 'd') {
      iniciarServos(opcion);
      if (estadoBanda == 3 || estadoBanda == 4) {
        banda.write(BANDA_DETENIDA);
        tiempoAnterior = millis();
        estadoBanda = 5;
      }
    }
  }

  vibracion();

  unsigned long tiempoActual = millis();
  valorIR = digitalRead(infrarrojo);

  switch (estadoBanda) {
    case 1:
      if (valorIR == LOW) {
        tiempoAnterior = tiempoActual;
        estadoBanda = 2;
      }
      break;

    case 2:
      if (tiempoActual - tiempoAnterior >= TIEMPO_A_CAMARA) {
        banda.write(BANDA_DETENIDA);
        Serial.println("P");
        tiempoParada = tiempoActual;
        estadoBanda = 3;
      }
      break;

    case 3:
      // Espera pulsos de ajuste o la clasificación desde la PC
      if (tiempoActual - tiempoParada >= TIMEOUT_CLASIFICACION) {
        banda.write(BANDA_AVANCE);
        estadoBanda = 1;
      }
      break;

    case 4:
      if (tiempoActual - tiempoAnterior >= duracionPulso) {
        banda.write(BANDA_DETENIDA);
        estadoBanda = estadoTrasPulso;
        Serial.println("OK");
      }
      break;

    case 5:
      if (tiempoActual - tiempoAnterior >= ESPERA_TRAS_CLASIFICAR) {
        banda.write(BANDA_AVANCE);
        estadoBanda = 1;
      }
      break;
  }

  // Secuencia de servos (siempre desde lados al centro, igual que la prueba):
  //   paso 1: lados al centro
  //   paso 2: frente a su posición (150 descarte, 110 tuerca, 90 rondana)
  //   paso 3: lados a su posición (55 tuerca, 140 rondana; descarte no lo mueve)
  switch (estadoServos) {
    case 10:
      // Descarte: llega a su ángulo siempre desde el mismo lado
      if (tiempoActual - tiempoServos >= PASO_APROXIMACION) {
        lados.write(LADOS_DESCARTE);
        tiempoServos = tiempoActual;
        estadoServos = 1;
      }
      break;

    case 1:
      if (tiempoActual - tiempoServos >= PASO_SERVOS) {
        if (tipoPieza == 'd') frente.write(FRENTE_DESCARTE);
        if (tipoPieza == 't') frente.write(FRENTE_TUERCA);
        if (tipoPieza == 'r') frente.write(FRENTE_RONDANA);
        tiempoServos = tiempoActual;
        estadoServos = 2;
      }
      break;

    case 2:
      if (tiempoActual - tiempoServos >= PASO_SERVOS) {
        if (tipoPieza == 't') lados.write(LADOS_TUERCA);
        if (tipoPieza == 'r') lados.write(LADOS_RONDANA);
        estadoServos = 0;   // la posición final se mantiene hasta la siguiente pieza
      }
      break;
  }
}

void iniciarServos(int tipo) {
  tipoPieza = tipo;
  tiempoServos = millis();
  if (tipo == 'd') {
    lados.write(LADOS_APROXIMACION);
    estadoServos = 10;   // luego baja a LADOS_DESCARTE
  } else {
    lados.write(LADOS_CENTRO);
    estadoServos = 1;
  }
}

void vibracion() {
  // Solo vibra mientras se espera una pieza: así entra una a la vez a la banda
  if (vibracionActiva && estadoBanda == 1) {
    analogWrite(ENA, 100);
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, HIGH);
  } else {
    analogWrite(ENA, 100);
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
  }
}
