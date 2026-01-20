#include <Wire.h>
#include <Servo.h>
#include <LiquidCrystal_I2C.h>

// ===== ПИНЫ =====
#define SERVO_PIN 3
#define LED_RED 4
#define LED_YELLOW 5
#define LED_GREEN 6

#define TRIG_PIN 8
#define ECHO_PIN 9

// ===== НАСТРОЙКИ =====
#define OPEN_ANGLE 90
#define CLOSE_ANGLE 0

#define CAR_NEAR 15      // машина подъехала
#define CAR_GONE 30      // машина уехала
#define BLOCK_DIST 10    // защита от прижатия

#define TOTAL_SPOTS 10

// ===== ОБЪЕКТЫ =====
Servo gateServo;
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ===== СОСТОЯНИЯ =====
bool gateOpen = false;
bool carUnderGate = false;
bool waitForCar = false;

int freeSpots = TOTAL_SPOTS;
unsigned long lastUltrasonicCheck = 0;

// ===== SETUP =====
void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  pinMode(LED_RED, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);

  gateServo.attach(SERVO_PIN);
  gateServo.write(CLOSE_ANGLE);

  lcd.init();
  lcd.backlight();

  showStatus("SYSTEM READY", freeSpots);
  setTrafficRed();

  Serial.println("✅ ARDUINO READY");
}

// ===== LOOP =====
void loop() {
  handleSerial();
  handleUltrasonic();
}

// ===== SERIAL =====
void handleSerial() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if (cmd.startsWith("DISPLAY:")) {
    String plate = cmd.substring(8);
    showPlate(plate);
  }

  else if (cmd == "OPEN") {
    openGate();
  }
}

// ===== УЛЬТРАЗВУК =====
void handleUltrasonic() {
  if (!gateOpen) return;
  if (millis() - lastUltrasonicCheck < 200) return;
  lastUltrasonicCheck = millis();

  long d = getDistance();

  // машина появилась
  if (d > 0 && d < CAR_NEAR && !carUnderGate) {
    carUnderGate = true;
    waitForCar = true;
  }

  // машина уехала
  if (d > CAR_GONE && carUnderGate) {
    carUnderGate = false;
    processExitOrEntry();
    closeGate();
  }
}

// ===== DIST =====
long getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long t = pulseIn(ECHO_PIN, HIGH, 30000);
  if (t == 0) return -1;
  return t * 0.034 / 2;
}

// ===== ЛОГИКА ПАРКОВКИ =====
void processExitOrEntry() {
  if (freeSpots > 0) {
    freeSpots--;  // въезд
  } else if (freeSpots < TOTAL_SPOTS) {
    freeSpots++;  // выезд
  }
  showStatus("FREE:", freeSpots);
}

// ===== GATE =====
void openGate() {
  gateServo.write(OPEN_ANGLE);
  gateOpen = true;
  waitForCar = true;
  carUnderGate = false;
  setTrafficGreen();
}

void closeGate() {
  if (getDistance() > 0 && getDistance() < BLOCK_DIST) return;

  gateServo.write(CLOSE_ANGLE);
  gateOpen = false;
  setTrafficRed();
}

// ===== DISPLAY =====
void showPlate(String plate) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("PLATE:");
  lcd.setCursor(0, 1);
  lcd.print(plate);
}

void showStatus(String label, int value) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(label);
  lcd.setCursor(0, 1);
  lcd.print("FREE: ");
  lcd.print(value);
}

// ===== TRAFFIC =====
void setTrafficRed() {
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_YELLOW, LOW);
}

void setTrafficGreen() {
  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_YELLOW, LOW);
}
