#include <SoftwareSerial.h>
#include <Servo.h>

SoftwareSerial BT(10, 11); // RX, TX

Servo servo1;
Servo servo2;

const int SERVO1_PIN = 6;
const int SERVO2_PIN = 5;

const int SERVO1_HOME = 180;
const int SERVO2_HOME = 0;

const int SERVO1_PULL = 0;
const int SERVO2_PULL = 180;

const int SERVO1_MID = 90;
const int SERVO2_MID = 90;

bool running = false;

void logBoth(const String &msg) {
  Serial.println(msg);  // Arduino Serial Monitor
  BT.println(msg);      // Python/telefon preko Bluetootha
}

void homeServos() {
  servo1.write(SERVO1_HOME);
  servo2.write(SERVO2_HOME);

  logBoth("HOME: servo1=180, servo2=0");
}

void openServos() {
  servo1.write(SERVO1_HOME);
  servo2.write(SERVO2_HOME);

  logBoth("OPEN: servo1=180, servo2=0");
}

void closeServos() {
  servo1.write(SERVO1_PULL);
  servo2.write(SERVO2_PULL);

  logBoth("CLOSE: servo1=0, servo2=180");
}

void stopAll() {
  running = false;
  servo1.write(SERVO1_HOME);
  servo2.write(SERVO2_HOME);

  logBoth("STOP + HOME");
}

bool readCommand() {
  if (!BT.available()) return false;

  char c = BT.read();

  Serial.print("Primljena Bluetooth komanda: ");
  Serial.println(c);

  if (c == 'g' || c == 'G') {
    running = true;
    logBoth("START GRASP");
  } 
  else if (c == 'f' || c == 'F' || c == 's' || c == 'S') {
    stopAll();
  } 
  else if (c == 'h' || c == 'H') {
    running = false;
    homeServos();
  } 
  else if (c == 'o' || c == 'O') {
    running = false;
    openServos();
  } 
  else if (c == 'c' || c == 'C') {
    running = false;
    closeServos();
  } 
  else if (c == '1') {
    running = false;
    logBoth("TEST SERVO 1");
    servo1.write(SERVO1_PULL);
    delay(700);
    servo1.write(SERVO1_HOME);
    logBoth("TEST SERVO 1 GOTOV");
  } 
  else if (c == '2') {
    running = false;
    logBoth("TEST SERVO 2");
    servo2.write(SERVO2_PULL);
    delay(700);
    servo2.write(SERVO2_HOME);
    logBoth("TEST SERVO 2 GOTOV");
  } 
  else {
    logBoth("NEPOZNATA KOMANDA");
  }

  return true;
}

bool waitWithStop(int ms) {
  int passed = 0;

  while (passed < ms) {
    readCommand();
    if (!running) return false;
    delay(20);
    passed += 20;
  }

  return true;
}

bool moveServo(Servo &servo, int from, int to, int stepDelay, const String &name) {
  Serial.print(name);
  Serial.print(": ");
  Serial.print(from);
  Serial.print(" -> ");
  Serial.println(to);

  if (from < to) {
    for (int p = from; p <= to; p++) {
      readCommand();
      if (!running) return false;

      servo.write(p);

      if (p % 30 == 0) {
        Serial.print(name);
        Serial.print(" pozicija: ");
        Serial.println(p);
      }

      delay(stepDelay);
    }
  } else {
    for (int p = from; p >= to; p--) {
      readCommand();
      if (!running) return false;

      servo.write(p);

      if (p % 30 == 0) {
        Serial.print(name);
        Serial.print(" pozicija: ");
        Serial.println(p);
      }

      delay(stepDelay);
    }
  }

  return true;
}

void graspSequence() {
  logBoth("FAZA 1: PAKOVANJE / CURL");
  if (!moveServo(servo1, SERVO1_HOME, SERVO1_PULL, 10, "Servo1")) return;
  if (!waitWithStop(300)) return;

  logBoth("FAZA 2: OTVARANJE / REACH");
  if (!moveServo(servo2, SERVO2_HOME, SERVO2_PULL, 10, "Servo2")) return;
  if (!waitWithStop(300)) return;

  logBoth("FAZA 3: OMOTAVANJE / WRAP");
  servo1.write(SERVO1_MID);
  Serial.println("Servo1 pozicija: 90");
  if (!waitWithStop(200)) return;

  if (!moveServo(servo2, SERVO2_PULL, SERVO2_MID, 15, "Servo2")) return;
  if (!waitWithStop(400)) return;

  logBoth("FAZA 4: ZATEZANJE / GRIP");
  if (!moveServo(servo1, SERVO1_MID, SERVO1_PULL, 8, "Servo1")) return;
  if (!moveServo(servo2, SERVO2_MID, SERVO2_PULL, 8, "Servo2")) return;
  if (!waitWithStop(700)) return;

  logBoth("DRZI OBJEKAT");
  running = false;
}

void setup() {
  Serial.begin(9600);
  BT.begin(9600);

  servo1.attach(SERVO1_PIN);
  servo2.attach(SERVO2_PIN);

  delay(500);

  Serial.println("================================");
  Serial.println("Arduino + HC-06 + Grappler");
  Serial.println("Serial Monitor aktivan");
  Serial.println("Komande: g=start, f=stop, h=home, o=open, c=close, 1=test1, 2=test2");
  Serial.println("================================");

  BT.println("Grappler spreman");
  BT.println("g=start, f=stop, h=home, o=open, c=close, 1=test1, 2=test2");

  homeServos();
}

void loop() {
  readCommand();

  if (Serial.available()) {    
    char c = Serial.read();

    Serial.print("Komanda iz Serial Monitora: ");
    Serial.println(c);

    BT.write(c);

    if (c == 'g' || c == 'G') {
      running = true;
      logBoth("START GRASP preko Serial Monitora");
    }

    if (c == 'f' || c == 'F') {
      stopAll();
    }

    if (c == 'h' || c == 'H') {
      running = false;
      homeServos();
    }
  }

  if (running) {
    graspSequence();
  }
}