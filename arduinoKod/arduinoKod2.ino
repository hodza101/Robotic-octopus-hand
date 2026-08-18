#include <SoftwareSerial.h>
#include <Servo.h>

// ============================================================
//  SPIROB GRAPPLER - QUIET / STABLE VERSION
//  Arduino Uno + HC-06 + 2 servo motora
//
//  Cilj ove verzije:
//  - bez stalne telemetrije prema aplikaciji
//  - bez stalnog ispisivanja na Arduino Serial Monitor
//  - manje trzanja servoa nakon hvatanja
//  - kompatibilno sa PC aplikacijom
// ============================================================

SoftwareSerial BT(10, 11); // RX, TX

Servo servo1;
Servo servo2;

// -----------------------------
// PINOVI
// -----------------------------
const byte SERVO1_PIN = 6;
const byte SERVO2_PIN = 5;

// -----------------------------
// DEBUG
// Ako želiš ispis na Arduino Serial Monitoru, stavi true.
// Za normalan rad ostavi false.
// -----------------------------
const bool DEBUG_SERIAL = false;
const bool SEND_BT_STATUS = true;

// -----------------------------
// SERVO POSTAVKE
// Važno: ne koristimo ekstremnih 0 i 180 jer servoi često zuje/trzaju na krajevima.
// Ako treba više hoda, pažljivo povećavaj prema 0/180.
// -----------------------------
const int SERVO1_HOME = 170;
const int SERVO2_HOME = 10;

const int SERVO1_PULL = 10;
const int SERVO2_PULL = 170;

const int SERVO1_MID = 90;
const int SERVO2_MID = 90;

const int SERVO_MIN_ANGLE = 0;
const int SERVO_MAX_ANGLE = 180;

// Ako true: nakon što uhvati objekat, Arduino odspoji servo signal.
// To često smanji trzanje/zujanje.
// Ako se sajla popušta i gripper izgubi hvat, stavi false.
const bool DETACH_AFTER_GRIP = true;

// Brzina kretanja.
const unsigned long STEP_INTERVAL_NORMAL = 12;
const unsigned long STEP_INTERVAL_FAST = 8;
const unsigned long STEP_INTERVAL_SLOW = 16;

// -----------------------------
// STANJE
// -----------------------------
enum State {
  IDLE,
  HOMING,
  OPENING,
  CLOSING,
  TEST_SERVO1_PULL,
  TEST_SERVO1_HOME,
  TEST_SERVO2_PULL,
  TEST_SERVO2_HOME,
  GRASP_CURL,
  GRASP_REACH,
  GRASP_WRAP,
  GRASP_GRIP,
  HOLDING,
  ESTOP
};

State state = IDLE;

int servo1Current = SERVO1_HOME;
int servo2Current = SERVO2_HOME;
int servo1Target = SERVO1_HOME;
int servo2Target = SERVO2_HOME;

unsigned long lastStepTime = 0;
unsigned long phaseStartTime = 0;
unsigned long activeStepInterval = STEP_INTERVAL_NORMAL;

char buffer[48];
byte bufferLen = 0;

// ============================================================
//  POMOĆNE FUNKCIJE
// ============================================================

int clampAngle(int x) {
  if (x < SERVO_MIN_ANGLE) return SERVO_MIN_ANGLE;
  if (x > SERVO_MAX_ANGLE) return SERVO_MAX_ANGLE;
  return x;
}

void debugPrint(const char *msg) {
  if (DEBUG_SERIAL) Serial.println(msg);
}

void btPrint(const char *msg) {
  if (SEND_BT_STATUS) BT.println(msg);
}

void statusMsg(const char *msg) {
  debugPrint(msg);
  btPrint(msg);
}

void attachServosIfNeeded() {
  if (!servo1.attached()) servo1.attach(SERVO1_PIN);
  if (!servo2.attached()) servo2.attach(SERVO2_PIN);
}

void detachServos() {
  if (servo1.attached()) servo1.detach();
  if (servo2.attached()) servo2.detach();
}

void writeServo1(int angle) {
  attachServosIfNeeded();
  servo1Current = clampAngle(angle);
  servo1.write(servo1Current);
}

void writeServo2(int angle) {
  attachServosIfNeeded();
  servo2Current = clampAngle(angle);
  servo2.write(servo2Current);
}

void setTargets(int s1, int s2, unsigned long intervalMs) {
  attachServosIfNeeded();
  servo1Target = clampAngle(s1);
  servo2Target = clampAngle(s2);
  activeStepInterval = intervalMs;
}

bool atTarget() {
  return servo1Current == servo1Target && servo2Current == servo2Target;
}

void updateServos() {
  if (state == HOLDING && DETACH_AFTER_GRIP) return;

  unsigned long now = millis();
  if (now - lastStepTime < activeStepInterval) return;
  lastStepTime = now;

  if (servo1Current < servo1Target) writeServo1(servo1Current + 1);
  else if (servo1Current > servo1Target) writeServo1(servo1Current - 1);

  if (servo2Current < servo2Target) writeServo2(servo2Current + 1);
  else if (servo2Current > servo2Target) writeServo2(servo2Current - 1);
}

// ============================================================
//  STATE MACHINE
// ============================================================

void enterState(State next) {
  state = next;
  phaseStartTime = millis();
  attachServosIfNeeded();

  switch (state) {
    case IDLE:
      break;

    case HOMING:
      statusMsg("HOME");
      setTargets(SERVO1_HOME, SERVO2_HOME, STEP_INTERVAL_FAST);
      break;

    case OPENING:
      statusMsg("OPEN");
      setTargets(SERVO1_HOME, SERVO2_HOME, STEP_INTERVAL_NORMAL);
      break;

    case CLOSING:
      statusMsg("CLOSE");
      setTargets(SERVO1_PULL, SERVO2_PULL, STEP_INTERVAL_NORMAL);
      break;

    case TEST_SERVO1_PULL:
      statusMsg("TEST SERVO 1");
      setTargets(SERVO1_PULL, servo2Current, STEP_INTERVAL_FAST);
      break;

    case TEST_SERVO1_HOME:
      setTargets(SERVO1_HOME, servo2Current, STEP_INTERVAL_FAST);
      break;

    case TEST_SERVO2_PULL:
      statusMsg("TEST SERVO 2");
      setTargets(servo1Current, SERVO2_PULL, STEP_INTERVAL_FAST);
      break;

    case TEST_SERVO2_HOME:
      setTargets(servo1Current, SERVO2_HOME, STEP_INTERVAL_FAST);
      break;

    case GRASP_CURL:
      statusMsg("START GRASP");
      statusMsg("FAZA 1: CURL");
      setTargets(SERVO1_PULL, SERVO2_HOME, STEP_INTERVAL_NORMAL);
      break;

    case GRASP_REACH:
      statusMsg("FAZA 2: REACH");
      setTargets(SERVO1_PULL, SERVO2_PULL, STEP_INTERVAL_NORMAL);
      break;

    case GRASP_WRAP:
      statusMsg("FAZA 3: WRAP");
      setTargets(SERVO1_MID, SERVO2_MID, STEP_INTERVAL_SLOW);
      break;

    case GRASP_GRIP:
      statusMsg("FAZA 4: GRIP");
      setTargets(SERVO1_PULL, SERVO2_PULL, STEP_INTERVAL_FAST);
      break;

    case HOLDING:
      statusMsg("DRZI OBJEKAT");
      if (DETACH_AFTER_GRIP) {
        delay(120);
        detachServos();
        statusMsg("SERVO SIGNAL OFF");
      }
      break;

    case ESTOP:
      statusMsg("STOP + HOME");
      setTargets(SERVO1_HOME, SERVO2_HOME, STEP_INTERVAL_FAST);
      break;
  }
}

void updateStateMachine() {
  updateServos();

  switch (state) {
    case IDLE:
      break;

    case HOMING:
    case OPENING:
    case CLOSING:
      if (atTarget()) enterState(IDLE);
      break;

    case TEST_SERVO1_PULL:
      if (atTarget() && millis() - phaseStartTime > 300) enterState(TEST_SERVO1_HOME);
      break;

    case TEST_SERVO1_HOME:
      if (atTarget()) {
        statusMsg("TEST SERVO 1 GOTOV");
        enterState(IDLE);
      }
      break;

    case TEST_SERVO2_PULL:
      if (atTarget() && millis() - phaseStartTime > 300) enterState(TEST_SERVO2_HOME);
      break;

    case TEST_SERVO2_HOME:
      if (atTarget()) {
        statusMsg("TEST SERVO 2 GOTOV");
        enterState(IDLE);
      }
      break;

    case GRASP_CURL:
      if (atTarget() && millis() - phaseStartTime > 250) enterState(GRASP_REACH);
      break;

    case GRASP_REACH:
      if (atTarget() && millis() - phaseStartTime > 250) enterState(GRASP_WRAP);
      break;

    case GRASP_WRAP:
      if (atTarget() && millis() - phaseStartTime > 350) enterState(GRASP_GRIP);
      break;

    case GRASP_GRIP:
      if (atTarget() && millis() - phaseStartTime > 500) enterState(HOLDING);
      break;

    case HOLDING:
      break;

    case ESTOP:
      if (atTarget()) enterState(IDLE);
      break;
  }
}

// ============================================================
//  KOMANDE
// ============================================================

void setServoAngleCommand(char id, const char *valueText) {
  int angle = clampAngle(atoi(valueText));
  attachServosIfNeeded();

  if (id == 'A' || id == 'a') {
    servo1Target = angle;
    statusMsg("SERVO1 SET");
  } else {
    servo2Target = angle;
    statusMsg("SERVO2 SET");
  }

  state = IDLE;
}

void handleCommand(const char *cmd) {
  if (!cmd || cmd[0] == '\0') return;

  char c = cmd[0];

  if (cmd[1] != '\0') {
    if (c == 'A' || c == 'a') {
      setServoAngleCommand('A', cmd + 1);
      return;
    }
    if (c == 'B' || c == 'b') {
      setServoAngleCommand('B', cmd + 1);
      return;
    }
    if (c == 'P' || c == 'p') {
      statusMsg("PID OK");
      return;
    }
  }

  switch (c) {
    case 'g':
    case 'G':
      enterState(GRASP_CURL);
      break;

    case 'f':
    case 'F':
    case 's':
    case 'S':
      attachServosIfNeeded();
      enterState(ESTOP);
      break;

    case 'h':
    case 'H':
      enterState(HOMING);
      break;

    case 'o':
    case 'O':
      enterState(OPENING);
      break;

    case 'c':
    case 'C':
      enterState(CLOSING);
      break;

    case '1':
      enterState(TEST_SERVO1_PULL);
      break;

    case '2':
      enterState(TEST_SERVO2_PULL);
      break;

    case '?':
      btPrint("PONG");
      break;

    default:
      statusMsg("UNKNOWN CMD");
      break;
  }
}

void feedInput(char ch) {
  if (ch == '\r') return;

  if (ch == '\n') {
    buffer[bufferLen] = '\0';
    handleCommand(buffer);
    bufferLen = 0;
    return;
  }

  bool oneCharCommand =
    ch == 'g' || ch == 'G' || ch == 'f' || ch == 'F' || ch == 's' || ch == 'S' ||
    ch == 'h' || ch == 'H' || ch == 'o' || ch == 'O' || ch == 'c' || ch == 'C' ||
    ch == '1' || ch == '2' || ch == '?';

  if (oneCharCommand && bufferLen == 0) {
    char tmp[2] = { ch, '\0' };
    handleCommand(tmp);
    return;
  }

  if (bufferLen < sizeof(buffer) - 1) {
    buffer[bufferLen++] = ch;
  } else {
    bufferLen = 0;
    statusMsg("BUFFER ERROR");
  }
}

void readBluetooth() {
  while (BT.available()) feedInput(BT.read());
}

void readUsbSerial() {
  // USB Serial ostaje moguć za ručni test, ali bez ikakvog automatskog logovanja.
  while (Serial.available()) feedInput(Serial.read());
}

// ============================================================
//  SETUP / LOOP
// ============================================================

void setup() {
  Serial.begin(9600);
  BT.begin(9600);

  servo1.attach(SERVO1_PIN);
  servo2.attach(SERVO2_PIN);

  writeServo1(SERVO1_HOME);
  writeServo2(SERVO2_HOME);
  setTargets(SERVO1_HOME, SERVO2_HOME, STEP_INTERVAL_FAST);

  delay(300);

  statusMsg("READY");
}

void loop() {
  readBluetooth();
  readUsbSerial();
  updateStateMachine();
}
