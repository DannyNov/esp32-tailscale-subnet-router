#pragma once
#include <assert.h>
#define portMAX_DELAY 0xffffffffu
#define configASSERT assert
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(m) ((void)(m))
#define portEXIT_CRITICAL(m) ((void)(m))
