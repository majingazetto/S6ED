.PHONY: all clean tobin

ISMINGW := $(shell uname | grep MINGW)

ifneq ($(ISMINGW),)
program 	= dsktool.exe
cpuprogram	= cpu.exe
else
program 	= dsktool
cpuprogram	= cpu
endif

BINDST = ../../bin
CPU = $(shell ./${cpuprogram})

all: cpu dsktool tobin

CC = gcc
CFLAGS = -O2 -Wall -fomit-frame-pointer

cpu:	
	$(CC) cpu.c -o $(cpuprogram)

dsktool: dsktool.c
	$(CC) $(CFLAGS) -DCPUBYTE=$(if $(CPU),$(CPU),0) $^ -o $(program)
	@echo "$@: $^" > $@.d

clean:
	rm -f $(program)
	rm -f $(cpuprogram)
	rm -f *.d

tobin:
	@if [ -d $(BINDST) ] ;\
	then \
		cp $(program) $(BINDST) ;\
	fi

-include *.d
