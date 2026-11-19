#pragma once
#include <windows.h>
typedef CRITICAL_SECTION pthread_mutex_t;
static int pthread_mutex_init(pthread_mutex_t *m,void*a){(void)a;InitializeCriticalSection(m);return 0;}
static int pthread_mutex_destroy(pthread_mutex_t*m){DeleteCriticalSection(m);return 0;}
static int pthread_mutex_lock(pthread_mutex_t*m){EnterCriticalSection(m);return 0;}
static int pthread_mutex_unlock(pthread_mutex_t*m){LeaveCriticalSection(m);return 0;}
