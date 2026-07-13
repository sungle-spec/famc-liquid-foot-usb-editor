/*
 * lf_interpose.c - DYLD interposer to capture the LF+ Editor's serial traffic.
 *
 * Hooks read/write (filtered to the /dev/cu.usbserial fd via F_GETPATH) and
 * ioctl (to catch the baud set via IOSSIOSPEED). Logs hex to a file.
 *
 * Build (x86_64, to match the Rosetta process):
 *   clang -arch x86_64 -dynamiclib -O2 -o scripts/ARTIFACTS/lf_interpose.dylib scripts/lf_interpose.c
 * Inject:
 *   DYLD_INSERT_LIBRARIES=.../lf_interpose.dylib "<app>/Contents/MacOS/LF+ Editor"
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/syslimits.h>
#include <stdarg.h>
#include <pthread.h>

/* Log destination: set LF_CAPTURE_LOG, or it falls back to /tmp. */
#define LOGPATH_FALLBACK "/tmp/lf_runtime_capture.txt"
#define IOSSIOSPEED _IOW('T', 2, unsigned int)  /* set arbitrary baud */

typedef struct interpose_s { const void *repl; const void *orig; } interpose_t;
#define DYLD_INTERPOSE(_r,_o) __attribute__((used)) static const interpose_t \
  _interpose_##_o __attribute__((section("__DATA,__interpose"))) = {(const void*)_r,(const void*)_o};

static pthread_mutex_t mtx = PTHREAD_MUTEX_INITIALIZER;
static FILE *lf = NULL;

static FILE* L(void){
    if(!lf){
        const char *p = getenv("LF_CAPTURE_LOG");
        lf = fopen(p && *p ? p : LOGPATH_FALLBACK, "a");
        if(lf) setvbuf(lf,NULL,_IOLBF,0);
    }
    return lf;
}

static int is_serial(int fd){
    char p[PATH_MAX];
    if (fcntl(fd, F_GETPATH, p) == 0 && strstr(p, "usbserial")) return 1;
    return 0;
}
static void dump(const char *dir, int fd, const unsigned char *b, long n){
    FILE *f = L(); if(!f || n<=0) return;
    pthread_mutex_lock(&mtx);
    fprintf(f, "%s len=%ld: ", dir, n);
    for(long i=0;i<n;i++) fprintf(f, "%02x", b[i]);
    fprintf(f, "\n");
    pthread_mutex_unlock(&mtx);
}

ssize_t my_write(int fd, const void *buf, size_t n){
    ssize_t r = write(fd, buf, n);
    if (r > 0 && is_serial(fd)) dump(">>W", fd, (const unsigned char*)buf, r);
    return r;
}
ssize_t my_read(int fd, void *buf, size_t n){
    ssize_t r = read(fd, buf, n);
    if (r > 0 && is_serial(fd)) dump("<<R", fd, (const unsigned char*)buf, r);
    return r;
}
int my_ioctl(int fd, unsigned long req, ...){
    va_list ap; va_start(ap, req); void *arg = va_arg(ap, void*); va_end(ap);
    int r = ioctl(fd, req, arg);
    if (is_serial(fd)) {
        FILE *f = L();
        if (f) {
            pthread_mutex_lock(&mtx);
            if (req == IOSSIOSPEED && arg) fprintf(f, "## IOSSIOSPEED baud=%u\n", *(unsigned int*)arg);
            else fprintf(f, "## ioctl req=0x%lx\n", req);
            pthread_mutex_unlock(&mtx);
        }
    }
    return r;
}
DYLD_INTERPOSE(my_write, write)
DYLD_INTERPOSE(my_read, read)
DYLD_INTERPOSE(my_ioctl, ioctl)

__attribute__((constructor)) static void init(void){ FILE *f=L(); if(f) fprintf(f, "=== interposer loaded ===\n"); }
