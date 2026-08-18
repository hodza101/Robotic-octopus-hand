/*
  SpiRob Grappler - STM32F103C8T6 Keil/C++ firmware
  MCU: STM32F103C8T6 / Blue Pill
  IDE: Keil uVision
  Style: CMSIS / register-level, bez Arduino biblioteka

  Pin mapa:
    HC-06 TXD  -> PA10  USART1_RX
    HC-06 RXD  -> PA9   USART1_TX
    Servo 1    -> PA0   TIM2_CH1
    Servo 2    -> PA1   TIM2_CH2
    Servo V+   -> vanjsko 5V/6V napajanje
    Servo GND  -> GND vanjskog napajanja
    STM32 GND  -> GND vanjskog napajanja

  Komunikacioni protokol:
    <g>     UHVATI
    <f>     E-STOP / PUSTI / HOME
    <h>     HOME
    <o>     OTVORI
    <c>     ZATEGNI
    <1>     TEST SERVO 1
    <2>     TEST SERVO 2
    <?>     PING / STATE
    <A090>  Servo 1 na 90 stepeni
    <B120>  Servo 2 na 120 stepeni

  STM32 odgovara:
    ACK:g
    STATE:S1=5;S2=175;GRIP=100
*/

#include "stm32f10x.h"
#include <stdint.h>

#define SYSCLK_HZ 72000000UL
#define UART_BAUD 9600UL

#define SERVO_MIN_US 700
#define SERVO_MAX_US 2300

#define SERVO1_HOME 175
#define SERVO2_HOME 5
#define SERVO1_GRIP 5
#define SERVO2_GRIP 175

static volatile uint32_t g_ms = 0;

static int servo1_angle = SERVO1_HOME;
static int servo2_angle = SERVO2_HOME;

extern "C" void SysTick_Handler(void) {
  g_ms++;
}

static void delay_ms(uint32_t ms) {
  uint32_t start = g_ms;
  while ((g_ms - start) < ms) {
    __NOP();
  }
}

static int clamp_int(int x, int lo, int hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

static int parse_3_digits(const char *s) {
  int x = 0;
  for (int i = 0; i < 3; i++) {
    if (s[i] < '0' || s[i] > '9') return -1;
    x = x * 10 + (s[i] - '0');
  }
  return x;
}

static void clock_init_72mhz(void) {
  RCC->CR |= RCC_CR_HSEON;

  uint32_t timeout = 0;
  while (!(RCC->CR & RCC_CR_HSERDY)) {
    timeout++;
    if (timeout > 1000000UL) {
      break;
    }
  }

  if (RCC->CR & RCC_CR_HSERDY) {
    FLASH->ACR = FLASH_ACR_PRFTBE | FLASH_ACR_LATENCY_2;

    RCC->CFGR &= ~(RCC_CFGR_HPRE | RCC_CFGR_PPRE1 | RCC_CFGR_PPRE2 |
                   RCC_CFGR_PLLSRC | RCC_CFGR_PLLMULL);

    RCC->CFGR |= RCC_CFGR_HPRE_DIV1;
    RCC->CFGR |= RCC_CFGR_PPRE1_DIV2;
    RCC->CFGR |= RCC_CFGR_PPRE2_DIV1;
    RCC->CFGR |= RCC_CFGR_PLLSRC;
    RCC->CFGR |= RCC_CFGR_PLLMULL9;

    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY)) {
    }

    RCC->CFGR &= ~RCC_CFGR_SW;
    RCC->CFGR |= RCC_CFGR_SW_PLL;

    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL) {
    }
  }
}

static void gpio_init(void) {
  RCC->APB2ENR |= RCC_APB2ENR_IOPAEN;
  RCC->APB2ENR |= RCC_APB2ENR_AFIOEN;

  /*
    PA0 = TIM2_CH1 AF push-pull 50MHz -> 0xB
    PA1 = TIM2_CH2 AF push-pull 50MHz -> 0xB
  */
  GPIOA->CRL &= ~((0xFUL << (0 * 4)) | (0xFUL << (1 * 4)));
  GPIOA->CRL |=  ((0xBUL << (0 * 4)) | (0xBUL << (1 * 4)));

  /*
    PA9  = USART1_TX AF push-pull 50MHz -> 0xB
    PA10 = USART1_RX input floating     -> 0x4
  */
  GPIOA->CRH &= ~((0xFUL << ((9 - 8) * 4)) | (0xFUL << ((10 - 8) * 4)));
  GPIOA->CRH |=  ((0xBUL << ((9 - 8) * 4)) | (0x4UL << ((10 - 8) * 4)));
}

static void uart1_init(void) {
  RCC->APB2ENR |= RCC_APB2ENR_USART1EN;

  USART1->CR1 = 0;
  USART1->BRR = SYSCLK_HZ / UART_BAUD;
  USART1->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}

static void uart_send_char(char c) {
  while (!(USART1->SR & USART_SR_TXE)) {
  }
  USART1->DR = (uint16_t)c;
}

static void uart_send(const char *s) {
  while (*s) {
    uart_send_char(*s++);
  }
}

static void uart_send_int(int x) {
  char buf[12];
  int i = 0;

  if (x == 0) {
    uart_send_char('0');
    return;
  }

  if (x < 0) {
    uart_send_char('-');
    x = -x;
  }

  while (x > 0 && i < 11) {
    buf[i++] = char('0' + (x % 10));
    x /= 10;
  }

  while (i > 0) {
    uart_send_char(buf[--i]);
  }
}

static int uart_available(void) {
  return (USART1->SR & USART_SR_RXNE) != 0;
}

static char uart_read_char(void) {
  return (char)(USART1->DR & 0xFF);
}

static void tim2_pwm_init(void) {
  RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;

  /*
    TIM2 radi na 72 MHz jer APB1 prescaler nije 1, pa timer clock = 2 * PCLK1.
    PSC = 71 -> 1 tick = 1 us
    ARR = 19999 -> period = 20 ms = 50 Hz
  */
  TIM2->PSC = 72 - 1;
  TIM2->ARR = 20000 - 1;

  TIM2->CCR1 = 1500;
  TIM2->CCR2 = 1500;

  TIM2->CCMR1 = 0;
  TIM2->CCMR1 |= (6UL << 4);   // OC1M = PWM mode 1
  TIM2->CCMR1 |= (1UL << 3);   // OC1PE
  TIM2->CCMR1 |= (6UL << 12);  // OC2M = PWM mode 1
  TIM2->CCMR1 |= (1UL << 11);  // OC2PE

  TIM2->CCER = 0;
  TIM2->CCER |= TIM_CCER_CC1E;
  TIM2->CCER |= TIM_CCER_CC2E;

  TIM2->CR1 |= TIM_CR1_ARPE;
  TIM2->EGR = TIM_EGR_UG;
  TIM2->CR1 |= TIM_CR1_CEN;
}

static int angle_to_us(int angle) {
  angle = clamp_int(angle, 0, 180);
  return SERVO_MIN_US + (angle * (SERVO_MAX_US - SERVO_MIN_US)) / 180;
}

static void servo1_write(int angle) {
  servo1_angle = clamp_int(angle, 0, 180);
  TIM2->CCR1 = (uint16_t)angle_to_us(servo1_angle);
}

static void servo2_write(int angle) {
  servo2_angle = clamp_int(angle, 0, 180);
  TIM2->CCR2 = (uint16_t)angle_to_us(servo2_angle);
}

static int grip_percent(void) {
  int p1_num = SERVO1_HOME - servo1_angle;
  int p1_den = SERVO1_HOME - SERVO1_GRIP;

  int p2_num = servo2_angle - SERVO2_HOME;
  int p2_den = SERVO2_GRIP - SERVO2_HOME;

  int p1 = 0;
  int p2 = 0;

  if (p1_den != 0) p1 = (p1_num * 100) / p1_den;
  if (p2_den != 0) p2 = (p2_num * 100) / p2_den;

  p1 = clamp_int(p1, 0, 100);
  p2 = clamp_int(p2, 0, 100);

  return (p1 + p2) / 2;
}

static void send_state(void) {
  uart_send("STATE:S1=");
  uart_send_int(servo1_angle);
  uart_send(";S2=");
  uart_send_int(servo2_angle);
  uart_send(";GRIP=");
  uart_send_int(grip_percent());
  uart_send("\r\n");
}

static void send_ack(const char *cmd) {
  uart_send("ACK:");
  uart_send(cmd);
  uart_send("\r\n");
  send_state();
}

static void send_err(const char *msg) {
  uart_send("ERR:");
  uart_send(msg);
  uart_send("\r\n");
  send_state();
}

static void set_home(void) {
  servo1_write(SERVO1_HOME);
  servo2_write(SERVO2_HOME);
}

static void set_grip(void) {
  servo1_write(SERVO1_GRIP);
  servo2_write(SERVO2_GRIP);
}

static void test_servo1(void) {
  int old = servo1_angle;
  servo1_write(60);
  delay_ms(350);
  servo1_write(120);
  delay_ms(350);
  servo1_write(old);
}

static void test_servo2(void) {
  int old = servo2_angle;
  servo2_write(60);
  delay_ms(350);
  servo2_write(120);
  delay_ms(350);
  servo2_write(old);
}

static void handle_command(const char *cmd) {
  if (cmd[0] == '\0') {
    return;
  }

  if (cmd[0] == 'g' && cmd[1] == '\0') {
    set_grip();
    send_ack("g");
    return;
  }

  if (cmd[0] == 'c' && cmd[1] == '\0') {
    set_grip();
    send_ack("c");
    return;
  }

  if (cmd[0] == 'f' && cmd[1] == '\0') {
    set_home();
    send_ack("f");
    return;
  }

  if (cmd[0] == 'h' && cmd[1] == '\0') {
    set_home();
    send_ack("h");
    return;
  }

  if (cmd[0] == 'o' && cmd[1] == '\0') {
    set_home();
    send_ack("o");
    return;
  }

  if (cmd[0] == '1' && cmd[1] == '\0') {
    test_servo1();
    send_ack("1");
    return;
  }

  if (cmd[0] == '2' && cmd[1] == '\0') {
    test_servo2();
    send_ack("2");
    return;
  }

  if (cmd[0] == '?' && cmd[1] == '\0') {
    send_ack("?");
    return;
  }

  if ((cmd[0] == 'A' || cmd[0] == 'a') && cmd[1] && cmd[2] && cmd[3] && cmd[4] == '\0') {
    int angle = parse_3_digits(&cmd[1]);
    if (angle < 0 || angle > 180) {
      send_err("bad_A_angle");
      return;
    }
    servo1_write(angle);
    send_ack("A");
    return;
  }

  if ((cmd[0] == 'B' || cmd[0] == 'b') && cmd[1] && cmd[2] && cmd[3] && cmd[4] == '\0') {
    int angle = parse_3_digits(&cmd[1]);
    if (angle < 0 || angle > 180) {
      send_err("bad_B_angle");
      return;
    }
    servo2_write(angle);
    send_ack("B");
    return;
  }

  send_err("unknown_command");
}

static void protocol_update(void) {
  static char frame[16];
  static uint8_t idx = 0;
  static uint8_t in_frame = 0;

  while (uart_available()) {
    char c = uart_read_char();

    if (c == '\r' || c == '\n' || c == ' ') {
      continue;
    }

    if (c == '<') {
      in_frame = 1;
      idx = 0;
      continue;
    }

    if (c == '>') {
      if (in_frame) {
        frame[idx] = '\0';
        handle_command(frame);
        idx = 0;
        in_frame = 0;
      }
      continue;
    }

    if (in_frame) {
      if (idx < sizeof(frame) - 1) {
        frame[idx++] = c;
      } else {
        idx = 0;
        in_frame = 0;
        send_err("frame_too_long");
      }
      continue;
    }

    /*
      Kompatibilnost:
      Ako korisnik testira direktno iz Bluetooth terminala i pošalje samo jedan znak
      bez < >, komanda će opet raditi.
    */
    if (c == 'g' || c == 'f' || c == 'h' || c == 'o' || c == 'c' ||
        c == '1' || c == '2' || c == '?') {
      char raw[2];
      raw[0] = c;
      raw[1] = '\0';
      handle_command(raw);
    }
  }
}

int main(void) {
  clock_init_72mhz();
  SysTick_Config(SYSCLK_HZ / 1000UL);

  gpio_init();
  uart1_init();
  tim2_pwm_init();

  delay_ms(200);
  set_home();

  uart_send("\r\nSpiRob STM32F103C8T6 controller ready\r\n");
  send_state();

  while (1) {
    protocol_update();
  }
}
